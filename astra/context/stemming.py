"""Reduce a word to a stem so a question matches the code it asks about.

A question says "budgeted", the module is token_budget.py. A question says
"resolves", the function is resolve_imports_into_edges. Comparing whole words
scores both as no match, which is what left token_budget.py outside the pack
for the question that is literally about it.

Deliberately a small suffix stripper rather than a full stemmer: a real
stemmer has irregular forms and this does not need them, and every rule here
is one whose result is still a prefix of the original.
"""

from __future__ import annotations

# Ordered longest-first: "ization" must be tried before "ize", or "ization"
# would strip to "at" instead of stopping at "ize".
_SUFFIXES = (
    "izations", "ization", "ically", "ically",
    "iveness", "fulness", "ousness",
    "ements", "ement", "ances", "ance",
    "ingly", "edly",
    "ings", "ing",
    "ies", "ied",
    "ers", "er",
    "est", "es",
    "ly",
    "ed",
    "s",
)

# Words that would be destroyed by stripping. "bus" must not become "bu",
# "gas" must not become "ga", "less" must not become "le".
_KEEP_AS_IS = frozenset(
    ["bus", "gas", "less", "loss", "cross", "class", "pass", "press", "process", "address", "access", "status", "focus", "bonus", "virus", "analysis", "basis", "thesis", "crisis", "this", "is", "was", "has", "its", "as", "us", "does", "yes", "plus", "thus", "unless", "cases", "uses", "comes", "goes", "makes", "takes", "gives"]
)

# The prefix length used to bucket stems once they are reduced. Six characters
# separates "import" from "important" but merges "resolve" and "resolver",
# which is the intent — they are the same word to a reader of the question.
_BUCKET = 6


def stem(word: str) -> str:
    """Reduce one word to its bucket key.

    Stripping happens fully before bucketing. Truncating first cut
    "ranking" to "rankin" and "trimming" to "trimm", neither of which then
    matched "rank" or "trim" — the truncation hid the suffix that would have
    lined them up.
    """
    lowered = word.lower()
    if lowered in _KEEP_AS_IS:
        return lowered
    for suffix in _SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) - len(suffix) >= 4:
            lowered = lowered[: -len(suffix)]
            break
    # A doubled consonant left by -ing/-ed ("trim" -> "trimm") has to be put
    # back or it never matches the shorter form.
    if len(lowered) >= 4 and lowered[-1] == lowered[-2] and lowered[-1] not in "aeiousl":
        lowered = lowered[:-1]
    return lowered[:_BUCKET]


def stem_set(words) -> set[str]:
    """Bucket keys for a collection of words.

    Each word may itself be an identifier: `resolve_imports_into_edges` is one
    string but four words, and treating it as a single opaque token collapsed
    it to "resolv", which matched every module that resolves anything.
    """
    result: set[str] = set()
    for word in words:
        if not word:
            continue
        for piece in word.replace("_", " ").replace("-", " ").split():
            result.add(stem(piece))
    return result


def name_stems(file_name: str) -> set[str]:
    """Stems for a file's own name.

    A filename is not prose, so the source-vocabulary stopword list does not
    apply: import_resolver.py is about `import`, and dropping that word is
    what left it unable to answer a question about imports.
    """
    return stem_set(file_name.replace(".", " ").split())


if __name__ == "__main__":
    # The cases that were broken
    assert stem("budgeted") == stem("budget") == "budget"
    assert stem("resolves") == stem("resolve") == "resolv"
    assert stem("trimming") == stem("trim") == "trim"
    assert stem("ranking") == stem("rank") == "rank"
    assert stem("configured") == stem("config") == "config"
    # Words that must survive
    assert stem("bus") == "bus"
    assert stem("pass") == "pass"
    assert stem("class") == "class"
    # Not required to merge: analysis and analyze are different words and
    # treating them as one would match every file that says either.
    assert stem("analysis") != stem("analyze")
    # Idempotent: stemming a stem changes nothing
    for word in ("budget", "resolve", "import", "configuration"):
        assert stem(stem(word)) == stem(word), word
    assert stem_set([]) == set()
    print("ok")
