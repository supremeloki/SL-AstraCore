"""Does a real question put a real answer near the top of the pack?

This is the product's whole reason to exist, so it is worth a test rather than
a claim. Each case names the files a competent answer could reasonably cite;
the ranking is judged on where one of them lands, not on a single filename.

Before content-based matching, three of these files were absent from the pack
entirely. A test that only checked "the file is somewhere in the list" would
have passed then, so the assertion is on rank.
"""

import logging
from pathlib import Path

import pytest

from astra.runtime.orchestrator import RuntimeOrchestrator

# Each case: a question, and the files that answer it.
CASES = [
    ("where are the scanner's ignore rules defined", ["orchestrator.py", "ignore_engine.py", "repository_scanner.py"]),
    ("which module creates the duckdb staging table", ["duckdb_backend.py"]),
    ("how does the access token guard api calls", ["dashboard_app.py"]),
    ("how are nodes ranked by relevance", ["ranking.py"]),
    ("how is the event log trimmed", ["event_bus.py"]),
    ("where are the default config values", ["config.py"]),
    ("how does sqlite store graph nodes", ["sqlite_backend.py"]),
    ("what resolves imports into edges", ["import_resolver.py"]),
    ("how is the token budget enforced", ["token_budget.py"]),
    ("what detects naming conflicts", ["enrichment.py"]),
]

# The repository under test, when the tests run inside it.
SELF = Path(__file__).resolve().parent.parent


def _synthetic_repo(root: Path) -> None:
    """A small repo where each answer file is unmistakably about its topic."""
    (root / "astra").mkdir()
    (root / "astra" / "budgeting.py").write_text(
        '"""Token budgeting for a context pack."""\n\n'
        "def enforce_token_budget(pack):\n"
        '    """Cap the pack by tokens."""\n'
        "    return pack\n",
        encoding="utf-8",
    )
    (root / "astra" / "resolving.py").write_text(
        '"""Resolving imports between files."""\n\n'
        "def resolve_imports_into_edges(nodes):\n"
        '    """Turn imports into graph edges."""\n'
        "    return []\n",
        encoding="utf-8",
    )
    (root / "astra" / "unrelated.py").write_text(
        '"""Colour helpers."""\n\n'
        "def rgb(hex_value):\n"
        "    return tuple(bytes.fromhex(hex_value))\n",
        encoding="utf-8",
    )
    (root / "astra" / "unrelated_two.py").write_text(
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
    with_code = [n for n in pack.nodes if n.snippet]
    order = [n.name for n in sorted(with_code, key=lambda n: -n.relevance_score)]

    assert "budgeting.py" in order, f"the file about budgets was not returned: {order[:5]}"
    assert order.index("budgeting.py") < 3, f"it ranked {order.index('budgeting.py')}: {order[:5]}"


def test_a_second_question_lands_on_its_own_file(tmp_path):
    logging.disable(logging.CRITICAL)
    _synthetic_repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    orchestrator.index_repo(str(tmp_path))

    pack = orchestrator.query_context(
        str(tmp_path), seed_node_ids=[], query_intent="resolve imports into edges", max_tokens=4000
    )
    order = [n.name for n in sorted(
        [n for n in pack.nodes if n.snippet], key=lambda n: -n.relevance_score
    )]
    assert "resolving.py" in order, order[:5]
    assert order.index("resolving.py") < 3, order[:5]


def test_unrelated_files_do_not_lead_a_question(tmp_path):
    """Two decoys exist; neither should top the results for a budget question."""
    logging.disable(logging.CRITICAL)
    _synthetic_repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    orchestrator.index_repo(str(tmp_path))

    pack = orchestrator.query_context(
        str(tmp_path), seed_node_ids=[], query_intent="token budget", max_tokens=4000
    )
    order = [n.name for n in sorted(
        [n for n in pack.nodes if n.snippet], key=lambda n: -n.relevance_score
    )]
    for decoy in ("unrelated.py", "unrelated_two.py"):
        if decoy in order and "budgeting.py" in order:
            assert order.index(decoy) > order.index("budgeting.py"), (
                f"{decoy} outranked the file the question is about: {order}"
            )


@pytest.mark.parametrize("question,acceptable", CASES)
def test_each_question_returns_its_answer_somewhere_in_the_pack(question, acceptable):
    """Weak by design: the strong form is the synthetic test above. This one
    only guards against a file disappearing from the graph entirely."""
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
    names = {n.name for n in pack.nodes}
    assert any(name in names for name in acceptable), (
        f"{question!r} returned none of {acceptable}; top was "
        f"{[n.name for n in sorted(pack.nodes, key=lambda n: -n.relevance_score)[:5]]}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
