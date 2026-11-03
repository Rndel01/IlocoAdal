import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document

from ilocoadal.definition_fetcher import DefinitionFetcher
from ilocoadal.document_builder import DocumentBuilder
from ilocoadal.errors import (ApiNotFoundError, ApiUnavailableError,
                              NoKeyTermsError, UnsupportedFileError)
from ilocoadal.http_utils import request_json
from ilocoadal.models import NOT_AVAILABLE, AnalysisResult, Term
from ilocoadal.process_manager import ProcessManager
from ilocoadal.stemmer import stem
from ilocoadal.text_analyzer import TextAnalyzer
from ilocoadal.text_processor import TextProcessor
from ilocoadal.text_translator import TextTranslator
from ilocoadal.user import User

SAMPLE = (
    "Photosynthesis is the process plants use to make food. "
    "Photosynthesis takes place in the chloroplasts of plant cells. "
    "Chlorophyll is the green pigment that absorbs sunlight. "
    "Dr. Smith studied chlorophyll in the lab. "
    "Stomata open and close to control gas exchange."
)


def build_builder_doc(terms):
    b = DocumentBuilder()
    b.build_document(terms, "x.pdf")
    with tempfile.TemporaryDirectory() as d:
        out = b.export(Path(d) / "o.docx")
        return Document(str(out)).paragraphs


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.p = TextProcessor()

    def test_tokenize_lowercases_and_filters(self):
        self.assertEqual(self.p.tokenize("The Plant's Cells, and 42!"), ["plant", "cells"])

    def test_clean_text(self):
        self.assertEqual(self.p.clean_text("The sun is BRIGHT."), "sun bright")

    def test_sentences_keep_original_wording_and_abbreviations(self):
        sents = self.p.split_sentences(SAMPLE)
        self.assertEqual(len(sents), 5)
        self.assertTrue(sents[3].startswith("Dr. Smith"))

    def test_joins_hyphenated_line_breaks(self):
        self.assertEqual(self.p.normalize("photo-\nsynthesis works"), "photosynthesis works")


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.p = TextProcessor()
        self.sents = self.p.split_sentences(SAMPLE)
        self.toks = [self.p.tokenize(s) for s in self.sents]

    def test_ranking_is_sorted_and_repeated_words_win(self):
        terms = TextAnalyzer().rank_terms(self.toks)
        scores = [t.score for t in terms]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertIn(terms[0].word, {"photosynthesis", "chlorophyll"})

    def test_top_n_and_contexts(self):
        terms = TextAnalyzer(top_n=3).analyze_text(self.sents, self.toks)
        self.assertEqual(len(terms), 3)
        for t in terms:
            self.assertTrue(t.contexts)
            self.assertTrue(all(c in self.sents for c in t.contexts))

    def test_empty_text_raises(self):
        with self.assertRaises(NoKeyTermsError):
            TextAnalyzer().rank_terms([[], []])


class StemmerTests(unittest.TestCase):
    def test_forms_merge(self):
        for group in (["plant", "plants", "planted", "planting"],
                      ["study", "studies", "studied"],
                      ["process", "processes", "processed"],
                      ["make", "making"], ["run", "running"], ["cell", "cells"]):
            self.assertEqual(len({stem(w) for w in group}), 1, group)

    def test_unrelated_words_stay_apart(self):
        self.assertNotEqual(stem("plant"), stem("plan"))
        self.assertEqual(stem("photosynthesis"), "photosynthesis")
        self.assertEqual(stem("gas"), "gas")


class MergingTests(unittest.TestCase):
    TEXT = ("Plants need light. A plant grows toward light. "
            "The planted seeds grew into healthy plants. Light drives growth.")

    def test_merged_term_shows_common_form_and_variants(self):
        p = TextProcessor()
        sents = p.split_sentences(self.TEXT)
        toks = [p.tokenize(s) for s in sents]
        terms = TextAnalyzer(top_n=5).analyze_text(sents, toks)
        plant = next(t for t in terms if t.stem == stem("plant"))
        self.assertEqual({plant.word, *plant.variants}, {"plant", "plants", "planted"})
        self.assertEqual(len(plant.contexts), 2)

    def test_builder_bolds_every_form_and_lists_variants(self):
        term = Term("plant", 0.5, "plant", ["plants"], ["Plants need light and a plant grows."])
        paras = build_builder_doc([term])
        self.assertTrue(any(p.text == "Also appears as: plants" for p in paras))
        bold = [r.text for p in paras for r in p.runs if r.bold and r.text in {"Plants", "plant"}]
        self.assertEqual(sorted(bold), ["Plants", "plant"])


class BuilderTests(unittest.TestCase):
    def test_skips_empty_sections(self):
        paras = build_builder_doc([Term("stomata", 0.3, contexts=["Stomata open."])])
        text = "\n".join(p.text for p in paras)
        self.assertIn("1. stomata", text)
        self.assertIn("Context", text)
        self.assertNotIn("Definition", text)

    def test_export_before_build_fails(self):
        with self.assertRaises(RuntimeError):
            DocumentBuilder().export("x.docx")


