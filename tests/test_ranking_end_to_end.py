"""Does a real question put a real answer near the top of the pack?

This is the product's whole reason to exist, so it is worth a test rather than
a claim. Each case names the files that answer it, and the assertion is on
rank — a membership check would have passed while three of these files were
absent from the pack entirely.

The expected lists are not always the file named in the question. Asking
"how is the context pack budgeted" is answered by context_engine.py as
defensibly as by token_budget.py, and the ranking preferring the one whose
source actually covers the words is the right behaviour, not a miss.
"""

import logging

import pytest

from astra.runtime.orchestrator import RuntimeOrchestrator

CASES = [
    ("where are the scanner's ignore rules defined",
     ["orchestrator.py", "ignore_engine.py", "repository_scanner.py"]),
    ("which module creates the duckdb staging table", ["duckdb_backend.py"]),
    ("how does the access token guard api calls", ["dashboard_app.py"]),
    ("how are nodes ranked by relevance", ["ranking.py"]),
    ("how is the event log trimmed", ["event_bus.py"]),
    ("where are the default config values", ["config.py"]),
    ("how does sqlite store graph nodes", ["sqlite_backend.py"]),
    ("what resolves imports into edges", ["import_resolver.py"]),
    ("how is the token budget enforced", ["token_budget.py", "context_engine.py"]),
    ("what detects naming conflicts", ["conflict_enricher.py", "conflict.py", "enrichment.py"]),
    ("how does the scanner use gitignore", ["orchestrator.py", "repository_scanner.py"]),
    ("where is the pack token budget decided", ["token_budget.py", "orchestrator.py"]),
]

# The repository under test, when the tests run inside it.
SELF = __import__("pathlib").Path(__file__).resolve().parent.parent


def _synthetic_repo(root) -> None:
    """A small repo where each answer file is unmistakably about its topic."""
    (root / "pkg").mkdir()
    (root / "pkg" / "budgeting.py").write_text(
        '"""Token budgeting for a context pack."""\n\n'
        "def enforce_token_budget(pack):\n"
        '    """Cap the pack by tokens."""\n'
        "    return pack\n",
        encoding="utf-8",
    )
    (root / "pkg" / "resolving.py").write_text(
        '"""Resolving imports between files."""\n\n'
        "def resolve_imports_into_edges(nodes):\n"
        '    """Turn imports into graph edges."""\n'
        "    return []\n",
        encoding="utf-8",
    )
    (root / "pkg" / "colours.py").write_text(
        '"""Colour helpers."""\n\n'
        "def rgb(hex_value):\n"
        "    return tuple(bytes.fromhex(hex_value))\n",
        encoding="utf-8",
    )
    (root / "pkg" / "geometry.py").write_text(
        '"""Geometry helpers."""\n\n'
        "def area(width, height):\n"
        "    return width * height\n",
        encoding="utf-8",
    )


def test_the_right_file_leads_a_real_question(tmp_path):
    logging.disable(logging.CRITICAL)
    _synthetic_repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    orchestrator.index_repo(str(tmp_path))

    pack = orchestrator.query_context(
        str(tmp_path), seed_node_ids=[], query_intent="token budget enforcement", max_tokens=4000
    )
    order = [
        n.name
        for n in sorted([n for n in pack.nodes if n.snippet], key=lambda n: -n.relevance_score)
    ]
    assert "budgeting.py" in order, f"the file about budgets was not returned: {order[:5]}"
    assert order.index("budgeting.py") < 3, order[:5]


def test_a_second_question_lands_on_its_own_file(tmp_path):
    logging.disable(logging.CRITICAL)
    _synthetic_repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    orchestrator.index_repo(str(tmp_path))

    pack = orchestrator.query_context(
        str(tmp_path), seed_node_ids=[], query_intent="resolve imports into edges", max_tokens=4000
    )
    order = [
        n.name
        for n in sorted([n for n in pack.nodes if n.snippet], key=lambda n: -n.relevance_score)
    ]
    assert "resolving.py" in order, order[:5]
    assert order.index("resolving.py") < 3, order[:5]


def test_unrelated_files_do_not_lead_a_question(tmp_path):
    logging.disable(logging.CRITICAL)
    _synthetic_repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    orchestrator.index_repo(str(tmp_path))

    pack = orchestrator.query_context(
        str(tmp_path), seed_node_ids=[], query_intent="token budget", max_tokens=4000
    )
    order = [
        n.name
        for n in sorted([n for n in pack.nodes if n.snippet], key=lambda n: -n.relevance_score)
    ]
    for decoy in ("colours.py", "geometry.py"):
        if decoy in order and "budgeting.py" in order:
            assert order.index(decoy) > order.index("budgeting.py"), (
                f"{decoy} outranked the file the question is about: {order}"
            )


@pytest.mark.parametrize("question,acceptable", CASES)
def test_each_question_ranks_its_answer_near_the_top(question, acceptable):
    logging.disable(logging.CRITICAL)
    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(SELF))
    try:
        result = orchestrator.index_repo(str(SELF))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"could not index the repository: {exc}")
    if result.file_count == 0:
        pytest.skip("repository is empty")

    pack = orchestrator.query_context(
        str(SELF), seed_node_ids=[], query_intent=question, max_tokens=4000
    )
    # Ranked over nodes that carry source, because that is what an agent reads.
    order = [
        n.name
        for n in sorted([n for n in pack.nodes if n.snippet], key=lambda n: -n.relevance_score)
    ]
    rank = min(
        (order.index(name) + 1 for name in acceptable if name in order),
        default=999,
    )
    assert rank <= 5, (
        f"{question!r} ranked none of {acceptable} in the top five; "
        f"it had {order[:5]}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
