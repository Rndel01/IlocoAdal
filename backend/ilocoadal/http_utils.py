"""Shared HTTP helper with retries, used by the two API clients."""
from __future__ import annotations

import json
import time
from typing import Callable, Optional
from urllib import error, request
from urllib.parse import urlencode

from .errors import ApiNotFoundError, ApiUnavailableError


def request_json(
    url: str,
    *,
    data: Optional[dict] = None,
    max_retries: int = 3,
    timeout: float = 10,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
):
    """GET (or POST when `data` is given) and return parsed JSON.

    Retries up to `max_retries` times on network errors, timeouts, HTTP 429
    and 5xx. 404 raises ApiNotFoundError at once; other 4xx raise
    ApiUnavailableError at once (retrying would not help).
    """
    body = urlencode(data, doseq=True).encode() if data else None
    last: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            req = request.Request(url, data=body, headers={"Accept": "application/json"})
            with request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:  # must come before URLError / OSError
            if exc.code == 404:
                raise ApiNotFoundError("Nothing was found.") from exc
            if exc.code != 429 and exc.code < 500:
                raise ApiUnavailableError(
                    f"The service rejected the request ({exc.code})."
                ) from exc
            last = exc
        except (error.URLError, TimeoutError, OSError, ValueError) as exc:
            last = exc
        if attempt < max_retries - 1:
            sleep(backoff * 2**attempt)
    raise ApiUnavailableError("Couldn't reach the online service.") from last
