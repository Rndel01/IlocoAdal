"""UCD: output of the pipeline; "Download document" serves the exported file."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from .models import Term
from .textutil import forms_pattern

GREEN = RGBColor(0x1B, 0x5E, 0x3B)
LABEL_COLORS = {
    "Definition": RGBColor(0x2E, 0x7D, 0x32),             # leaf green
    "Context": RGBColor(0x7A, 0x8F, 0x1A),                # olive green
    "Translated definition": RGBColor(0x00, 0x79, 0x6B),  # teal green
    "Translated context": RGBColor(0x0B, 0x4F, 0x3A),     # deep forest green
}



def _apply_colors(doc) -> None:
    doc.styles["Normal"].font.size = Pt(10)
    doc.styles["List Bullet"].font.size = Pt(10)
    doc.styles["Heading 2"].font.size = Pt(15)

    """Recolor the title and headings, including the line under the title."""
    for name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        try:
            doc.styles[name].font.color.rgb = GREEN
        except KeyError:
            pass
    try:
        for edge in doc.styles["Title"].element.iter(qn("w:bottom")):
            edge.set(qn("w:color"), "1B5E3B")
            for attr in ("w:themeColor", "w:themeShade", "w:themeTint"):
                edge.attrib.pop(qn(attr), None)
    except KeyError:
        pass

class DocumentBuilder:
    """Writes the annotated document (.docx) in two steps:
        builder.build_document(terms, source_name)   # compose in memory
        builder.export(output_path)                  # save, returns the path

    Sections with no content are left out, so the document is complete even
    when definitions or translations are missing (e.g. no internet).
    """

    def __init__(
        self,
        title: str = "Key terms",
        include_definitions: bool = True,
        include_context: bool = True,
        include_translations: bool = True,
        bold_matches: bool = True,
    ) -> None:
        self.title = title
        self.include_definitions = include_definitions
        self.include_context = include_context
        self.include_translations = include_translations
        self.bold_matches = bold_matches
        self.terms: list[Term] = []
        self._doc: Optional[Document] = None

    def build_document(self, terms: list[Term], source_name: str) -> None:
        self.terms = list(terms)
        doc = Document()
        _apply_colors(doc)
        doc.add_heading(self.title, level=0)
        doc.add_paragraph(f"Source: {source_name}  |  {len(terms)} key terms")

        for rank, term in enumerate(terms, start=1):
            doc.add_heading(f"{rank}. {term.word}", level=2)
            if term.variants:
                doc.add_paragraph().add_run(
                    "Also appears as: " + ", ".join(term.variants)
                ).italic = True
            if self.include_definitions:
                self._section(doc, "Definition", term.definitions)
            if self.include_context:
                self._context(doc, term, self.bold_matches)
            if self.include_translations:
                self._section(doc, "Translated definition", term.translated_definitions)
                self._section(doc, "Translated context", term.translated_contexts)
        self._doc = doc

    def export(self, output_path: str | Path) -> Path:
        if self._doc is None:
            raise RuntimeError("Call build_document() before export().")
        output_path = Path(output_path)
        self._doc.save(str(output_path))
        return output_path

    @staticmethod
    def _section(doc, label: str, items: list[str]) -> None:
        if not items:
            return
        run = doc.add_paragraph().add_run(label)
        run.bold = True
        run.font.color.rgb = LABEL_COLORS[label]
        for item in items:
            doc.add_paragraph(item, style="List Bullet")

    @staticmethod
    def _context(doc, term: Term, bold: bool = True) -> None:
        if not term.contexts:
            return
        run = doc.add_paragraph().add_run("Context")
        run.bold = True
        run.font.color.rgb = LABEL_COLORS["Context"]
        pattern = forms_pattern([term.word, *term.variants])
        for sentence in term.contexts:
            para = doc.add_paragraph(style="List Bullet")
            if not bold:
                para.add_run(sentence)
                continue
            pos = 0
            for match in pattern.finditer(sentence):
                para.add_run(sentence[pos:match.start()])
                para.add_run(match.group()).bold = True
                pos = match.end()
            para.add_run(sentence[pos:])
