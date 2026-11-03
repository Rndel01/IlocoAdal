"""UCD: "Extract and preprocess raw text" (the preprocess half)."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable

from .errors import ConfigError
from .stopwords import FILLER_WORDS, GENERIC_WORDS

# Words that end with a period but do not end a sentence.
_ABBREVIATIONS = {
    "e.g.", "i.e.", "etc.", "vs.", "dr.", "mr.", "mrs.", "ms.", "prof.",
    "fig.", "no.", "approx.", "al.", "st.",
}
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]*[A-Z0-9])")
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)*")
_GAP = re.compile(r"[\s\-\u2010-\u2014]*")   # what may separate two words of one phrase
_BULLET = re.compile(r"^\s*(?:[\u2022\u25cf\u25aa\u25e6\u2023\u25ab\u25a0\u25a1\u25cb\u25c6\u25ba\u25b6\-\u2013\u2014*]"
                     r"|\d{1,2}[.)]|[a-z][.)])\s+")
_LEADERS = re.compile(r"(?:\.\s*){4,}|(?:\u2026\s*){2,}")   # "....." in contents/index lines

# Text matching these is removed from a segment (it is noise, not content).
DEFAULT_STRIP_PATTERNS = [r"https?://\S+", r"\bwww\.\S+", r"\S+@\S+\.\S+"]
# A segment matching these is dropped entirely (citations and source lines).
DEFAULT_SKIP_PATTERNS = [
    r"^\s*(?:source|sources|reference|references|retrieved)\b",
    r"\(\d{4}[a-z]?\)",
]


def _compile(patterns: Iterable[str], what: str) -> list[re.Pattern]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p, re.I))
        except re.error as exc:
            raise ConfigError(f"{what}: '{p}' is not a valid pattern ({exc}).") from exc
    return out


class TextProcessor:
    """Prepares raw text for analysis.

    Original sentences are kept (they become the context sentences); only the
    tokens used for scoring are lowercased, stripped of punctuation and
    filtered of filler words.

    Sentences are found using the document's layout, not just punctuation:
    slides and lecture notes have bullets and short lines with no full stops,
    so a bullet, a heading line, or a line that ends early starts a new sentence.
    """

    def __init__(
        self,
        filler_words: Iterable[str] = FILLER_WORDS,
        extra_filler_words: Iterable[str] = (),
        min_word_length: int = 3,
        extra_abbreviations: Iterable[str] = (),
        generic_words: Iterable[str] = GENERIC_WORDS,
        skip_patterns: Iterable[str] = DEFAULT_SKIP_PATTERNS,
        strip_patterns: Iterable[str] = DEFAULT_STRIP_PATTERNS,
        drop_repeated_lines_min: int = 3,
    ) -> None:
        self.abbreviations = _ABBREVIATIONS | {a.lower() for a in extra_abbreviations}
        self.filler_words = frozenset(filler_words) | {
            w.lower() for w in extra_filler_words
        }
        self.generic_words = frozenset(generic_words)
        self._hard_fillers = self.filler_words - self.generic_words
        self.min_word_length = min_word_length
        self.skip_patterns = _compile(skip_patterns, "text.skip_patterns")
        self.strip_patterns = _compile(strip_patterns, "text.strip_patterns")
        self.drop_repeated_lines_min = drop_repeated_lines_min

    # -- layout-aware sentence splitting -------------------------------------------
    def normalize(self, raw_text: str) -> str:
        """Fix PDF line breaks: join hyphenated words, collapse whitespace."""
        text = unicodedata.normalize("NFKC", raw_text).replace("\u00ad", "")
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)    # re-join split words
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _lines(self, raw_text: str) -> list[str]:
        text = unicodedata.normalize("NFKC", raw_text).replace("\u00ad", "").replace("\r", "")
        text = re.sub(r"(\w)-[ \t]*\n[ \t]*(\w)", r"\1\2", text)   # photo-\nsynthesis
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
        lines = ["" if _LEADERS.search(ln) else ln for ln in lines]   # contents / index lines
        if self.drop_repeated_lines_min > 0:        # headers / footers repeated on every page
            repeated = {ln for ln, n in Counter(l for l in lines if l).items()
                        if n >= self.drop_repeated_lines_min and len(ln) <= 80}
            lines = [ln for ln in lines if ln not in repeated]
        return lines

    def _continues(self, prev: str, line: str, width: float) -> bool:
        """Does `line` continue the sentence that `prev` started?"""
        if prev.endswith((".", "!", "?", ":")):
            last = prev.split()[-1].lower()
            is_initial = len(last) == 2 and last[0].isalpha() and last.endswith(".")
            return last in self.abbreviations or is_initial     # "Dr.\\nSmith"
        if prev.endswith(","):
            return True
        if line[:1].islower():                                  # wrapped mid-sentence
            return True
        # A capital letter usually starts something new (slide titles, list items),
        # so only join when the previous line ran right up to the margin.
        return len(prev) >= 0.9 * width

    def _segments(self, raw_text: str) -> list[str]:
        lines = self._lines(raw_text)
        lengths = sorted(len(ln) for ln in lines if ln)
        # Typical full-line width. Never below 50: in a short document the longest
        # lines are not really "full", and joining them would glue unrelated lines.
        width = max(lengths[int(0.9 * (len(lengths) - 1))], 50) if lengths else 0
        segments: list[str] = []
        current: list[str] = []
        prev = None
        for ln in lines:
            if not ln:                                          # blank line = paragraph break
                if current:
                    segments.append(" ".join(current))
                    current = []
                prev = None
                continue
            bullet = _BULLET.match(ln)
            if bullet:
                ln = ln[bullet.end():]
                if not ln:
                    continue
            if prev is not None and not bullet and self._continues(prev, ln, width):
                current.append(ln)
            else:
                if current:
                    segments.append(" ".join(current))
                current = [ln]
            prev = ln
        if current:
            segments.append(" ".join(current))
        return segments

    def _clean_segment(self, segment: str) -> str | None:
        if any(p.search(segment) for p in self.skip_patterns):
            return None
        for p in self.strip_patterns:
            segment = p.sub(" ", segment)
        segment = re.sub(r"\s+", " ", segment).strip()
        return segment or None

    def split_sentences(self, raw_text: str) -> list[str]:
        sentences: list[str] = []
        for segment in self._segments(raw_text):
            cleaned = self._clean_segment(segment)
            if cleaned is None:
                continue
            pieces: list[str] = []
            for part in _SENTENCE_BREAK.split(cleaned):
                if pieces:
                    last_word = pieces[-1].split()[-1].lower()
                    is_initial = len(last_word) == 2 and last_word[0].isalpha() and last_word.endswith(".")
                    if last_word in self.abbreviations or is_initial:
                        pieces[-1] += " " + part
                        continue
                pieces.append(part)
            sentences.extend(p for p in pieces if p)
        return sentences

    # -- tokens --------------------------------------------------------------------------
    def tokenize(self, text: str) -> list[str]:
        """Lowercase, drop punctuation and numbers, filter filler words."""
        text = text.lower().replace("\u2019", "'")
        tokens: list[str] = []
        for word in _WORD.findall(text):
            if word in self.filler_words:
                continue
            word = word[:-2] if word.endswith("'s") else word  # plant's -> plant
            if len(word) >= self.min_word_length and word not in self.filler_words:
                tokens.append(word)
        return tokens

    def tokenize_chunks(self, text: str) -> list[list[str]]:
        """Runs of neighbouring words, for finding phrases like "use case".
        A chunk ends at punctuation, a number, a function word (of, the, and...)
        or a word that is too short. Generic words (use, many...) stay inside
        chunks so phrases containing them can be found."""
        text = text.lower().replace("\u2019", "'")
        chunks: list[list[str]] = []
        current: list[str] = []
        last_end = None
        for m in _WORD.finditer(text):
            word = m.group()
            if current and (last_end is None or not _GAP.fullmatch(text[last_end:m.start()])):
                chunks.append(current)
                current = []
            last_end = m.end()
            if word in self._hard_fillers:
                if current:
                    chunks.append(current)
                    current = []
                continue
            word = word[:-2] if word.endswith("'s") else word
            if len(word) < self.min_word_length or word in self._hard_fillers:
                if current:
                    chunks.append(current)
                    current = []
                continue
            current.append(word)
        if current:
            chunks.append(current)
        return chunks

    def clean_text(self, text: str) -> str:
        return " ".join(self.tokenize(text))
