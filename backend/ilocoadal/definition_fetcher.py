"""UCD: "Fetch definitions" (secondary actor: Free Dictionary API)."""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from .errors import ApiNotFoundError
from .http_utils import request_json
from .models import NOT_AVAILABLE

DEFAULT_API_URL = "https://api.dictionaryapi.dev/api/v2/entries"


class DefinitionFetcher:
    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        max_retries: int = 3,
        max_definitions: int = 3,
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

    def get_definition(self, word: str) -> list[str]:
        """Up to `max_definitions` definitions, e.g. "(noun) A living thing...".
        Returns [NOT_AVAILABLE] when the dictionary has no entry.
        Raises ApiUnavailableError when the service can't be reached."""
        key = word.strip().lower()
        if key in self._cache:
            return list(self._cache[key])
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
        result = found[: self.max_definitions] or [NOT_AVAILABLE]
        self._cache[key] = result
        return list(result)
