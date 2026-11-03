"""Regression tests for slide-style documents (bullets, short lines, source lines)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document

from ilocoadal.config import Config
from ilocoadal.document_builder import DocumentBuilder
from ilocoadal.errors import ConfigError
from ilocoadal.models import AnalysisResult, Term
from ilocoadal.normalizer import make_normalizer
from ilocoadal.process_manager import ProcessManager
from ilocoadal.stopwords import FILLER_WORDS, GENERIC_WORDS
from ilocoadal.text_analyzer import TextAnalyzer
from ilocoadal.text_processor import TextProcessor
from ilocoadal.textutil import forms_pattern

SLIDES = """Use Case Diagram
• models the behavior (context) of a system
• captures the requirements of a system
• describes in high-level the scope of the
system
Elements of Use Case Diagram
1.  sequential,
2.  concurrent, and
Source: https://www.example.com/guide/uml-
modeling/behavior/
Schach, Stephen R. (2004). An Introduction to object-oriented design. NY: The McGraw-Hill Companies
Notation:
Package:
Dependency:
"""


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.p = TextProcessor()

    def test_bullets_and_headings_become_separate_sentences(self):
        s = self.p.split_sentences(SLIDES)
        self.assertIn("Use Case Diagram", s)
        self.assertIn("models the behavior (context) of a system", s)
        self.assertIn("captures the requirements of a system", s)
        self.assertLess(max(len(x) for x in s), 100)       # nothing glued together

    def test_wrapped_bullet_is_rejoined(self):
        s = self.p.split_sentences(SLIDES)
        self.assertIn("describes in high-level the scope of the system", s)

    def test_source_lines_and_citations_are_dropped(self):
        joined = " ".join(self.p.split_sentences(SLIDES)).lower()
        for noise in ("example.com", "mcgraw", "schach", "source"):
            self.assertNotIn(noise, joined)

    def test_urls_inside_text_are_stripped_not_the_sentence(self):
        s = self.p.split_sentences("Plants make food, see https://x.org/a for more. Light matters.")
        self.assertEqual(s[0], "Plants make food, see for more.")

    def test_prose_wrapped_lines_still_work(self):
        prose = ("Photosynthesis is the process plants use to make food and it takes place in the\n"
                 "chloroplasts of plant cells. Chlorophyll is the green pigment that absorbs\n"
                 "sunlight and gives leaves their colour.\n")
        s = self.p.split_sentences(prose)
        self.assertEqual(len(s), 2)
        self.assertTrue(s[0].endswith("plant cells."))

    def test_abbreviation_at_line_end_does_not_split(self):
        s = self.p.split_sentences("We asked Dr.\nSmith about the results of the experiment yesterday.")
        self.assertEqual(len(s), 1)

    def test_repeated_footer_lines_are_ignored(self):
        text = "\n".join(f"Chlorophyll absorbs light on page {i}.\nMMSU Footer\n" for i in range(4))
        self.assertNotIn("footer", " ".join(self.p.split_sentences(text)).lower())
        keep = TextProcessor(drop_repeated_lines_min=0)
        self.assertIn("MMSU Footer", keep.split_sentences(text))

    def test_custom_patterns_and_bad_patterns(self):
        p = TextProcessor(skip_patterns=[r"^confidential"], strip_patterns=[])
        self.assertEqual(p.split_sentences("Confidential draft\n\nPlants need light."), ["Plants need light."])
        with self.assertRaises(ConfigError):
            TextProcessor(skip_patterns=["(unclosed"])

    def test_chunks_break_at_function_words_punctuation_and_numbers(self):
        self.assertEqual(self.p.tokenize_chunks("The use case diagram of object-oriented design 2 now"),
                         [["use", "case", "diagram"], ["object", "oriented", "design"], ["now"]])
        self.assertEqual(self.p.tokenize_chunks("Use Case 1, Use Case 2"), [["use", "case"], ["use", "case"]])

    def test_generic_words_are_kept_in_chunks_but_not_tokens(self):
        self.assertNotIn("use", self.p.tokenize("use case"))
        self.assertIn("use", self.p.tokenize_chunks("use case")[0])
        self.assertTrue(GENERIC_WORDS <= FILLER_WORDS)


def analyze(text, **kw):
    p = TextProcessor()
    sents = p.split_sentences(text)
    toks = [p.tokenize(s) for s in sents]
    chunks = [p.tokenize_chunks(s) for s in sents]
    an = TextAnalyzer(top_n=kw.pop("top_n", 20), generic_words=p.generic_words,
                      max_phrase_words=kw.pop("max_phrase_words", 3), **kw)
    ranked = an.rank_terms(toks, chunks)
    stems = an.stem_sets(toks, chunks)
    return an, an.select_terms(ranked, sents, stems), sents


PHRASES = """Describes the steps performed in a use case.
Improve any process by clarifying use cases.
A use case diagram shows actors.
Every use case diagram has a boundary.
Many students read the notes.
Many people like the results.
Some students passed.
"""


class PhraseTests(unittest.TestCase):
    def test_phrase_is_one_term_and_its_words_are_not_double_counted(self):
        _, terms, _ = analyze(PHRASES)
        words = {t.word for t in terms}
        self.assertIn("use case diagram", words)
        self.assertIn("use case", words)           # still seen on its own, twice
        by = {t.word: t for t in terms}
        self.assertEqual(set(by["use case"].variants), {"use cases"})
        self.assertNotIn("diagram", words)          # only ever inside "use case diagram"

    def test_generic_word_needs_to_belong_to_the_phrase(self):
        _, terms, _ = analyze(PHRASES)
        self.assertNotIn("many students", {t.word for t in terms})   # "many" is everywhere

    def test_single_word_mode_matches_old_behaviour(self):
        _, terms, _ = analyze(PHRASES, max_phrase_words=1)
        self.assertTrue(all(" " not in t.word for t in terms))

    def test_phrase_boost_ranks_phrases_higher(self):
        _, plain, _ = analyze(PHRASES, phrase_boost=1.0)
        _, boosted, _ = analyze(PHRASES, phrase_boost=3.0)
        rank = lambda ts: [t.word for t in ts].index("use case diagram")
        self.assertLessEqual(rank(boosted), rank(plain))

    def test_phrase_gets_context_sentences_containing_it(self):
        _, terms, _ = analyze(PHRASES)
        t = next(t for t in terms if t.word == "use case diagram")
        self.assertTrue(t.contexts)
        self.assertTrue(all("use case diagram" in c.lower() for c in t.contexts))

    def test_hyphenated_and_wrapped_phrases_match_for_bolding(self):
        pat = forms_pattern(["object oriented"])
        self.assertTrue(pat.search("An object-oriented design"))
        self.assertTrue(pat.search("An object oriented design"))
        self.assertFalse(pat.search("An objects oriented design"))

    def test_lemma_heading_for_phrases(self):
        an = TextAnalyzer(heading_form="lemma", normalizer=make_normalizer("lemmatizer"))
        from collections import Counter
        self.assertEqual(an.order_forms(Counter({"use cases": 3}))[0], "use case")


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.an = TextAnalyzer(context_min_length=40, context_max_length=120, max_contexts=2)

    def test_same_sentence_is_listed_once(self):
        sents = ["An actor starts the process of the system today."] * 3 + ["Another actor stops the process."]
        stems = [{"actor"}] * 4
        ctx = self.an.find_context("actor", sents, stems)
        self.assertEqual(len(ctx), 2)
        self.assertNotEqual(ctx[0], ctx[1])

    def test_readable_lengths_first_then_closest_to_range(self):
        sents = ["Actor.", "An actor is a role played by a user of the system under design.",
                 "x " * 200 + "actor"]
        stems = [{"actor"}] * 3
        ctx = self.an.find_context("actor", sents, stems)
        self.assertEqual(ctx[0], sents[1])
        self.assertEqual(ctx[1], "Actor.")        # short is nearer to the range than a 400-char one

    def test_long_sentence_is_cut_around_the_term(self):
        sent = ("filler " * 60) + "The actor does something important here " + ("more " * 60)
        out = self.an.find_context("actor", [sent], [{"actor"}], ["actor"])[0]
        self.assertLessEqual(len(out), 120 + 4)
        self.assertIn("actor", out)
        self.assertTrue(out.startswith("…") and out.endswith("…"))


class EndToEndSlides(unittest.TestCase):
    def test_slide_deck_gives_short_readable_contexts_and_no_url_junk(self):
        with tempfile.TemporaryDirectory() as d:
            from test_api import make_pdf
            lines = ["Use Case Diagram", "- models the behavior of a system",
                     "- captures the requirements of a system", "Elements of Use Case Diagram",
                     "Use Case Name - process of the system", "Actor - role of the user",
                     "Source: https://www.lucidchart.com/pages/uml-diagram",
                     "Every use case has an actor", "An actor starts a use case"]
            pdf = make_pdf(Path(d) / "slides.pdf", lines)
            a = ProcessManager(Config(), online=False).analyze(pdf)
        self.assertLess(max(len(s) for s in a.sentences), 100)
        words = {t.word for t in a.terms}
        self.assertNotIn("com", words)
        self.assertNotIn("lucidchart", words)
        self.assertTrue(any(" " in w for w in words))              # found a phrase
        for t in a.terms:
            for c in t.contexts:
                self.assertLessEqual(len(c), 300)

    def test_add_term_accepts_a_phrase_and_reports_missing_ones(self):
        with tempfile.TemporaryDirectory() as d:
            from test_api import make_pdf
            pdf = make_pdf(Path(d) / "a.pdf", ["The use case diagram is drawn first.", "Actors use the diagram daily."])
            m = ProcessManager(Config(), online=False)
            a = m.analyze(pdf)
            t = m.add_term(a, "Use Case Diagram")
            self.assertEqual(t.word, "use case diagram")
            self.assertTrue(t.contexts)
            from ilocoadal.errors import TermNotFoundError
            with self.assertRaises(TermNotFoundError):
                m.add_term(a, "zebra crossing")


class BuilderAndConfig(unittest.TestCase):
    def test_builder_bolds_a_phrase(self):
        term = Term("use case", 0.5, "use cas", ["use cases"], ["Each use case has an actor."])
        b = DocumentBuilder()
        b.build_document([term], "x.pdf")
        with tempfile.TemporaryDirectory() as d:
            out = b.export(Path(d) / "o.docx")
            runs = [r.text for p in Document(str(out)).paragraphs for r in p.runs if r.bold]
        self.assertIn("use case", runs)

    def test_new_settings_validate(self):
        for bad in ({"analysis": {"max_phrase_words": 0}}, {"analysis": {"max_phrase_words": 9}},
                    {"analysis": {"phrase_cohesion": 0}}, {"analysis": {"phrase_cohesion": 1.5}},
                    {"analysis": {"phrase_boost": 0}}, {"text": {"skip_patterns": ["(oops"]}},
                    {"text": {"drop_repeated_lines_min": -1}}):
            with self.assertRaises(ConfigError, msg=bad):
                ProcessManager(Config.from_dict(bad))
        m = ProcessManager(Config.from_dict({"analysis": {"max_phrase_words": 1}}))
        self.assertEqual(m.analyzer.max_phrase_words, 1)


if __name__ == "__main__":
    unittest.main()
