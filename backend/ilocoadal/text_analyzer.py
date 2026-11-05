"""UCD: "Rank terms (TF-IDF)" and "Extract context sentences"."""
from __future__ import annotations

import re
import math
from collections import Counter, defaultdict
from typing import Iterable, Optional

from .errors import NoKeyTermsError
from .models import Term
from .normalizer import Normalizer
from .textutil import forms_pattern

_NO_TERMS = "This document doesn't have enough text to find key terms."
_DEFINES = re.compile(r"\b(?:is called|are called|we call|is defined as|is said to be|denoted by|is an?)\b", re.I)


def _noisy(s: str) -> bool:
    """Contents lines, spaced-out letters ("S e t s"), symbol soup."""
    if sum(c.isalpha() for c in s) < 0.65 * len(s):
        return True
    words = s.split()
    return len(words) >= 6 and sum(len(w) == 1 for w in words) > 0.4 * len(words)

_CODE = re.compile(r"[a-z]{2,}_[a-z]{2,}|/\*|\*/|\);|\)\s*\{|\bvoid\s+\*?\w+\(")


def _is_code(s: str) -> bool:
    return bool(_CODE.search(s))

_STEREO = re.compile(r"<<|>>|«|»")


def _is_sentence(s: str) -> bool:
    """Slide labels like "Track Order" or "<<access>>" are not sentences."""
    words = s.split()
    if len(words) < 5 or _STEREO.search(s):
        return False
    lead = [w for w in words if w[0].isalpha()]
    if len(lead) >= 3 and sum(w[0].isupper() for w in lead) > 0.6 * len(lead):
        return False   # Title Case heading
    return s.rstrip()[-1] in ".!?:;" or len(words) >= 8

