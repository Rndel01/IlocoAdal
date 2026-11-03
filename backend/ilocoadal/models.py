from __future__ import annotations

from dataclasses import asdict, dataclass, field

NOT_AVAILABLE = "Definition not available"


@dataclass
class Term:
    """One key word and everything the system learns about it.

    word      the form shown in the document (see analysis.heading_form)
    stem      internal grouping key shared by merged forms (also the term's id)
    variants  the other forms found in the text, e.g. ["plants", "planted"]
    selected  the checkbox on the Review screen; unticked terms are skipped

    Filled by: TextAnalyzer (word, stem, variants, score, contexts),
    DefinitionFetcher (definitions), TextTranslator (translated_*).
    """

    word: str
    score: float = 0.0
    stem: str = ""
    variants: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    definitions: list[str] = field(default_factory=list)
    translated_definitions: list[str] = field(default_factory=list)
    translated_contexts: list[str] = field(default_factory=list)
    selected: bool = True

    @property
    def id(self) -> str:
        return self.stem or self.word.lower()

    def to_dict(self) -> dict:
        return {"id": self.id, **asdict(self)}


@dataclass
class AnalysisWarning:
    """A non-fatal problem. `code` is stable (no_internet,
    translation_not_configured, translation_unavailable)."""

    code: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisResult:
    """Everything produced before the document is built. Kept so the Review
    screen can add a term without re-reading the PDF."""

    source_name: str
    sentences: list[str]
    sentence_tokens: list[list[str]]
    sentence_stems: list[set[str]]
    terms: list[Term]
    warnings: list[AnalysisWarning] = field(default_factory=list)
    source_names: list[str] = field(default_factory=list)  # one per document

    def selected_terms(self) -> list[Term]:
        return [t for t in self.terms if t.selected]
