"""Controller: runs the use cases in order (see the UCD) and reports progress."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import re
import threading
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .definition_fetcher import DefinitionFetcher
from .document_builder import DocumentBuilder
from .errors import (ApiError, CancelledError, IlocoAdalError, NoFilesError,
                     TermNotFoundError, TextExtractionError, UnsupportedFileError)
from .models import NOT_AVAILABLE, AnalysisResult, AnalysisWarning, Term
from .normalizer import make_normalizer
from .text_analyzer import TextAnalyzer
from .text_extractor import get_extractor
from .text_processor import TextProcessor
from .text_translator import TextTranslator
from .textutil import forms_pattern

ProgressCallback = Callable[[int, int, str], None]  # (step, total, label)
ReviewCallback = Callable[[AnalysisResult], None]   # may edit analysis.terms

# Step keys, in order, with the wording used on the Processing screen.
STEP_LABELS = {
    "read": "Reading document",
    "clean": "Extract and clean text",
    "rank": "Rank key terms",
    "contexts": "Find context sentences",
    "definitions": "Fetching definitions",
    "translate": "Translating content",
    "build": "Build document",
}


class ProcessManager:
    """Three phases, so the "Review key terms" screen fits in the middle:

        analysis = manager.analyze(path)      # offline
        # ...user reviews / edits analysis.terms (term.selected)...
        manager.enrich(analysis)              # internet (skipped if disabled)
        manager.build(analysis)               # offline

    start_process() runs all three. All settings come from `Config`; the
    component arguments are for tests or custom replacements.
    """

    STEPS = list(STEP_LABELS)           # keys, in order
    STEP_LABELS = STEP_LABELS

    def __init__(
        self,
        config: Optional[Config] = None,
        processor: Optional[TextProcessor] = None,
        analyzer: Optional[TextAnalyzer] = None,
        builder: Optional[DocumentBuilder] = None,
        fetcher: Optional[DefinitionFetcher] = None,
        translator: Optional[TextTranslator] = None,
        online: bool = True,
    ) -> None:
        cfg = self.config = config or Config()
        self.processor = processor or TextProcessor(
            extra_filler_words=cfg.text.extra_filler_words,
            min_word_length=cfg.text.min_word_length,
            extra_abbreviations=cfg.text.extra_abbreviations,
            skip_patterns=cfg.text.skip_patterns,
            strip_patterns=cfg.text.strip_patterns,
            drop_repeated_lines_min=cfg.text.drop_repeated_lines_min,
        )
        a = cfg.analysis
        self.analyzer = analyzer or TextAnalyzer(
            top_n=a.top_n, max_contexts=a.max_contexts,
            context_min_length=a.context_min_length,
            context_max_length=a.context_max_length, heading_form=a.heading_form,
            normalizer=make_normalizer(cfg.text.normalizer, cfg.text.language),
            max_phrase_words=a.max_phrase_words, min_phrase_count=a.min_phrase_count,
            phrase_cohesion=a.phrase_cohesion, phrase_boost=a.phrase_boost,
            generic_words=self.processor.generic_words,
        )
        d = cfg.document
        self.builder = builder or DocumentBuilder(
            title=d.title, include_definitions=d.include_definitions,
            include_context=d.include_context,
            include_translations=d.include_translations, bold_matches=d.bold_matches,
        )
        dc, tc = cfg.dictionary, cfg.translation
        self.fetcher = fetcher or DefinitionFetcher(
            api_url=dc.api_url, max_retries=dc.max_retries,
            max_definitions=dc.max_definitions, language=dc.language,
            timeout=dc.timeout_seconds, backoff=dc.retry_backoff_seconds,
        )
        self.translator = translator or TextTranslator(
            api_key=tc.resolve_api_key(), target_language=tc.target_language,
            source_language=tc.source_language, api_url=tc.api_url,
            max_retries=tc.max_retries, timeout=tc.timeout_seconds,
            backoff=tc.retry_backoff_seconds,
        )
        self.dictionary_enabled = dc.enabled and online
        self.translation_enabled = tc.enabled and online
        # Steps this run will actually perform (the UI's progress total).
        self.steps = [
            s for s in self.STEPS
            if not (s == "definitions" and not self.dictionary_enabled)
            and not (s == "translate" and not self.translation_enabled)
        ]
        self.cancel_event = threading.Event()
        self.file_name = ""
        self.terms: list[Term] = []
        self.last_analysis: Optional[AnalysisResult] = None

    # -- helpers -----------------------------------------------------------
    def cancel(self) -> None:
        """Ask a running job to stop at the next step."""
        self.cancel_event.set()

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise CancelledError("Cancelled.")

    def _report(self, on_progress: Optional[ProgressCallback], key: str) -> None:
        self._check_cancel()
        if on_progress:
            on_progress(self.steps.index(key) + 1, len(self.steps), STEP_LABELS[key])

    # -- UCD: Upload document ------------------------------------------------
    def validate(self, path: str | Path) -> bool:
        """True if the file can be processed; otherwise raises
        UnsupportedFileError with the reason (shown on the error screen)."""
        path = Path(path)
        if not path.is_file():
            raise UnsupportedFileError("The file could not be found.")
        get_extractor(path, self.config.files.allowed_extensions)
        limit = self.config.files.max_file_size_mb
        if path.stat().st_size > limit * 1024 * 1024:
            raise UnsupportedFileError(f"This file is too large (limit is {limit:g} MB).")
        return True

    def validate_files(self, paths: list[Path]) -> None:
        limit = self.config.files.max_files
        if len(paths) > limit:
            raise UnsupportedFileError(f"You can add up to {limit} documents at once.")
        for path in paths:
            self.validate(path)

    def describe_file(self, path: str | Path) -> dict:
        """What the "Ready to Process" list shows for one file. Raises the same
        errors as validate(), and also for unreadable / protected PDFs."""
        path = Path(path)
        self.validate(path)
        extractor = get_extractor(path, self.config.files.allowed_extensions)
        size = path.stat().st_size
        return {
            "name": path.name,
            "path": str(path),
            "format": extractor.format_name,
            "size_bytes": size,
            "size_mb": round(size / 1024 / 1024, 2),
            "pages": extractor.count_pages(path),
        }

    def handle_error(self, error: Exception) -> str:
        """Message the UI should show for an exception."""
        if isinstance(error, IlocoAdalError):
            return str(error)
        return "Something went wrong. Please try again."

    # -- phase 1: extract, clean, rank, contexts -----------------------------
    def analyze(
        self,
        input_paths: str | Path | list[str | Path],
        on_progress: Optional[ProgressCallback] = None,
    ) -> AnalysisResult:
        """One or several documents. Their sentences are pooled into one list,
        so the result is a single combined set of key terms. A document with no
        readable text is skipped (with a warning) as long as another one works."""
        single = isinstance(input_paths, (str, Path))
        paths = [Path(p) for p in ([input_paths] if single else input_paths)]
        if not paths:
            raise NoFilesError("Add a document first.")
        self.validate_files(paths)
        allowed = self.config.files.allowed_extensions

        self._report(on_progress, "read")                    # UCD: extract raw text
        texts: list[tuple[str, str]] = []
        skipped: list[tuple[str, TextExtractionError]] = []
        for path in paths:
            self._check_cancel()
            try:
                texts.append((path.name, get_extractor(path, allowed).extract_text(path)))
            except TextExtractionError as exc:
                skipped.append((path.name, exc))
        if not texts:
            raise skipped[0][1]

        self._report(on_progress, "clean")                   # UCD: preprocess
        sentences: list[str] = []
        for _, text in texts:                                # per document, so a
            sentences.extend(self.processor.split_sentences(text))  # sentence never spans two
        sentence_tokens = [self.processor.tokenize(s) for s in sentences]
        chunks = ([self.processor.tokenize_chunks(s) for s in sentences]
                  if self.analyzer.max_phrase_words >= 2 else None)

        self._report(on_progress, "rank")                    # UCD: rank terms
        ranked = self.analyzer.rank_terms(sentence_tokens, chunks)      # also finds phrases
        sentence_stems = self.analyzer.stem_sets(sentence_tokens, chunks)

        self._report(on_progress, "contexts")                # UCD: context sentences
        terms = self.analyzer.select_terms(ranked, sentences, sentence_stems)

        names = [name for name, _ in texts]
        analysis = AnalysisResult(
            ", ".join(names), sentences, sentence_tokens, sentence_stems, terms,
            source_names=names,
        )
        for name, exc in skipped:
            self._warn(analysis, "file_skipped", f'"{name}" was skipped: {exc}')
        self.file_name, self.terms, self.last_analysis = analysis.source_name, terms, analysis
        return analysis

    # -- Review key terms ------------------------------------------------------
    def add_term(self, analysis: AnalysisResult, word: str) -> Term:
        """For the 'Add a term' box. A word or a short phrase. An already-listed
        term is just re-ticked."""
        words = re.findall(r"[a-z]+(?:'[a-z]+)*", word.lower().replace("\u2019", "'"))
        if not words:
            raise TermNotFoundError(f'"{word.strip()}" was not found in the document.')
        normalizer = self.analyzer.normalizer
        key = " ".join(normalizer.key(w) for w in words)
        for existing in analysis.terms:
            if existing.stem == key:
                existing.selected = True
                return existing
        contexts = self.analyzer.find_context(
            key, analysis.sentences, analysis.sentence_stems, [" ".join(words)])
        if not contexts and len(words) > 1:          # a phrase that wasn't mined: search the text
            pattern = forms_pattern([" ".join(words)])
            hits = [s for s in analysis.sentences if pattern.search(s)]
            contexts = hits[: self.analyzer.max_contexts]
        if not contexts:
            raise TermNotFoundError(f'"{word.strip()}" was not found in the document.')
        if len(words) == 1:
            found = Counter(
                t for tokens in analysis.sentence_tokens for t in tokens if normalizer.key(t) == key
            )
            ordered = self.analyzer.order_forms(found)
            term = Term(word=ordered[0], stem=key, variants=ordered[1:], contexts=contexts)
        else:
            term = Term(word=" ".join(words), stem=key, contexts=contexts)
        analysis.terms.append(term)
        return term

    # -- phase 2: online steps (never fatal) ----------------------------------
    def enrich(
        self,
        analysis: AnalysisResult,
        on_progress: Optional[ProgressCallback] = None,
        strict: bool = False,
    ) -> None:
        """Fetch definitions, then translate. If a service can't be reached:
        strict=False adds a warning to analysis.warnings and skips the rest;
        strict=True raises ApiError so the caller can ask the user what to do.
        Work already done is kept, so calling enrich() again resumes."""
        if self.dictionary_enabled:                           # UCD: fetch definitions
            self._report(on_progress, "definitions")
            self._fetch_definitions(analysis, strict)
        if self.translation_enabled:                          # UCD: translate
            self._report(on_progress, "translate")
            self._translate(analysis, strict)

    def _warn(self, analysis: AnalysisResult, code: str, message: str) -> None:
        if not any(w.code == code for w in analysis.warnings):
            analysis.warnings.append(AnalysisWarning(code, message))

    def _lookup(self, term: Term) -> list[str]:
        forms = [term.word] + sorted(term.variants, key=len)[:1]  # e.g. plants, plant
        for form in forms:
            result = self.fetcher.get_definition(form)
            if result != [NOT_AVAILABLE]:
                return result
        return [NOT_AVAILABLE]

    DEFINITION_WORKERS = 6      # lookups running at the same time

    def _lookup_one(self, term: Term, stop: threading.Event):
        """Runs in a worker thread. Returns the error, or None if it worked."""
        if stop.is_set() or self.cancel_event.is_set():
            return None
        try:
            term.definitions = self._lookup(term)
        except ApiError as exc:
            stop.set()                      # no point trying the rest
            return exc
        return None

    def _fetch_definitions(self, analysis: AnalysisResult, strict: bool = False) -> None:
        todo = [t for t in analysis.selected_terms() if not t.definitions]
        if not todo:
            return
        self._check_cancel()
        stop = threading.Event()
        with ThreadPoolExecutor(max_workers=self.DEFINITION_WORKERS) as pool:
            errors = [e for e in pool.map(lambda t: self._lookup_one(t, stop), todo) if e]
        self._check_cancel()
        if errors:
            if strict:
                raise errors[0]
            self._warn(analysis, "no_internet",
                       "No internet connection. Definitions were left out.")

    def _translate(self, analysis: AnalysisResult, strict: bool = False) -> None:
        if not self.translator.is_configured:
            self._warn(analysis, "translation_not_configured",
                       "Translation isn't set up (no API key). Translations were left out.")
            return
        for term in analysis.selected_terms():
            self._check_cancel()
            if term.translated_contexts or term.translated_definitions:
                continue
            definitions = [d for d in term.definitions if d != NOT_AVAILABLE]
            texts = term.contexts + definitions
            if not texts:
                continue
            try:
                out = self.translator.translate_many(texts)
            except ApiError:
                if strict:
                    raise
                self._warn(analysis, "translation_unavailable",
                           "Translation was unavailable. Translations were left out.")
                return
            n = len(term.contexts)
            term.translated_contexts = out[:n]
            term.translated_definitions = out[n:]

    # -- phase 3: build the document ------------------------------------------
    def default_output_path(self, source_names: str | list[str]) -> Path:
        files = self.config.files
        names = [source_names] if isinstance(source_names, str) else list(source_names)
        folder = Path(files.output_dir) if files.output_dir else Path(".")
        folder.mkdir(parents=True, exist_ok=True)
        stem_name = Path(names[0]).with_suffix("").name if len(names) == 1 else files.combined_name
        base = stem_name + files.output_suffix
        path, n = folder / f"{base}.docx", 2
        while path.exists():                     # never overwrite an earlier result
            path, n = folder / f"{base}_{n}.docx", n + 1
        return path

    def build(
        self,
        analysis: AnalysisResult,
        output_path: str | Path | None = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Path:
        if output_path is None:
            output_path = self.default_output_path(analysis.source_names or analysis.source_name)
        self._report(on_progress, "build")
        self.builder.build_document(analysis.selected_terms(), analysis.source_name)
        return self.builder.export(output_path)

    def start_process(
        self,
        input_path: str | Path | list[str | Path],
        output_path: str | Path | None = None,
        on_progress: Optional[ProgressCallback] = None,
        review: Optional[ReviewCallback] = None,
    ) -> Path:
        analysis = self.analyze(input_path, on_progress)
        if review:
            review(analysis)  # user unticks / adds terms
        self.enrich(analysis, on_progress)
        return self.build(analysis, output_path, on_progress)
