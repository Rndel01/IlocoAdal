"""Small helpers shared by the analyzer and the document builder."""
from __future__ import annotations

import re
from typing import Iterable


def forms_pattern(forms: Iterable[str]) -> re.Pattern:
    """Regex matching any form of a term inside a sentence. Longest forms first,
    whole words only, and the words of a phrase may be separated by spaces or
    hyphens ("object oriented" matches "object-oriented")."""
    ordered = sorted({f for f in forms if f}, key=len, reverse=True)
    parts = [r"[\s\-]+".join(re.escape(w) for w in f.split(" ")) for f in ordered]
    return re.compile(r"\b(" + "|".join(parts) + r")\b", re.I)
