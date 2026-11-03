"""Groups word forms together (plant / plants / planted -> one term).

Two modes, chosen with `text.normalizer` in the config:

  stemmer     the small rule-based stemmer in stemmer.py. No dependencies,
              but misses irregular forms (mice, children).
  lemmatizer  dictionary-based lemmatization (simplemma, pure Python, works
              offline), followed by the stemmer as a safety net so words the
              dictionary doesn't know still merge (chloroplast / chloroplasts).

`key()` is the internal grouping key. `lemma()` is a real dictionary form
(or None in stemmer mode) and can be shown as the heading.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .errors import ConfigError
from .stemmer import stem


class Normalizer:
    name = "stemmer"

    def key(self, word: str) -> str:
        return stem(word)

    def lemma(self, word: str) -> Optional[str]:
        return None


class Lemmatizer(Normalizer):
    name = "lemmatizer"

    def __init__(self, language: str = "en") -> None:
        try:
            import simplemma
        except ImportError as exc:
            raise ConfigError(
                "Lemmatization needs the 'simplemma' package "
                "(pip install simplemma), or set text.normalizer to \"stemmer\"."
            ) from exc
        try:
            simplemma.lemmatize("test", lang=language)
        except ValueError as exc:
            raise ConfigError(f"Lemmatization doesn't support language '{language}'.") from exc
        self._lemmatize = lru_cache(maxsize=50_000)(
            lambda word: simplemma.lemmatize(word, lang=language).lower()
        )

    def lemma(self, word: str) -> str:
        return self._lemmatize(word.lower())

    def key(self, word: str) -> str:
        # The dictionary isn't always consistent: it maps bacteria -> bacterium
        # but bacterium -> bacteria. Taking the smaller of one and two lemma
        # steps gives both words the same key.
        first = self.lemma(word)
        return stem(min(first, self.lemma(first)), min_e_len=4)


def make_normalizer(kind: str = "stemmer", language: str = "en") -> Normalizer:
    if kind == "lemmatizer":
        return Lemmatizer(language)
    return Normalizer()
