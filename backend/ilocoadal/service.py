"""Job layer between the HTTP server and ProcessManager.

A job moves through these states (what the Flutter app polls for):

    draft -> analyzing -> enriching -> building -> done
    draft -> analyzing -> review -> enriching -> building -> done
                          (only when analysis.review_terms is true)
    enriching -> offline -> (retry) enriching | (skip_online) enriching -> building
                          (only when analysis.ask_when_offline is true)
    any state -> error | cancelled

`draft` is the "Ready to Process" screen: documents can be added and removed
until Start Processing. Analysis then runs in a background thread so the UI
stays responsive.
"""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Iterable, Optional

from .config import Config
from .errors import (ApiError, CancelledError, ConfigError, NoFilesError, NoKeyTermsError,
                     UnsupportedFileError)
from .models import NOT_AVAILABLE, AnalysisWarning
from .process_manager import STEP_LABELS, ProcessManager

FINISHED = {"done", "error", "cancelled"}
RUNNING = {"analyzing", "enriching", "building"}


class ServiceError(Exception):
    """An error with an HTTP status and a stable code for the app."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Job:
    def __init__(self, job_id: str, manager: ProcessManager) -> None:
        self.id = job_id
        self.manager = manager
        self.state = "draft"
        self.files: list[dict] = []
        self.step, self.total, self.label = 0, len(manager.steps), ""
        self.analysis = None
        self.error: Optional[dict] = None
        self.document_path: Optional[Path] = None
        self.skipped_online = False      # the user chose "Continue without definitions"
        self.updated = time.time()
        self.lock = threading.RLock()

    def set_state(self, state: str) -> None:
        with self.lock:
            self.state, self.updated = state, time.time()

    def on_progress(self, step: int, total: int, label: str) -> None:
        with self.lock:
            self.step, self.total, self.label = step, total, label
            if self.manager.steps[step - 1] == "build":
                self.state = "building"
            self.updated = time.time()

    def _steps(self) -> list[dict]:
        """The Processing screen's checklist: done / active / pending."""
        out = []
        for i, key in enumerate(self.manager.steps, start=1):
            if self.state == "done" or (self.state == "review" and i <= self.step):
                status = "done"
            elif i < self.step:
                status = "done"
            elif i == self.step:
                status = {"error": "error", "cancelled": "cancelled"}.get(self.state, "active")
            else:
                status = "pending"
            if self.skipped_online and key in ("definitions", "translate"):
                status = "skipped"
            out.append({"key": key, "label": STEP_LABELS[key], "status": status})
        return out

    def _summary(self) -> Optional[dict]:
        """The Results screen's banner: "7 key terms found. 1 had no definition"."""
        if self.analysis is None:
            return None
        chosen = self.analysis.selected_terms()
        return {
            "document_count": len(self.analysis.source_names) or len(self.files),
            "term_count": len(chosen),
            "without_definition": sum(1 for t in chosen if t.definitions == [NOT_AVAILABLE]),
        }

    def status(self) -> dict:
        with self.lock:
            steps = self._steps()
            return {
                "id": self.id,
                "state": self.state,
                "files": [dict(f) for f in self.files],
                "can_start": self.state == "draft" and bool(self.files),
                "step": self.step,
                "total_steps": self.total,
                "label": self.label,
                "steps": steps,
                "progress": (sum(s["status"] in ("done", "skipped") for s in steps) / len(steps))
                            if steps else 0.0,
                "summary": self._summary(),
                "error": self.error,
                "warnings": [w.to_dict() for w in (self.analysis.warnings if self.analysis else [])],
                "document_ready": self.state == "done",
                "document_path": str(self.document_path) if self.document_path else None,
            }


