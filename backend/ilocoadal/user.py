"""The User box in the class diagram: what the UI layer holds and calls."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from .process_manager import ProcessManager, ProgressCallback, ReviewCallback


class User:
    def __init__(
        self,
        manager: Optional[ProcessManager] = None,
        display: Callable[[str], None] = print,
    ) -> None:
        self.manager = manager or ProcessManager()
        self.selected_files: list[Path] = []
        self.status_message = ""
        self.document_path: Optional[Path] = None
        self._display = display

    def upload_document(self, path: str | Path) -> bool:
        """Add a file to the list. Shows the error message and returns False if
        it can't be used (the list stays unchanged)."""
        try:
            info = self.manager.describe_file(path)
            if Path(path) in self.selected_files:
                self.show_message("That document is already added.")
                return False
            if len(self.selected_files) >= self.manager.config.files.max_files:
                self.show_message(
                    f"You can add up to {self.manager.config.files.max_files} documents at once.")
                return False
        except Exception as exc:
            self.show_message(self.manager.handle_error(exc))
            return False
        self.selected_files.append(Path(path))
        pages = f", {info['pages']} pages" if info["pages"] else ""
        self.show_message(f"Added: {info['name']} ({info['format']}, {info['size_mb']} MB{pages})")
        return True

    @property
    def selected_file(self) -> Optional[Path]:
        return self.selected_files[0] if self.selected_files else None

    def remove_document(self, path: str | Path) -> None:
        if Path(path) in self.selected_files:
            self.selected_files.remove(Path(path))

    def process_document(
        self,
        output_path: str | Path | None = None,
        on_progress: Optional[ProgressCallback] = None,
        review: Optional[ReviewCallback] = None,
    ) -> bool:
        if not self.selected_files:
            self.show_message("Please choose a document first.")
            return False
        try:
            self.document_path = self.manager.start_process(
                self.selected_files, output_path, on_progress, review
            )
        except Exception as exc:
            self.show_message(self.manager.handle_error(exc))
            return False
        analysis = self.manager.last_analysis
        for warning in (analysis.warnings if analysis else []):
            self.show_message(f"Warning: {warning.message}")
        self.show_message("Your document is ready.")
        return True

    def download_document(self, destination: str | Path | None = None) -> Optional[Path]:
        """Copy the finished document to `destination` (or just return its path)."""
        if self.document_path is None:
            self.show_message("There is no document to download yet.")
            return None
        if destination is None:
            return self.document_path
        return Path(shutil.copy(self.document_path, destination))

    def show_message(self, text: str) -> None:
        self.status_message = text
        self._display(text)