class DefinitionFetcherTests(unittest.TestCase):
    DATA = [{"meanings": [{"partOfSpeech": "noun", "definitions": [
        {"definition": "A living organism."}, {"definition": "A factory."},
        {"definition": "To place in soil."}, {"definition": "Fourth one."}]}]}]

    def test_parses_and_limits_definitions(self):
        f = DefinitionFetcher(max_definitions=3)
        with patch.object(f, "_request", return_value=self.DATA):
            out = f.get_definition("Plant")
        self.assertEqual(out[0], "(noun) A living organism.")
        self.assertEqual(len(out), 3)

    def test_not_found_is_not_available(self):
        f = DefinitionFetcher()
        with patch.object(f, "_request", side_effect=ApiNotFoundError("x")):
            self.assertEqual(f.get_definition("zzzq"), [NOT_AVAILABLE])

    def test_unreachable_raises(self):
        f = DefinitionFetcher()
        with patch.object(f, "_request", side_effect=ApiUnavailableError("x")):
            with self.assertRaises(ApiUnavailableError):
                f.get_definition("plant")


class TranslatorTests(unittest.TestCase):
    def test_translates_in_order(self):
        t = TextTranslator(api_key="k")
        reply = {"data": {"translations": [{"translatedText": "A"}, {"translatedText": "B"}]}}
        with patch.object(t, "_request", return_value=reply):
            self.assertEqual(t.translate_many(["x", "y"]), ["A", "B"])

    def test_missing_key_raises(self):
        with self.assertRaises(ApiUnavailableError):
            TextTranslator(api_key="").translate_many(["x"])

    def test_bad_reply_raises(self):
        t = TextTranslator(api_key="k")
        with patch.object(t, "_request", return_value={"oops": 1}):
            with self.assertRaises(ApiUnavailableError):
                t.translate_many(["x"])


class RetryTests(unittest.TestCase):
    def test_retries_then_gives_up(self):
        calls = []
        with patch("ilocoadal.http_utils.request.urlopen",
                   side_effect=lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(OSError("down"))):
            with self.assertRaises(ApiUnavailableError):
                request_json("http://x", max_retries=3, sleep=lambda s: None)
        self.assertEqual(len(calls), 3)


class ManagerEnrichTests(unittest.TestCase):
    def make_analysis(self):
        return AnalysisResult("x.pdf", [], [], [], [
            Term("plants", 0.5, "plant", ["plant"], ["Plants need light."]),
            Term("stomata", 0.4, "stomata", [], ["Stomata open."]),
        ])

    def make_manager(self):
        m = ProcessManager(translator=TextTranslator(api_key="k"))
        return m

    def test_full_enrich(self):
        m = self.make_manager()
        a = self.make_analysis()

        def define(word):
            return [NOT_AVAILABLE] if word == "plants" else ["(noun) A plant."] if word == "plant" else [NOT_AVAILABLE]
        with patch.object(m.fetcher, "get_definition", side_effect=define), \
             patch.object(m.translator, "translate_many",
                          side_effect=lambda texts: [f"T:{t}" for t in texts]):
            m.enrich(a)
        plants, stomata = a.terms
        self.assertEqual(plants.definitions, ["(noun) A plant."])   # fell back to variant
        self.assertEqual(stomata.definitions, [NOT_AVAILABLE])
        self.assertEqual(plants.translated_contexts, ["T:Plants need light."])
        self.assertEqual(plants.translated_definitions, ["T:(noun) A plant."])
        self.assertEqual(stomata.translated_definitions, [])        # not-available skipped
        self.assertEqual(a.warnings, [])

    def test_no_internet_continues_with_warning(self):
        m = self.make_manager()
        a = self.make_analysis()
        with patch.object(m.fetcher, "get_definition", side_effect=ApiUnavailableError("x")) as g, \
             patch.object(m.translator, "translate_many", side_effect=ApiUnavailableError("x")) as t:
            m.enrich(a)
        self.assertEqual(g.call_count, 1)    # stops after the first failure
        self.assertEqual(t.call_count, 1)
        self.assertEqual(len(a.warnings), 2)
        self.assertTrue(all(not x.definitions and not x.translated_contexts for x in a.terms))

    def test_missing_key_warns_once(self):
        m = ProcessManager(translator=TextTranslator(api_key=""))
        a = self.make_analysis()
        with patch.object(m.fetcher, "get_definition", return_value=["d"]):
            m.enrich(a)
        self.assertEqual(len(a.warnings), 1)
        self.assertIn("API key", a.warnings[0].message)
        self.assertEqual(a.warnings[0].code, "translation_not_configured")

    def test_offline_mode_skips_api_steps(self):
        m = ProcessManager(online=False)
        a = self.make_analysis()
        with patch.object(m.fetcher, "get_definition") as g:
            m.enrich(a)
        g.assert_not_called()


class EndToEndTests(unittest.TestCase):
    def test_unsupported_type(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "notes.txt"
            f.write_text("hello")
            with self.assertRaises(UnsupportedFileError):
                ProcessManager().validate(f)

    def test_user_reports_error_message(self):
        msgs = []
        u = User(ProcessManager(), display=msgs.append)
        self.assertFalse(u.upload_document("missing.pdf"))
        self.assertEqual(msgs[-1], "The file could not be found.")
        self.assertFalse(u.process_document())

    def test_handle_error_hides_unexpected_details(self):
        self.assertEqual(ProcessManager().handle_error(KeyError("secret")),
                         "Something went wrong. Please try again.")


if __name__ == "__main__":
    unittest.main()