class JobService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # -- lookup ---------------------------------------------------------------
    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise ServiceError(404, "not_found", "That job does not exist.")
        return job

    def _purge(self) -> None:
        cutoff = time.time() - self.config.server.job_ttl_minutes * 60
        with self._lock:
            for jid in [j for j, job in self._jobs.items()
                        if (job.state in FINISHED or job.state == "draft") and job.updated < cutoff]:
                del self._jobs[jid]   # the output files are kept

    # -- create / documents -------------------------------------------------------
    def create_job(
        self,
        options: Optional[dict] = None,
        paths: Optional[Iterable[str]] = None,
        start: bool = False,
    ) -> Job:
        """A new job in `draft`. Documents given in `paths` are added at once
        (an unusable one raises its error and no job is kept)."""
        self._purge()
        try:
            config = self.config.with_overrides(options or {})
        except ConfigError as exc:
            raise ServiceError(400, exc.code, str(exc)) from exc
        job = Job(uuid.uuid4().hex[:12], ProcessManager(config))
        for path in paths or []:
            self.add_file(job, path)
        with self._lock:
            self._jobs[job.id] = job
        if start:
            self.start(job)
        return job

    def _need_draft(self, job: Job) -> None:
        if job.state != "draft":
            raise ServiceError(409, "wrong_state",
                               f"Documents can only be changed before processing (job is {job.state}).")

    def add_file(self, job: Job, path: str) -> dict:
        """Check the document and add it to the list. Raises the error for the
        error screen if it can't be used (the list stays unchanged)."""
        with job.lock:
            self._need_draft(job)
            resolved = str(Path(path).resolve())
            if any(f["_resolved"] == resolved for f in job.files):
                raise ServiceError(400, "duplicate_file", "That document is already added.")
            limit = job.manager.config.files.max_files
            if len(job.files) >= limit:
                raise UnsupportedFileError(f"You can add up to {limit} documents at once.")
            entry = {"id": uuid.uuid4().hex[:8], **job.manager.describe_file(path),
                     "_resolved": resolved}
            job.files.append(entry)
            return self._public_file(entry)

    @staticmethod
    def _public_file(entry: dict) -> dict:
        return {k: v for k, v in entry.items() if not k.startswith("_")}

    def files(self, job: Job) -> list[dict]:
        with job.lock:
            return [self._public_file(f) for f in job.files]

    def remove_file(self, job: Job, file_id: str) -> None:
        with job.lock:
            self._need_draft(job)
            for i, entry in enumerate(job.files):
                if entry["id"] == file_id:
                    del job.files[i]
                    return
        raise ServiceError(404, "not_found", "That document is not in the list.")

    # -- run -----------------------------------------------------------------------
    def start(self, job: Job) -> None:
        with job.lock:
            self._need_draft(job)
            if not job.files:
                raise NoFilesError("Add a document first.")
            job.state, job.updated = "analyzing", time.time()
        self._start(self._analyze, job)

    @staticmethod
    def _start(target, job: Job, *args) -> None:
        threading.Thread(target=target, args=(job, *args), daemon=True).start()

    def _fail(self, job: Job, exc: Exception) -> None:
        if isinstance(exc, CancelledError):
            job.set_state("cancelled")
            return
        with job.lock:
            job.error = {"code": getattr(exc, "code", "unknown"),
                         "message": job.manager.handle_error(exc)}
        job.set_state("error")

    def _analyze(self, job: Job) -> None:
        try:
            job.analysis = job.manager.analyze([f["path"] for f in job.files], job.on_progress)
            if job.manager.config.analysis.review_terms:
                job.set_state("review")
            else:
                self._finish(job)
        except Exception as exc:  # noqa: BLE001 - every failure becomes a job error
            self._fail(job, exc)

    def _finish(self, job: Job, skip_online: bool = False) -> None:
        try:
            job.set_state("enriching")
            if skip_online:
                with job.lock:
                    job.skipped_online = True
                    if not any(w.code == "no_internet" for w in job.analysis.warnings):
                        job.analysis.warnings.append(AnalysisWarning(
                            "no_internet",
                            "No internet connection. Definitions and translations were left out."))
            else:
                try:
                    job.manager.enrich(job.analysis, job.on_progress,
                                       strict=job.manager.config.analysis.ask_when_offline)
                except ApiError:
                    job.set_state("offline")   # the app asks: Try again / Continue without
                    return
            path = job.manager.build(job.analysis, None, job.on_progress)
            with job.lock:
                job.document_path = path
            job.set_state("done")
        except Exception as exc:  # noqa: BLE001
            self._fail(job, exc)

    # -- terms (Results screen; Review screen when enabled) -----------------------------
    def _need_review(self, job: Job) -> None:
        if job.state != "review":
            raise ServiceError(409, "wrong_state",
                               f"This is only possible while reviewing (job is {job.state}).")

    @staticmethod
    def _term_dict(term, top_score: float) -> dict:
        data = term.to_dict()
        data["relative_score"] = round(term.score / top_score, 4) if top_score else 0.0
        return data

    def terms(self, job: Job) -> list[dict]:
        if job.analysis is None:
            raise ServiceError(409, "wrong_state", "The terms are not ready yet.")
        top = max((t.score for t in job.analysis.terms), default=0.0)
        return [self._term_dict(t, top) for t in job.analysis.terms]

    def set_selected(self, job: Job, term_id: str, selected: bool) -> dict:
        with job.lock:
            self._need_review(job)
            top = max((t.score for t in job.analysis.terms), default=0.0)
            for term in job.analysis.terms:
                if term.id == term_id:
                    term.selected = selected
                    return self._term_dict(term, top)
        raise ServiceError(404, "not_found", "That term does not exist.")

    def add_term(self, job: Job, word: str) -> dict:
        with job.lock:
            self._need_review(job)
            term = job.manager.add_term(job.analysis, word)
            top = max((t.score for t in job.analysis.terms), default=0.0)
            return self._term_dict(term, top)

    def continue_job(self, job: Job) -> None:
        with job.lock:
            self._need_review(job)
            if not job.analysis.selected_terms():
                raise NoKeyTermsError("Select at least one key term.")
            job.state = "enriching"
        self._start(self._finish, job)

    # -- offline: the user decides -------------------------------------------------------
    def _need_offline(self, job: Job) -> None:
        if job.state != "offline":
            raise ServiceError(409, "wrong_state",
                               f"This is only possible after a connection problem (job is {job.state}).")

    def retry(self, job: Job) -> None:
        """"Try again": resumes the online steps where they stopped."""
        with job.lock:
            self._need_offline(job)
            job.state = "enriching"
        self._start(self._finish, job)

    def skip_online(self, job: Job) -> None:
        """"Continue without definitions": builds the document with what it has."""
        with job.lock:
            self._need_offline(job)
            job.state, job.skipped_online = "enriching", True
        self._start(self._finish, job, True)

    # -- finish up -------------------------------------------------------------------------
    def cancel(self, job: Job) -> None:
        with job.lock:
            if job.state in FINISHED:
                return
            if job.state in {"draft", "review", "offline"}:   # nothing is running
                job.set_state("cancelled")
                return
        job.manager.cancel()                           # the worker stops at the next step

    def document(self, job: Job) -> Path:
        if job.state != "done" or not job.document_path:
            raise ServiceError(409, "wrong_state", "The document is not ready yet.")
        return job.document_path

    def delete(self, job: Job) -> None:
        if job.state in RUNNING:
            raise ServiceError(409, "wrong_state", "Cancel the job first.")
        with self._lock:
            self._jobs.pop(job.id, None)