class TextAnalyzer:
    """Ranks terms with TF-IDF and finds the sentences they appear in.

    Word forms are merged first (plant / plants / planted -> one term).
    A single document has no corpus, so each sentence is treated as a small
    "document" when computing IDF.

    Phrases: with max_phrase_words > 1, words that keep appearing side by side
    ("use case", "activity diagram") are treated as one term. A pair is kept if
    it occurs at least `min_phrase_count` times and one of its words is mostly
    seen next to the other (cohesion, 0-1). Inside a phrase, its words are not
    counted again as separate terms.
    """

    def __init__(
        self,
        top_n: int = 10,
        max_contexts: int = 2,
        context_min_length: int = 40,
        context_max_length: int = 300,
        heading_form: str = "most_common",  # "shortest" or "lemma" also possible
        normalizer: Normalizer | None = None,
        max_phrase_words: int = 1,
        min_phrase_count: int = 2,
        phrase_cohesion: float = 0.15,
        phrase_boost: float = 1.0,
        generic_words: Iterable[str] = (),
    ) -> None:
        self.normalizer = normalizer or Normalizer()  # default: the simple stemmer
        self.top_n = top_n
        self.max_contexts = max_contexts
        self.context_min_length = context_min_length
        self.context_max_length = context_max_length
        self.heading_form = heading_form
        self.max_phrase_words = max_phrase_words
        self.min_phrase_count = min_phrase_count
        self.phrase_cohesion = phrase_cohesion
        self.phrase_boost = phrase_boost
        self.generic_words = frozenset(generic_words)
        self._phrase_keys: set[str] = set()   # phrases found by the last rank_terms()

    # -- word forms ---------------------------------------------------------------
    def _lemma_form(self, form: str) -> str:
        words = form.split(" ")
        last = self.normalizer.lemma(words[-1])
        return " ".join(words[:-1] + [last or words[-1]])

    def order_forms(self, counts: Counter[str]) -> list[str]:
        """Word forms with the one to show as the heading first. With
        heading_form "lemma" the dictionary form is put first even if the
        text only has other forms (e.g. only "plants" -> heading "plant")."""
        if self.heading_form == "lemma":
            ordered = sorted(counts, key=lambda f: (-counts[f], len(f), f))
            lemma = self._lemma_form(ordered[0])
            return [lemma] + [f for f in ordered if f != lemma]
        if self.heading_form == "shortest":
            return sorted(counts, key=lambda f: (len(f), -counts[f], f))
        return sorted(counts, key=lambda f: (-counts[f], len(f), f))

    # -- which words / phrases each sentence contains ---------------------------------
    def _phrases_in(self, chunk_keys: list[list[str]]) -> set[str]:
        found: set[str] = set()
        for ks in chunk_keys:
            for n in range(2, self.max_phrase_words + 1):
                for i in range(len(ks) - n + 1):
                    phrase = " ".join(ks[i:i + n])
                    if phrase in self._phrase_keys:
                        found.add(phrase)
        return found

    def stem_sets(
        self,
        sentence_tokens: list[list[str]],
        chunk_lists: Optional[list[list[list[str]]]] = None,
    ) -> list[set[str]]:
        """Per sentence: the keys of its words, plus any phrase found by the
        last rank_terms(). Call rank_terms() first when using phrases."""
        key = self.normalizer.key
        sets = [{key(t) for t in tokens} for tokens in sentence_tokens]
        if chunk_lists is not None and self._phrase_keys:
            for s, chunks in zip(sets, chunk_lists):
                s |= self._phrases_in([[key(t) for t in ch] for ch in chunks])
        return sets

    # -- phrase mining -------------------------------------------------------------------
    def _accept_phrases(self, chunk_keys: list[list[list[str]]]) -> set[tuple[str, ...]]:
        top = self.max_phrase_words
        uni: Counter[str] = Counter()
        grams: dict[int, Counter] = {n: Counter() for n in range(2, top + 1)}
        for chunks in chunk_keys:
            for ks in chunks:
                uni.update(ks)
                for n in range(2, top + 1):
                    for i in range(len(ks) - n + 1):
                        gram = tuple(ks[i:i + n])
                        if len(set(gram)) == n:
                            grams[n][gram] += 1
        accepted: set[tuple[str, ...]] = set()
        for gram, c in grams.get(2, {}).items():
            if c < self.min_phrase_count:
                continue
            a, b = uni[gram[0]], uni[gram[1]]
            if gram[0] in self.generic_words or gram[1] in self.generic_words:
                # "use case" is fine, "many students" is not: a generic word must
                # belong almost only to this phrase.
                score = 2 * c / (a + b)
            else:
                # "diagram" is seen in many phrases, so judge each word separately:
                # is "activity" mostly followed by "diagram", or "diagram" mostly preceded by "activity"?
                score = max(c / a, c / b)
            if score >= self.phrase_cohesion:
                accepted.add(gram)
        for n in range(3, top + 1):
            for gram, c in grams[n].items():
                if c < self.min_phrase_count:
                    continue
                parts = min(grams[n - 1].get(gram[:-1], 0), grams[n - 1].get(gram[1:], 0))
                if parts and c / parts >= self.phrase_cohesion:
                    accepted.add(gram)
        return accepted

    def _cover(self, chunks_by_sentence, keys_by_sentence, phrases):
        """Walk every chunk left to right, taking the longest phrase at each
        position; words not inside a phrase count as single-word terms."""
        counts: Counter[str] = Counter()
        doc_freq: Counter[str] = Counter()
        forms: dict[str, Counter[str]] = defaultdict(Counter)
        for chunks, keys in zip(chunks_by_sentence, keys_by_sentence):
            present: set[str] = set()
            for chunk, ks in zip(chunks, keys):
                i = 0
                while i < len(ks):
                    take = 0
                    for n in range(min(self.max_phrase_words, len(ks) - i), 1, -1):
                        if tuple(ks[i:i + n]) in phrases:
                            take = n
                            break
                    if take:
                        k = " ".join(ks[i:i + take])
                        counts[k] += 1
                        present.add(k)
                        forms[k][" ".join(chunk[i:i + take])] += 1
                        i += take
                    else:
                        if chunk[i] not in self.generic_words:
                            counts[ks[i]] += 1
                            present.add(ks[i])
                            forms[ks[i]][chunk[i]] += 1
                        i += 1
            doc_freq.update(present)
        return counts, doc_freq, forms

    # -- UCD: Rank terms (TF-IDF) ----------------------------------------------------------
    def rank_terms(
        self,
        token_lists: list[list[str]],
        chunk_lists: Optional[list[list[list[str]]]] = None,
    ) -> list[Term]:
        """Every merged term, sorted from highest to lowest score. Pass
        `chunk_lists` (TextProcessor.tokenize_chunks per sentence) to also find phrases."""
        key = self.normalizer.key
        self._phrase_keys = set()
        if chunk_lists is not None and self.max_phrase_words >= 2:
            keys = [[[key(t) for t in ch] for ch in chunks] for chunks in chunk_lists]
            phrases = self._accept_phrases(keys)
            for _ in range(4):                    # drop phrases that end up too rare
                counts, doc_freq, forms = self._cover(chunk_lists, keys, phrases)
                weak = {p for p in phrases if counts.get(" ".join(p), 0) < self.min_phrase_count}
                if not weak:
                    break
                phrases -= weak
            self._phrase_keys = {" ".join(p) for p in phrases if counts.get(" ".join(p), 0)}
        else:
            counts, doc_freq = Counter(), Counter()
            forms = defaultdict(Counter)
            for tokens in token_lists:
                stems = [key(t) for t in tokens]
                counts.update(stems)
                doc_freq.update(set(stems))
                for token, k in zip(tokens, stems):
                    forms[k][token] += 1

        total = sum(counts.values())
        if total == 0:
            raise NoKeyTermsError(_NO_TERMS)

        n_docs = len(token_lists)
        terms = []
        for k, count in counts.items():
            tf = count / total
            idf = math.log((1 + n_docs) / (1 + doc_freq[k])) + 1  # smoothed
            boost = self.phrase_boost ** k.count(" ")
            ordered = self.order_forms(forms[k])
            variants = [v for v in ordered[1:] if forms[k][v] >= 2]   # hide one-off oddities
            terms.append(
                Term(word=ordered[0], stem=k, score=tf * idf * boost, variants=variants)
            )
        terms.sort(key=lambda t: (-t.score, t.word))
        return terms

    # -- UCD: Extract context sentences ------------------------------------------------------
    def _fit(self, sentence: str, forms: Optional[list[str]]) -> str:
        """A sentence longer than the limit is cut to a window around the term."""
        limit = self.context_max_length
        if len(sentence) <= limit:
            return sentence
        m = forms_pattern(forms).search(sentence) if forms else None
        center = m.start() if m else 0
        start = max(0, center - limit // 3)
        end = min(len(sentence), start + limit)
        start = max(0, end - limit)
        if start > 0 and sentence[start - 1] != " ":
            nxt = sentence.find(" ", start)
            if 0 <= nxt < (center if m else end):
                start = nxt + 1
        if end < len(sentence):
            cut = sentence.rfind(" ", start, end)
            if cut > start:
                end = cut
        return ("… " if start > 0 else "") + sentence[start:end].strip() + (" …" if end < len(sentence) else "")

    def find_context(
        self,
        stem_key: str,
        sentences: list[str],
        sentence_stems: list[set[str]],
        forms: Optional[list[str]] = None,
    ) -> list[str]:
        """Original sentences containing any form of the term. The same sentence
        is never listed twice; readable lengths come first."""
        matches, seen = [], set()
        for s, keys in zip(sentences, sentence_stems):
            if stem_key in keys:
                norm = " ".join(s.lower().split())
                if norm not in seen:
                    seen.add(norm)
                    matches.append(s)
        matches = [s for s in matches if not _is_code(s) and _is_sentence(s)]   # program code is never a context
        lo, hi = self.context_min_length, self.context_max_length

        def badness(s: str) -> tuple:   # stable sort keeps document order
            if lo <= len(s) <= hi:
                fit = (0, 0)
            else:
                fit = (1, lo - len(s) if len(s) < lo else len(s) - hi)
            return (1 if _noisy(s) else 0, *fit, 0 if _DEFINES.search(s) else 1)

        matches.sort(key=badness)
        return [self._fit(s, forms) for s in matches[: self.max_contexts]]

    def select_terms(
        self,
        ranked: list[Term],
        sentences: list[str],
        sentence_stems: list[set[str]],
    ) -> list[Term]:
        """Keep the top terms and attach contexts. Terms with no sentence are skipped."""
        selected: list[Term] = []
        for term in ranked:
            term.contexts = self.find_context(
                term.stem, sentences, sentence_stems, [term.word, *term.variants])
            if term.contexts:
                selected.append(term)
            if len(selected) == self.top_n:
                break
        if not selected:
            raise NoKeyTermsError(_NO_TERMS)
        return selected

    def analyze_text(
        self,
        sentences: list[str],
        sentence_tokens: list[list[str]],
        sentence_stems: list[set[str]] | None = None,
        chunk_lists: Optional[list[list[list[str]]]] = None,
    ) -> list[Term]:
        """Rank and attach contexts in one call."""
        ranked = self.rank_terms(sentence_tokens, chunk_lists)
        if sentence_stems is None:
            sentence_stems = self.stem_sets(sentence_tokens, chunk_lists)
        return self.select_terms(ranked, sentences, sentence_stems)
