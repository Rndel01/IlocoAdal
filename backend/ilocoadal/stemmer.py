"""Simple word merging (a light stemmer).

Reduces a word to a grouping key so that "plant", "plants", "planted" and
"planting" count as one term. The key is only used internally for counting
and matching; the document always shows real words from the text.

It handles plurals, -ed and -ing endings, and a trailing silent e. It is
deliberately simple: irregular forms (leaf/leaves) are not merged.
"""

_VOWELS = set("aeiouy")


def stem(word: str, min_e_len: int = 3) -> str:
    w = word.lower()
    if len(w) <= 3:
        return w

    # plurals
    if w.endswith("sses"):                       # processes -> process
        w = w[:-2]
    elif w.endswith("ies") and len(w) > 4:       # studies -> study
        w = w[:-3] + "y"
    elif w.endswith(("ches", "shes", "xes")):    # branches -> branch
        w = w[:-2]
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]                               # cells -> cell

    # verb endings
    if w.endswith("ied") and len(w) > 4:         # studied -> study
        w = w[:-3] + "y"
    else:
        for suffix in ("ing", "ed"):
            base = w[: -len(suffix)]
            if w.endswith(suffix) and len(base) >= 3 and any(c in _VOWELS for c in base):
                w = base
                if len(w) >= 3 and w[-1] == w[-2] and w[-1] not in "lsz":
                    w = w[:-1]                   # running -> run
                break

    # silent e: make / making -> mak
    if w.endswith("e") and len(w) > min_e_len:
        w = w[:-1]
    return w
