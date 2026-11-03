"""UCD: "Translate contexts and definition" (secondary actor: Google Translate API).

Uses the Cloud Translation v2 REST API, which needs an API key. Pass it in or
set the GOOGLE_TRANSLATE_API_KEY environment variable.
"""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote

from .errors import ApiUnavailableError
from .http_utils import request_json

DEFAULT_API_URL = "https://translation.googleapis.com/language/translate/v2"


class TextTranslator:
    def __init__(
        self,
        api_key: Optional[str] = None,
        target_language: str = "ilo",  # Ilocano
        source_language: str = "en",
        api_url: str = DEFAULT_API_URL,
        max_retries: int = 3,
        timeout: float = 10.0,
        backoff: float = 1.0,
        api_key_env: str = "GOOGLE_TRANSLATE_API_KEY",
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get(api_key_env, "")
        self.timeout = timeout
        self.backoff = backoff
        self.target_language = target_language
        self.source_language = source_language
        self.api_url = api_url
        self.max_retries = max_retries

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _request(self, url: str, data: dict):
        return request_json(
            url, data=data, max_retries=self.max_retries,
            timeout=self.timeout, backoff=self.backoff,
        )

    def translate_many(self, texts: list[str]) -> list[str]:
        """Translate several texts in one request (same order back)."""
        if not texts:
            return []
        if not self.is_configured:
            raise ApiUnavailableError("Translation isn't set up (no API key).")
        url = f"{self.api_url}?key={quote(self.api_key)}"
        data = {
            "q": texts,
            "source": self.source_language,
            "target": self.target_language,
            "format": "text",
        }
        response = self._request(url, data)
        try:
            out = [item["translatedText"] for item in response["data"]["translations"]]
        except (KeyError, TypeError) as exc:
            raise ApiUnavailableError("Unexpected reply from the translator.") from exc
        if len(out) != len(texts):
            raise ApiUnavailableError("Unexpected reply from the translator.")
        return out

    def translate_text(self, text: str) -> str:
        return self.translate_many([text])[0]
