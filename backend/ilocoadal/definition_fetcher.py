from __future__ import annotations

import re

from typing import Optional
from urllib.parse import quote

from .errors import ApiNotFoundError
from .http_utils import request_json
from .models import NOT_AVAILABLE

DEFAULT_API_URL = "https://api.dictionaryapi.dev/api/v2/entries"

_WORD = re.compile(r"[a-z]{4,}")
_SKIP = frozenset("that this with which from have used their them into such than also other some being".split())


def _bag(text: str) -> set[str]:
    """Word beginnings (5 letters), so thread / threads match."""
    return {w[:5] for w in _WORD.findall(text.lower()) if w not in _SKIP}

_IT = frozenset(
    "software computer computing program programming system data code network class "
    "function algorithm memory process thread module instance structure variable "
    "execution application database server client protocol".split()
)


def _it_hits(text: str) -> int:
    words = re.findall(r"[a-z]+", text.lower())
    return sum(1 for w in words if w in _IT or w[:-1] in _IT)

class DefinitionFetcher:
    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        max_retries: int = 3,
        max_definitions: int = 2,
        language: str = "en",
        timeout: float = 10.0,
        backoff: float = 1.0,
    ) -> None:
        self._cache: dict[str, list[str]] = {}
        self.api_url = api_url.rstrip("/")
        self.max_retries = max_retries
        self.max_definitions = max_definitions
        self.language = language
        self.timeout = timeout
        self.backoff = backoff

    def _request(self, url: str):
        return request_json(
            url, max_retries=self.max_retries, timeout=self.timeout, backoff=self.backoff
        )

    def get_definition(self, word: str, hint: str = "") -> list[str]:
        """Up to `max_definitions` definitions, best match with `hint` first.
        Returns [NOT_AVAILABLE] when the dictionary has no entry.
        Raises ApiUnavailableError when the service can't be reached."""
        key = word.strip().lower()
        if key not in self._cache:
            url = f"{self.api_url}/{quote(self.language)}/{quote(key)}"
            try:
                data = self._request(url)
            except ApiNotFoundError:
                self._cache[key] = [NOT_AVAILABLE]
                return [NOT_AVAILABLE]
            found: list[str] = []
            entries = data if isinstance(data, list) else []
            for entry in entries:
                for meaning in entry.get("meanings", []):
                    pos = meaning.get("partOfSpeech", "")
                    for item in meaning.get("definitions", []):
                        text = (item.get("definition") or "").strip()
                        if text:
                            found.append(f"({pos}) {text}" if pos else text)
            self._cache[key] = found or [NOT_AVAILABLE]
        senses = self._cache[key]
        if senses == [NOT_AVAILABLE]:
            return list(senses)
        if hint:
            own = _bag(key)                      # the term's own word proves nothing
            bag = _bag(hint) - own
            senses = sorted(
                senses,
                key=lambda s: -(len(bag & (_bag(s) - own)) + 2 * _it_hits(s)),
            )
        return senses[: self.max_definitions]
