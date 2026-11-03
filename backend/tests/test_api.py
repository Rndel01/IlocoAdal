import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document

from ilocoadal.config import Config
from ilocoadal.definition_fetcher import DefinitionFetcher
from ilocoadal.errors import (ApiUnavailableError, ConfigError, NoFilesError,
                              TextExtractionError, UnsupportedFileError)
from ilocoadal.models import NOT_AVAILABLE
from ilocoadal.process_manager import ProcessManager
from ilocoadal.server import make_server
from ilocoadal.service import JobService, ServiceError
from ilocoadal.text_translator import TextTranslator

PLANTS = [
    "Photosynthesis is the process plants use to make food.",
    "Photosynthesis takes place in the chloroplasts of plant cells.",
    "Chlorophyll is the green pigment that absorbs sunlight.",
    "Stomata open and close to control gas exchange in the leaves.",
    "Plants release oxygen during photosynthesis every single day.",
]
CODE = [
    "An algorithm is a step by step set of instructions for solving a problem.",
    "The algorithm sorts the list before searching it for the answer.",
    "A model learns patterns from the training data it is given.",
    "The model predicts new values after the algorithm finishes training.",
]


def make_pdf(path: Path, sentences=PLANTS, pages: int = 1) -> Path:
    """A tiny valid PDF with real text (no extra libraries needed)."""
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = "BT /F1 11 Tf 14 TL 40 780 Td " + " ".join(f"({esc(s)}) ' " for s in sentences) + "ET"
    page_ids = [3 + 2 * i for i in range(pages)]
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] /Count {pages} >>"]
    font_id = 3 + 2 * pages
    for i in range(pages):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    path.write_bytes(out)
    return path


def wait_for(get_state, wanted, timeout=10):
    end = time.time() + timeout
    state = None
    while time.time() < end:
        state = get_state()
        if state in wanted:
            return state
        time.sleep(0.02)
    raise AssertionError(f"timed out; last value {state}")


