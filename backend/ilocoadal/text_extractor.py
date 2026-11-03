"""UCD: "Extract and preprocess raw text" (the extract half)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from .errors import TextExtractionError, UnsupportedFileError


class TextExtractor(ABC):
    """Reads the raw text out of a document. Add a subclass for each new
    format (for example DocxExtractor) and register it in EXTRACTORS."""

    format_name = "Document"   # shown on the "Ready to Process" screen

    @abstractmethod
    def extract_text(self, path: Path) -> str:
        ...

    def count_pages(self, path: Path) -> Optional[int]:
        """Page count, or None for formats without pages."""
        return None


class PDFExtractor(TextExtractor):
    format_name = "PDF"

    def _open(self, path: Path) -> PdfReader:
        try:
            reader = PdfReader(str(path))
        except Exception as exc:  # corrupted or not really a PDF
            raise TextExtractionError("Unable to read this document.") from exc

        if reader.is_encrypted:
            try:
                opened = reader.decrypt("")  # works only if no password is set
            except Exception:
                opened = 0
            if not opened:
                raise UnsupportedFileError(
                    "This PDF is password-protected. Please use an unlocked copy."
                )
        return reader

    def count_pages(self, path: Path) -> int:
        reader = self._open(path)
        try:
            return len(reader.pages)
        except Exception as exc:
            raise TextExtractionError("Unable to read this document.") from exc

    def extract_text(self, path: Path) -> str:
        reader = self._open(path)
        pages: list[str] = []
        try:
            for page in reader.pages:
                pages.append(page.extract_text() or "")
        except Exception as exc:
            raise TextExtractionError("Unable to read this document.") from exc

        text = "\n".join(pages).strip()
        if not text:
            raise TextExtractionError(
                "No readable text was found. Scanned pages and images "
                "aren't supported yet."
            )
        return text


EXTRACTORS: dict[str, TextExtractor] = {".pdf": PDFExtractor()}


def get_extractor(path: Path, allowed_extensions: list[str] | None = None) -> TextExtractor:
    """The extractor for this file type. `allowed_extensions` (from the config)
    can switch off formats that are registered in EXTRACTORS."""
    suffix = path.suffix.lower()
    usable = {
        ext: ex for ext, ex in EXTRACTORS.items()
        if allowed_extensions is None or ext in allowed_extensions
    }
    extractor = usable.get(suffix)
    if extractor is None:
        raise UnsupportedFileError(
            f"Only these file types are supported for now: {', '.join(sorted(usable))}"
        )
    return extractor
