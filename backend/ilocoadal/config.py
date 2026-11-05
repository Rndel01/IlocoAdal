"""All settings in one place. Load from a JSON file with Config.load(path).

Only the settings you write in the file are changed; everything else keeps
its default. Unknown names are rejected (so typos are caught), except keys
starting with "_" which are ignored and can be used for comments.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Optional

from .errors import ConfigError
from .text_processor import DEFAULT_SKIP_PATTERNS, DEFAULT_STRIP_PATTERNS


@dataclass
class FilesConfig:
    max_file_size_mb: float = 20.0    # per file (the Upload screen says 20MB)
    max_files: int = 10               # documents per job
    allowed_extensions: list[str] = field(default_factory=lambda: [".pdf"])
    output_dir: str = ""              # "" = current folder. On a phone, set this.
    output_suffix: str = "_key_terms"  # report.pdf -> report_key_terms.docx
    combined_name: str = "combined"   # base name when several documents are combined


@dataclass
class TextConfig:
    min_word_length: int = 3
    extra_filler_words: list[str] = field(default_factory=list)
    extra_abbreviations: list[str] = field(default_factory=list)  # e.g. ["inc.", "ltd."]
    normalizer: str = "lemmatizer"    # how word forms are merged: "lemmatizer" or "stemmer"
    language: str = "en"              # document language (used by the lemmatizer)
    # Slide text often has source lines and citations. A sentence matching a skip
    # pattern is dropped; text matching a strip pattern (URLs, emails) is removed.
    skip_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_SKIP_PATTERNS))
    strip_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_STRIP_PATTERNS))
    drop_repeated_lines_min: int = 3  # a short line repeated this often (page headers/footers) is ignored; 0 = off


@dataclass
class AnalysisConfig:
    top_n: int = 10
    max_contexts: int = 2
    context_min_length: int = 40      # preferred sentence length range
    context_max_length: int = 300
    heading_form: str = "most_common"  # or "shortest", or "lemma" (needs the lemmatizer)
    max_phrase_words: int = 3         # 1 = single words only; 2-3 also finds phrases like "use case"
    min_phrase_count: int = 2         # a phrase must appear at least this often
    phrase_cohesion: float = 0.15     # 0-1: how often one word is next to the other (higher = stricter)
    phrase_boost: float = 1.5         # >1 ranks phrases above single words (per extra word); 1 = no boost
    review_terms: bool = False        # pause for a Review screen (not in the current design)
    ask_when_offline: bool = True     # if the dictionary/translator can't be reached, pause and
                                      # let the user choose (Try again / Continue). False = continue
                                      # automatically and just add a warning


@dataclass
class DictionaryConfig:
    enabled: bool = True
    api_url: str = "https://api.dictionaryapi.dev/api/v2/entries"
    language: str = "en"
    max_retries: int = 3
    max_definitions: int = 2
    timeout_seconds: float = 10.0
    retry_backoff_seconds: float = 1.0


@dataclass
class TranslationConfig:
    enabled: bool = True
    api_url: str = "https://translation.googleapis.com/language/translate/v2"
    api_key: str = ""                 # or leave empty and use api_key_env
    api_key_env: str = "GOOGLE_TRANSLATE_API_KEY"
    source_language: str = "en"
    target_language: str = "ilo"      # Ilocano
    max_retries: int = 3
    timeout_seconds: float = 10.0
    retry_backoff_seconds: float = 1.0

    def resolve_api_key(self) -> str:
        return self.api_key or os.environ.get(self.api_key_env, "")


@dataclass
class DocumentConfig:
    title: str = "Key terms"
    include_definitions: bool = True
    include_context: bool = True
    include_translations: bool = True
    bold_matches: bool = True


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"           # keep local: the server is for the app only
    port: int = 8765                  # 0 = pick a free port (it is printed on start)
    auth_token: str = ""              # if set, requests need "Authorization: Bearer <token>"
    allow_origin: str = ""            # CORS origin, only needed for Flutter web in development
    job_ttl_minutes: float = 60.0     # how long finished jobs are remembered


_HEADING_FORMS = {"most_common", "shortest", "lemma"}
_NORMALIZERS = {"lemmatizer", "stemmer"}

# Options a single job may override (POST /jobs {"options": {...}}).
_JOB_OPTIONS = {
    "top_n": ("analysis", "top_n"),
    "review": ("analysis", "review_terms"),
    "ask_when_offline": ("analysis", "ask_when_offline"),
    "target_language": ("translation", "target_language"),
}


def _coerce(current, value, name: str):
    if isinstance(current, bool):
        ok = isinstance(value, bool)
    elif isinstance(current, int):
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif isinstance(current, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        value = float(value) if ok else value
    elif isinstance(current, str):
        ok = isinstance(value, str)
    elif isinstance(current, list):
        ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
    else:  # pragma: no cover
        ok = False
    if not ok:
        raise ConfigError(f"Setting '{name}' has the wrong type.")
    return value


def _apply(section, data, path: str) -> None:
    if not isinstance(data, dict):
        raise ConfigError(f"'{path.rstrip('.') or 'config'}' must be an object.")
    names = {f.name for f in fields(section)}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if key not in names:
            raise ConfigError(f"Unknown setting '{path}{key}'.")
        current = getattr(section, key)
        if is_dataclass(current):
            _apply(current, value, f"{path}{key}.")
        else:
            setattr(section, key, _coerce(current, value, f"{path}{key}"))


@dataclass
class Config:
    files: FilesConfig = field(default_factory=FilesConfig)
    text: TextConfig = field(default_factory=TextConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    dictionary: DictionaryConfig = field(default_factory=DictionaryConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    document: DocumentConfig = field(default_factory=DocumentConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    # -- loading ---------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        cfg = cls()
        _apply(cfg, data, "")
        cfg.validate()
        return cfg

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "Config":
        """Defaults, overridden by the JSON file at `path` (if given)."""
        if path is None:
            return cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {path}") from None
        except (OSError, ValueError) as exc:
            raise ConfigError(f"Can't read the config file: {exc}") from exc
        return cls.from_dict(data)

    # -- checks ----------------------------------------------------------
    def validate(self) -> None:
        def need(ok: bool, message: str) -> None:
            if not ok:
                raise ConfigError(message)

        f, t, a = self.files, self.text, self.analysis
        d, tr, s = self.dictionary, self.translation, self.server
        need(f.max_file_size_mb > 0, "files.max_file_size_mb must be above 0.")
        need(f.max_files >= 1, "files.max_files must be at least 1.")
        need(bool(f.allowed_extensions)
             and all(e.startswith(".") for e in f.allowed_extensions),
             "files.allowed_extensions must be a list like [\".pdf\"].")
        f.allowed_extensions = [e.lower() for e in f.allowed_extensions]
        need(t.min_word_length >= 1, "text.min_word_length must be at least 1.")
        need(t.normalizer in _NORMALIZERS,
             f"text.normalizer must be one of {sorted(_NORMALIZERS)}.")
        need(bool(t.language), "text.language can't be empty.")
        need(not (a.heading_form == "lemma" and t.normalizer != "lemmatizer"),
             'analysis.heading_form "lemma" needs text.normalizer "lemmatizer".')
        need(1 <= a.max_phrase_words <= 5, "analysis.max_phrase_words must be between 1 and 5.")
        need(a.min_phrase_count >= 1, "analysis.min_phrase_count must be at least 1.")
        need(0 < a.phrase_cohesion <= 1, "analysis.phrase_cohesion must be above 0 and at most 1.")
        need(a.phrase_boost > 0, "analysis.phrase_boost must be above 0.")
        need(t.drop_repeated_lines_min >= 0, "text.drop_repeated_lines_min can't be negative.")
        need(a.top_n >= 1, "analysis.top_n must be at least 1.")
        need(a.max_contexts >= 1, "analysis.max_contexts must be at least 1.")
        need(0 <= a.context_min_length <= a.context_max_length,
             "analysis.context_min_length must not exceed context_max_length.")
        need(a.heading_form in _HEADING_FORMS,
             f"analysis.heading_form must be one of {sorted(_HEADING_FORMS)}.")
        for name, sec in (("dictionary", d), ("translation", tr)):
            need(sec.max_retries >= 1, f"{name}.max_retries must be at least 1.")
            need(sec.timeout_seconds > 0, f"{name}.timeout_seconds must be above 0.")
            need(sec.retry_backoff_seconds >= 0, f"{name}.retry_backoff_seconds can't be negative.")
        need(d.max_definitions >= 1, "dictionary.max_definitions must be at least 1.")
        need(bool(d.language) and bool(tr.target_language) and bool(tr.source_language),
             "Language codes can't be empty.")
        need(0 <= s.port <= 65535, "server.port must be between 0 and 65535.")
        need(s.job_ttl_minutes > 0, "server.job_ttl_minutes must be above 0.")

    # -- output ----------------------------------------------------------
    def to_dict(self) -> dict:
        """Everything, including secrets (use to write a config file)."""
        return asdict(self)

    def public_dict(self) -> dict:
        """Safe to send to the app: secrets are replaced by flags."""
        data = asdict(self)
        data["translation"].pop("api_key")
        data["translation"]["api_key_configured"] = bool(self.translation.resolve_api_key())
        data["server"].pop("auth_token")
        data["server"]["auth_required"] = bool(self.server.auth_token)
        return data

    def with_overrides(self, options: dict) -> "Config":
        """A copy with per-job options applied. Allowed: top_n, review,
        target_language, online (False turns off dictionary + translation)."""
        if not isinstance(options, dict):
            raise ConfigError("'options' must be an object.")
        cfg = copy.deepcopy(self)
        for key, value in options.items():
            if key == "online":
                if not isinstance(value, bool):
                    raise ConfigError("Option 'online' must be true or false.")
                if not value:
                    cfg.dictionary.enabled = cfg.translation.enabled = False
            elif key in _JOB_OPTIONS:
                section, name = _JOB_OPTIONS[key]
                target = getattr(cfg, section)
                setattr(target, name, _coerce(getattr(target, name), value, key))
            else:
                raise ConfigError(f"Unknown option '{key}'.")
        cfg.validate()
        return cfg
