import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ilocoadal.config import Config
from ilocoadal.errors import ConfigError
from ilocoadal.normalizer import Lemmatizer, Normalizer, make_normalizer
from ilocoadal.process_manager import ProcessManager
from ilocoadal.text_analyzer import TextAnalyzer
from ilocoadal.text_processor import TextProcessor

TEXT = ("Mice eat seeds. A mouse hides in the grass. Many mice live in fields. "
        "The children watched the mouse. A child saw two mice.")


def terms_for(**analyzer_kwargs):
    p = TextProcessor()
    sents = p.split_sentences(TEXT)
    toks = [p.tokenize(s) for s in sents]
    return TextAnalyzer(top_n=10, **analyzer_kwargs).analyze_text(sents, toks)


class LemmatizerTests(unittest.TestCase):
    def setUp(self):
        self.lem = Lemmatizer("en")

    def test_irregular_forms_merge(self):
        for a, b in (("mice", "mouse"), ("children", "child"), ("studies", "study"),
                     ("bacteria", "bacterium"), ("ran", "run"), ("planted", "plant")):
            self.assertEqual(self.lem.key(a), self.lem.key(b), (a, b))

    def test_unrelated_words_stay_apart(self):
        self.assertNotEqual(self.lem.key("plant"), self.lem.key("plan"))
        self.assertEqual(self.lem.lemma("Photosynthesis"), "photosynthesis")

    def test_stemmer_mode_cannot_merge_irregulars(self):
        n = Normalizer()
        self.assertNotEqual(n.key("mice"), n.key("mouse"))
        self.assertIsNone(n.lemma("mice"))

    def test_analyzer_merges_with_lemmatizer_only(self):
        with_lem = {t.word: t for t in terms_for(normalizer=self.lem)}
        without = {t.word: t for t in terms_for()}
        mouse = next(t for t in with_lem.values() if "mouse" in {t.word, *t.variants})
        self.assertEqual({mouse.word, *mouse.variants}, {"mice", "mouse"})
        self.assertIn("mice", without)
        self.assertIn("mouse", without)       # separate terms without lemmatization

    def test_lemma_heading(self):
        mouse = next(t for t in terms_for(normalizer=self.lem, heading_form="lemma")
                     if "mice" in {t.word, *t.variants})
        self.assertEqual(mouse.word, "mouse")
        self.assertIn("mice", mouse.variants)


class WiringTests(unittest.TestCase):
    def test_config_chooses_normalizer(self):
        self.assertEqual(ProcessManager(Config()).analyzer.normalizer.name, "lemmatizer")
        cfg = Config.from_dict({"text": {"normalizer": "stemmer"}})
        self.assertEqual(ProcessManager(cfg).analyzer.normalizer.name, "stemmer")

    def test_lemma_heading_needs_lemmatizer(self):
        with self.assertRaises(ConfigError):
            Config.from_dict({"text": {"normalizer": "stemmer"},
                              "analysis": {"heading_form": "lemma"}})
        with self.assertRaises(ConfigError):
            Config.from_dict({"text": {"normalizer": "magic"}})

    def test_unsupported_language(self):
        with self.assertRaises(ConfigError):
            make_normalizer("lemmatizer", "xx-not-a-language")

    def test_missing_package_gives_clear_error(self):
        with patch.dict(sys.modules, {"simplemma": None}):
            with self.assertRaises(ConfigError) as cm:
                Lemmatizer("en")
        self.assertIn("simplemma", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
