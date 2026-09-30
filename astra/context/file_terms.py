"""Match a query against what a file actually contains, not just its name.

The graph stores each file's path, language and size. Ranking on that alone
means "what resolves imports between files" cannot tell import_resolver.py
from any other module, because only one of them mentions `resolve`. The
name and path are kept, and the file's own words are added, so the question
can be answered by evidence rather than by a filename that happens to
contain a keyword.
"""

from __future__ import annotations

import re
from pathlib import Path

from astra.context.stemming import name_stems, stem_set

# Words too common in source to be evidence of anything.
_STOPWORDS = frozenset(
    (
        "the", "and", "for", "with", "this", "that", "from", "into", "def", "class",
        "self", "none", "true", "false", "return", "import", "as", "if", "else",
        "elif", "while", "in", "not", "or", "is", "are", "was", "were", "be",
        "been", "has", "have", "had", "do", "does", "did", "can", "could",
        "should", "would", "may", "might", "must", "will", "list", "dict", "str",
        "int", "float", "bool", "set", "tuple", "type", "value", "name", "path",
        "file", "data", "result", "results", "node", "nodes", "item", "items",
        "key", "keys", "index", "get", "set", "add", "new",
    )
)

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# Split camelCase and snake_case so `parseFile` and `parse_file` both yield
# "parse" and "file", which is what a question would use.
_SPLIT = re.compile(r"[_\-.]+")


def _tokens(text: str) -> set[str]:
    found: set[str] = set()
    for raw in _WORD.findall(text):
        for piece in _SPLIT.split(raw):
            piece = piece.lower()
            if len(piece) > 2 and piece not in _STOPWORDS:
                found.add(piece)
        # camelCase and PascalCase: parseFile -> parse, file
        for piece in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+", raw):
            piece = piece.lower()
            if len(piece) > 2 and piece not in _STOPWORDS:
                found.add(piece)
    return found


def file_terms(path: str, max_bytes: int = 20_000) -> set[str]:
    """Distinctive words from a file's source. Empty set if unreadable.

    Reads a bounded prefix: a large generated file is not worth indexing, and
    the docstring plus the top of the module is where the vocabulary is.

    The filename's own words are included even when the body never says them —
    a module called context_selector.py should be findable by "selector" —
    but they are also returned separately so the ranker can weigh a name in
    the query above a word that merely occurs in the source.
    """
    from_file_name = name_stems(Path(path).stem)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(max_bytes)
    except OSError:
        return from_file_name
    # Stemmed on the way in, so the ranker compares stems to stems. Doing it
    # here rather than there means it happens once per file, not once per
    # query per file.
    return from_file_name | stem_set(_tokens(text))


if __name__ == "__main__":
    assert "import" not in _tokens("import os")
    assert "resolve" in _tokens("def resolve_imports_into_edges()")
    assert "parse" in _tokens("def parseFile()")
    assert "parse" in _tokens("def parse_file()")
    # the filename is evidence even when the body never says the word
    assert "selector" in file_terms("context_selector.py")
    # An unreadable file still contributes its own name: a module called
    # budget.py must be findable by "budget" even when its body cannot be read.
    assert "exist" in file_terms("does-not-exist.py")
    print("ok")