class ConfigTests(unittest.TestCase):
    def test_defaults_and_partial_file(self):
        cfg = Config.from_dict({"analysis": {"top_n": 4}, "_note": "ignored"})
        self.assertEqual(cfg.analysis.top_n, 4)
        self.assertEqual(cfg.analysis.max_contexts, 2)

    def test_design_defaults(self):
        cfg = Config()
        self.assertEqual(cfg.files.max_file_size_mb, 20)   # "up to 20MB" on the Upload screen
        self.assertFalse(cfg.analysis.review_terms)         # the design has no Review screen
        self.assertTrue(cfg.analysis.ask_when_offline)      # the design has a "No internet" screen

    def test_shipped_config_matches_defaults(self):
        shipped = Config.load(Path(__file__).resolve().parent.parent / "config.json")
        self.assertEqual(shipped, Config())

    def test_rejects_typos_wrong_types_and_bad_values(self):
        for bad in ({"analysis": {"topn": 3}}, {"analysis": {"top_n": "3"}},
                    {"analysis": {"top_n": True}}, {"analysis": {"top_n": 0}},
                    {"analysis": {"heading_form": "x"}}, {"nope": {}},
                    {"files": {"max_files": 0}}, {"server": {"port": 70000}}):
            with self.assertRaises(ConfigError, msg=bad):
                Config.from_dict(bad)

    def test_missing_and_broken_file(self):
        with self.assertRaises(ConfigError):
            Config.load("/no/such/config.json")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.json"
            f.write_text("{oops")
            with self.assertRaises(ConfigError):
                Config.load(f)

    def test_public_dict_hides_secrets(self):
        cfg = Config()
        cfg.translation.api_key = "SECRET"
        cfg.server.auth_token = "TOKEN"
        text = json.dumps(cfg.public_dict())
        self.assertNotIn("SECRET", text)
        self.assertNotIn("TOKEN", text)
        self.assertTrue(cfg.public_dict()["translation"]["api_key_configured"])

    def test_job_overrides(self):
        cfg = Config().with_overrides({"top_n": 3, "online": False, "target_language": "tl"})
        self.assertEqual(cfg.analysis.top_n, 3)
        self.assertFalse(cfg.dictionary.enabled or cfg.translation.enabled)
        self.assertEqual(Config().analysis.top_n, 10)
        with self.assertRaises(ConfigError):
            Config().with_overrides({"files": 1})


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.cfg = Config.from_dict({"files": {"output_dir": self.tmp.name}})

    def test_settings_are_used(self):
        cfg = Config.from_dict({
            "analysis": {"top_n": 2, "heading_form": "shortest"},
            "text": {"extra_filler_words": ["photosynthesis"]},
            "files": {"max_file_size_mb": 0.0001},
            "dictionary": {"language": "tl", "max_definitions": 1},
            "document": {"title": "My notes", "include_context": False},
        })
        m = ProcessManager(cfg, online=False)
        self.assertEqual(m.analyzer.top_n, 2)
        self.assertEqual(m.analyzer.heading_form, "shortest")
        self.assertEqual(m.processor.tokenize("Photosynthesis plants"), ["plants"])
        self.assertEqual(m.fetcher.language, "tl")
        self.assertEqual(m.builder.title, "My notes")
        with self.assertRaises(UnsupportedFileError):
            m.validate(make_pdf(self.dir / "a.pdf"))

    def test_steps_follow_the_processing_screen(self):
        m = ProcessManager(Config())
        self.assertEqual([m.STEP_LABELS[k] for k in m.steps], [
            "Reading document", "Extract and clean text", "Rank key terms",
            "Find context sentences", "Fetching definitions", "Translating content",
            "Build document"])
        self.assertEqual(len(ProcessManager(Config(), online=False).steps), 5)

    def test_language_goes_into_url(self):
        f = DefinitionFetcher(language="tl")
        with patch.object(f, "_request", return_value=[]) as r:
            f.get_definition("Bahay")
        self.assertTrue(r.call_args[0][0].endswith("/tl/bahay"))

    def test_output_never_overwrites(self):
        m = ProcessManager(Config.from_dict({"files": {"output_dir": str(self.dir / "out")}}),
                           online=False)
        first = m.default_output_path("a.pdf")
        first.write_bytes(b"x")
        self.assertEqual(m.default_output_path("a.pdf").name, "a_key_terms_2.docx")
        self.assertEqual(m.default_output_path(["a.pdf", "b.pdf"]).name, "combined_key_terms.docx")

    def test_unselected_terms_are_left_out(self):
        m = ProcessManager(self.cfg, online=False)
        analysis = m.analyze(make_pdf(self.dir / "a.pdf"))
        dropped = analysis.terms[0]
        dropped.selected = False
        out = m.build(analysis)
        text = "\n".join(p.text for p in Document(str(out)).paragraphs)
        self.assertNotIn(f"1. {dropped.word}", text)
        self.assertIn(f"{len(analysis.terms) - 1} key terms", text)

    # -- the "Ready to Process" list --------------------------------------------
    def test_describe_file(self):
        pdf = make_pdf(self.dir / "Chapter 1.pdf", pages=3)
        info = ProcessManager(self.cfg).describe_file(pdf)
        self.assertEqual((info["name"], info["format"], info["pages"]), ("Chapter 1.pdf", "PDF", 3))
        self.assertEqual(info["size_bytes"], pdf.stat().st_size)
        self.assertIsInstance(info["size_mb"], float)

    def test_describe_file_rejects_bad_files(self):
        m = ProcessManager(self.cfg)
        bad = self.dir / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        with self.assertRaises(TextExtractionError):
            m.describe_file(bad)
        with self.assertRaises(UnsupportedFileError):
            m.describe_file(self.dir / "missing.pdf")

    # -- several documents, one combined result ------------------------------------
    def test_combined_analysis(self):
        m = ProcessManager(Config.from_dict({"files": {"output_dir": self.tmp.name},
                                             "analysis": {"top_n": 30}}), online=False)
        a = make_pdf(self.dir / "plants.pdf", PLANTS)
        b = make_pdf(self.dir / "code.pdf", CODE)
        analysis = m.analyze([a, b])
        words = {t.word for t in analysis.terms}
        self.assertTrue({"photosynthesis", "algorithm", "model"} <= words)
        self.assertEqual(analysis.source_names, ["plants.pdf", "code.pdf"])
        out = m.build(analysis)
        self.assertEqual(out.name, "combined_key_terms.docx")
        text = "\n".join(p.text for p in Document(str(out)).paragraphs)
        self.assertIn("plants.pdf, code.pdf", text)

    def test_unreadable_document_is_skipped_with_warning(self):
        m = ProcessManager(self.cfg, online=False)
        good = make_pdf(self.dir / "good.pdf")
        empty = make_pdf(self.dir / "scan.pdf", [])
        analysis = m.analyze([empty, good])
        self.assertEqual(analysis.source_names, ["good.pdf"])
        self.assertEqual(analysis.warnings[0].code, "file_skipped")
        with self.assertRaises(TextExtractionError):
            m.analyze([empty])

    def test_no_documents_and_too_many(self):
        m = ProcessManager(Config.from_dict({"files": {"max_files": 1}}), online=False)
        with self.assertRaises(NoFilesError):
            m.analyze([])
        a, b = make_pdf(self.dir / "a.pdf"), make_pdf(self.dir / "b.pdf")
        with self.assertRaises(UnsupportedFileError):
            m.analyze([a, b])


class ServiceFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.plants = make_pdf(self.dir / "plants.pdf", PLANTS, pages=2)
        self.code = make_pdf(self.dir / "code.pdf", CODE)
        self.cfg = Config.from_dict({"files": {"output_dir": self.tmp.name},
                                     "translation": {"api_key": "k"}})
        self.svc = JobService(self.cfg)

    def test_draft_add_remove_and_start(self):
        job = self.svc.create_job()
        self.assertEqual(job.status()["state"], "draft")
        self.assertFalse(job.status()["can_start"])
        with self.assertRaises(NoFilesError):
            self.svc.start(job)

        first = self.svc.add_file(job, str(self.plants))
        self.assertEqual((first["name"], first["format"], first["pages"]), ("plants.pdf", "PDF", 2))
        self.assertNotIn("_resolved", first)
        second = self.svc.add_file(job, str(self.code))
        self.assertEqual([f["name"] for f in self.svc.files(job)], ["plants.pdf", "code.pdf"])
        self.assertTrue(job.status()["can_start"])

        with self.assertRaises(ServiceError) as cm:
            self.svc.add_file(job, str(self.code))
        self.assertEqual(cm.exception.code, "duplicate_file")
        with self.assertRaises(UnsupportedFileError):
            self.svc.add_file(job, str(self.dir / "missing.pdf"))
        self.assertEqual(len(self.svc.files(job)), 2)           # list unchanged by failures

        self.svc.remove_file(job, first["id"])
        self.assertEqual([f["name"] for f in self.svc.files(job)], ["code.pdf"])
        with self.assertRaises(ServiceError):
            self.svc.remove_file(job, "nope")

    def test_max_files(self):
        svc = JobService(Config.from_dict({"files": {"max_files": 1}}))
        job = svc.create_job()
        svc.add_file(job, str(self.plants))
        with self.assertRaises(UnsupportedFileError):
            svc.add_file(job, str(self.code))

    def test_full_run_matches_the_screens(self):
        def define(self_, word):
            return [NOT_AVAILABLE] if word == "model" else ["(noun) A thing."]
        translate = lambda self_, texts: [f"T:{t}" for t in texts]
        job = self.svc.create_job({"top_n": 30}, [str(self.plants), str(self.code)])
        with patch.object(DefinitionFetcher, "get_definition", define), \
             patch.object(TextTranslator, "translate_many", translate):
            self.svc.start(job)
            wait_for(lambda: job.state, {"done", "error"})
        status = job.status()
        self.assertEqual(status["state"], "done", status["error"])

        self.assertEqual(status["total_steps"], 7)
        self.assertEqual([s["status"] for s in status["steps"]], ["done"] * 7)
        self.assertEqual(status["steps"][4]["label"], "Fetching definitions")
        self.assertEqual(status["progress"], 1.0)
        # Results banner: "N key terms found. 1 terms had no definition available."
        self.assertEqual(status["summary"]["document_count"], 2)
        self.assertEqual(status["summary"]["term_count"], len(self.svc.terms(job)))
        self.assertEqual(status["summary"]["without_definition"], 1)

        terms = {t["word"]: t for t in self.svc.terms(job)}
        self.assertEqual(terms["model"]["definitions"], [NOT_AVAILABLE])
        self.assertEqual(terms["algorithm"]["translated_definitions"], ["T:(noun) A thing."])
        self.assertTrue(terms["algorithm"]["translated_contexts"][0].startswith("T:"))
        self.assertEqual(max(t["relative_score"] for t in terms.values()), 1.0)
        self.assertEqual(self.svc.document(job).name, "combined_key_terms.docx")

    # -- no internet: pause, then Try again / Continue without ---------------------
    @staticmethod
    def _down(self_, word):
        raise ApiUnavailableError("down")

    def test_offline_pauses_then_retry_resumes(self):
        with patch.object(DefinitionFetcher, "get_definition", self._down):
            job = self.svc.create_job({"top_n": 3}, [str(self.plants)], start=True)
            wait_for(lambda: job.state, {"offline", "done", "error"})
        self.assertEqual(job.state, "offline")
        self.assertIsNone(job.document_path)
        calls = []
        def ok(self_, word):
            calls.append(word)
            return ["(noun) A thing."]
        with patch.object(DefinitionFetcher, "get_definition", ok), \
             patch.object(TextTranslator, "translate_many", lambda s_, t: list(t)):
            self.svc.retry(job)
            wait_for(lambda: job.state, {"done", "error", "offline"})
        self.assertEqual(job.state, "done", job.status()["error"])
        self.assertEqual(len(calls), 3)
        self.assertEqual(job.status()["warnings"], [])

    def test_offline_skip_builds_without_online_data(self):
        with patch.object(DefinitionFetcher, "get_definition", self._down):
            job = self.svc.create_job({"top_n": 3}, [str(self.plants)], start=True)
            wait_for(lambda: job.state, {"offline", "done", "error"})
        self.assertEqual(job.state, "offline")
        self.svc.skip_online(job)
        wait_for(lambda: job.state, {"done", "error"})
        status = job.status()
        self.assertEqual(status["state"], "done", status["error"])
        self.assertEqual(status["warnings"][0]["code"], "no_internet")
        by_key = {x["key"]: x["status"] for x in status["steps"]}
        self.assertEqual((by_key["definitions"], by_key["translate"], by_key["build"]),
                         ("skipped", "skipped", "done"))
        self.assertEqual(status["progress"], 1.0)
        text = "\n".join(p.text for p in Document(str(self.svc.document(job))).paragraphs)
        self.assertNotIn("Definition", text)

    def test_ask_when_offline_false_continues_with_warning(self):
        with patch.object(DefinitionFetcher, "get_definition", self._down), \
             patch.object(TextTranslator, "translate_many", lambda s_, t: list(t)):
            job = self.svc.create_job({"top_n": 3, "ask_when_offline": False},
                                      [str(self.plants)], start=True)
            wait_for(lambda: job.state, {"offline", "done", "error"})
        self.assertEqual(job.state, "done")
        self.assertEqual(job.status()["warnings"][0]["code"], "no_internet")

    def test_cancel_while_offline_and_wrong_state(self):
        with patch.object(DefinitionFetcher, "get_definition", self._down):
            job = self.svc.create_job({"top_n": 3}, [str(self.plants)], start=True)
            wait_for(lambda: job.state, {"offline", "done", "error"})
        self.svc.cancel(job)
        self.assertEqual(job.state, "cancelled")
        for action in (self.svc.retry, self.svc.skip_online):
            with self.assertRaises(ServiceError) as cm:
                action(job)
            self.assertEqual(cm.exception.code, "wrong_state")

    def test_steps_mid_run(self):
        job = self.svc.create_job({"online": False}, [str(self.plants)])
        job.step, job.state = 3, "analyzing"
        self.assertEqual([s["status"] for s in job.status()["steps"]],
                         ["done", "done", "active", "pending", "pending"])
        job.state = "error"
        self.assertEqual(job.status()["steps"][2]["status"], "error")

    def test_review_flow_when_enabled(self):
        job = self.svc.create_job({"review": True, "top_n": 3, "online": False}, [str(self.plants)])
        self.svc.start(job)
        wait_for(lambda: job.state, {"review", "error"})
        self.assertEqual(job.state, "review")
        terms = self.svc.terms(job)
        self.svc.set_selected(job, terms[0]["id"], False)
        self.assertEqual(self.svc.add_term(job, "stomata")["word"], "stomata")
        self.svc.continue_job(job)
        wait_for(lambda: job.state, {"done", "error"})
        self.assertEqual(job.status()["summary"]["term_count"], 3)

    def test_no_review_by_default_and_missing_key_warns(self):
        svc = JobService(Config.from_dict({"files": {"output_dir": self.tmp.name},
                                           "dictionary": {"enabled": False},
                                           "translation": {"api_key": "", "api_key_env": "NOPE_NOT_SET"}}))
        job = svc.create_job(paths=[str(self.plants)], start=True)
        wait_for(lambda: job.state, {"done", "error"})
        self.assertEqual(job.state, "done")
        self.assertEqual(job.status()["warnings"][0]["code"], "translation_not_configured")

    def test_unreadable_document_becomes_error_state(self):
        scan = make_pdf(self.dir / "scan.pdf", [])
        job = self.svc.create_job({"online": False}, [str(scan)], start=True)
        wait_for(lambda: job.state, {"error"})
        self.assertEqual(job.status()["error"]["code"], "cannot_read")

    def test_bad_inputs(self):
        with self.assertRaises(UnsupportedFileError):
            self.svc.create_job(paths=[str(self.dir / "missing.pdf")])
        with self.assertRaises(ServiceError):
            self.svc.create_job({"bogus": 1})
        with self.assertRaises(ServiceError):
            self.svc.get("deadbeef")
        job = self.svc.create_job({"online": False}, [str(self.plants)], start=True)
        with self.assertRaises(ServiceError) as cm:
            self.svc.add_file(job, str(self.code))               # only while draft
        self.assertEqual(cm.exception.code, "wrong_state")

    def test_cancel_in_draft_and_review(self):
        job = self.svc.create_job(paths=[str(self.plants)])
        self.svc.cancel(job)
        self.assertEqual(job.state, "cancelled")
        job = self.svc.create_job({"review": True, "online": False}, [str(self.plants)], start=True)
        wait_for(lambda: job.state, {"review"})
        self.svc.cancel(job)
        self.assertEqual(job.state, "cancelled")
        with self.assertRaises(ServiceError) as cm:
            self.svc.continue_job(job)
        self.assertEqual(cm.exception.code, "wrong_state")

    def test_cancel_while_running(self):
        gate = threading.Event()
        def slow(self_, word):
            gate.wait(5)
            return ["d"]
        job = self.svc.create_job({"review": True}, [str(self.plants)], start=True)
        wait_for(lambda: job.state, {"review"})
        with patch.object(DefinitionFetcher, "get_definition", slow):
            self.svc.continue_job(job)
            wait_for(lambda: job.label, {"Fetching definitions"})
            self.svc.cancel(job)
            gate.set()
            wait_for(lambda: job.state, {"cancelled", "done", "error"})
        self.assertEqual(job.state, "cancelled")

    def test_continue_needs_a_selected_term(self):
        job = self.svc.create_job({"review": True, "top_n": 2}, [str(self.plants)], start=True)
        wait_for(lambda: job.state, {"review"})
        for t in self.svc.terms(job):
            self.svc.set_selected(job, t["id"], False)
        with self.assertRaises(Exception) as cm:
            self.svc.continue_job(job)
        self.assertEqual(cm.exception.code, "no_key_terms")


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.plants = make_pdf(cls.dir / "plants.pdf", PLANTS, pages=2)
        cls.code = make_pdf(cls.dir / "code.pdf", CODE)
        cfg = Config.from_dict({
            "files": {"output_dir": cls.tmp.name},
            "server": {"port": 0, "auth_token": "tok", "allow_origin": "http://localhost:5000"},
            "dictionary": {"enabled": False}, "translation": {"enabled": False},
        })
        cls.server = make_server(cfg)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, token="tok", raw=False):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        req = request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with request.urlopen(req) as resp:
                payload = resp.read()
                return resp.status, (payload if raw else (json.loads(payload) if payload else None)), resp
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read()), exc

    def test_health_needs_no_token_but_everything_else_does(self):
        self.assertEqual(self.call("GET", "/health", token=None)[0], 200)
        status, body, _ = self.call("GET", "/config", token=None)
        self.assertEqual((status, body["error"]["code"]), (401, "unauthorized"))
        status, body, resp = self.call("GET", "/config")
        self.assertEqual(status, 200)
        self.assertEqual(body["files"]["max_file_size_mb"], 20)
        self.assertNotIn("auth_token", body["server"])
        self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "http://localhost:5000")

    def test_the_four_screens_over_http(self):
        # Upload screen -> Ready to Process
        status, job, _ = self.call("POST", "/jobs", {"options": {"top_n": 20}})
        self.assertEqual((status, job["state"]), (201, "draft"))
        jid = job["id"]
        status, f1, _ = self.call("POST", f"/jobs/{jid}/files", {"path": str(self.plants)})
        self.assertEqual((status, f1["name"], f1["format"], f1["pages"]), (201, "plants.pdf", "PDF", 2))
        _, f2, _ = self.call("POST", f"/jobs/{jid}/files", {"path": str(self.code)})
        self.assertEqual(len(self.call("GET", f"/jobs/{jid}/files")[1]["files"]), 2)
        self.assertEqual(self.call("DELETE", f"/jobs/{jid}/files/{f2['id']}")[0], 204)   # the X button
        self.call("POST", f"/jobs/{jid}/files", {"path": str(self.code)})                # upload another
        self.assertEqual(self.call("POST", f"/jobs/{jid}/files", {"path": str(self.code)})[1]["error"]["code"],
                         "duplicate_file")
        self.assertTrue(self.call("GET", f"/jobs/{jid}")[1]["can_start"])

        # Start Processing -> Processing screen
        self.assertEqual(self.call("POST", f"/jobs/{jid}/start")[0], 202)
        wait_for(lambda: self.call("GET", f"/jobs/{jid}")[1]["state"], {"done", "error"})

        # Results screen
        status = self.call("GET", f"/jobs/{jid}")[1]
        self.assertEqual(status["state"], "done", status["error"])
        self.assertEqual(status["summary"]["document_count"], 2)
        terms = self.call("GET", f"/jobs/{jid}/terms")[1]["terms"]
        self.assertEqual(status["summary"]["term_count"], len(terms))
        code, doc, _ = self.call("GET", f"/jobs/{jid}/document", raw=True)
        self.assertEqual(code, 200)
        self.assertTrue(doc.startswith(b"PK"))
        self.assertEqual(self.call("DELETE", f"/jobs/{jid}")[0], 204)
        self.assertEqual(self.call("GET", f"/jobs/{jid}")[0], 404)

    def test_shortcuts_and_errors(self):
        status, job, _ = self.call("POST", "/jobs", {"path": str(self.plants), "start": True,
                                                    "options": {"online": False}})
        self.assertEqual(status, 201)
        wait_for(lambda: self.call("GET", f"/jobs/{job['id']}")[1]["state"], {"done"})

        status, body, _ = self.call("POST", "/jobs", {"paths": ["/nope/x.pdf"]})
        self.assertEqual((status, body["error"]["code"]), (400, "unsupported_file"))
        self.assertEqual(self.call("POST", "/jobs", {"paths": "x"})[1]["error"]["code"], "bad_request")
        draft = self.call("POST", "/jobs", {})[1]["id"]
        self.assertEqual(self.call("POST", f"/jobs/{draft}/start")[1]["error"]["code"], "no_files")
        self.assertEqual(self.call("POST", f"/jobs/{draft}/files", {})[1]["error"]["code"], "bad_request")
        self.assertEqual(self.call("GET", f"/jobs/{draft}/document")[0], 409)
        self.assertEqual(self.call("POST", f"/jobs/{draft}/retry")[1]["error"]["code"], "wrong_state")
        self.assertEqual(self.call("POST", f"/jobs/{draft}/skip_online")[1]["error"]["code"], "wrong_state")
        self.assertEqual(self.call("GET", "/elsewhere")[0], 404)


if __name__ == "__main__":
    unittest.main()
