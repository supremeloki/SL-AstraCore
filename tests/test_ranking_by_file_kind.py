"""Prose outranks source, and size outranks subject.

Two defects measured on this repository's own questions:

- "where are the scanner's ignore rules defined" put README.md second and
  repository_scanner.py third. The README says the same sentence in prose, so
  it repeats the question's words with nothing else competing.
- "where are the default config values" put ranking.py first: it holds all
  three of {default, config, values} across 361 distinct words, so raw
  coverage scored 1.0, while config.py — the file the question names — holds
  two of them across 104. A name that matches a rare word of the question
  wins; a name that matches a common one does not.
"""

import logging
import os

from astra.context.ranking import _is_prose, _is_test_file
from astra.models.graph_node import GraphNode, NodeType

logging.disable(logging.CRITICAL)


def _node(path):
    node = GraphNode(
        id=f"file:{path}", label=path.rsplit("/", 1)[-1], node_type=NodeType.FILE,
        confidence=0.5,
    )
    node.properties = {"file_path": path}
    node.metadata = {}
    return node


# ── telling prose and source apart ────────────────────────────────────────

def test_documentation_is_prose():
    for path in ("README.md", "docs/guide.rst", "NOTES.txt", "CHANGELOG.markdown"):
        assert _is_prose(_node(path)), path


def test_build_and_dependency_files_are_prose():
    for path in ("pyproject.toml", "requirements.txt", "Dockerfile", "Makefile"):
        assert _is_prose(_node(path)), path


def test_development_requirements_are_prose():
    assert _is_prose(_node("requirements-dev.txt"))
    assert _is_prose(_node("constraints.in"))


def test_source_is_not_prose():
    for path in ("billing.py", "scanner/repository_scanner.py", "src/app.ts"):
        assert not _is_prose(_node(path)), path


def test_only_the_extension_decides():
    """markdown_adapter.py is a parser adapter, not documentation."""
    assert not _is_prose(_node("astra/parser/markdown_adapter.py"))
    assert not _is_prose(_node("docs.py"))


def test_tests_are_detected_and_not_confused_with_prose():
    assert _is_test_file(_node("tests/test_billing.py"))
    assert _is_test_file(_node("src/billing_test.py"))
    assert not _is_test_file(_node("contest.py"))
    assert not _is_prose(_node("src/billing.py"))


# ── ranking behaviour ─────────────────────────────────────────────────────

def _order(engine, root, question, budget=4000):
    pack = engine.query_context(
        root, seed_node_ids=[], query_intent=question, max_tokens=budget
    )
    return [
        n.name
        for n in sorted(
            [n for n in pack.nodes if n.snippet], key=lambda n: -n.relevance_score
        )
    ]


def test_a_file_named_after_a_rare_word_of_the_question_comes_first(tmp_path):
    from astra.runtime.orchestrator import RuntimeOrchestrator

    (tmp_path / "config.py").write_text(
        '"""Default configuration values."""\n\nDEFAULTS = {"a": 1}\n', encoding="utf-8"
    )
    for index in range(30):
        (tmp_path / f"mod{index}.py").write_text(
            f"def f{index}():\n    return {index}\n", encoding="utf-8"
        )

    engine = RuntimeOrchestrator()
    engine.register_repo(str(tmp_path))
    engine.index_repo(str(tmp_path))
    order = _order(engine, str(tmp_path), "where are the default config values")

    assert order, "the pack was empty"
    assert order[0] == "config.py", order[:5]


def test_the_readme_does_not_outrank_the_code_it_describes():
    from astra.runtime.orchestrator import RuntimeOrchestrator

    root = os.getcwd()
    engine = RuntimeOrchestrator()
    engine.register_repo(root)
    engine.index_repo(root)
    try:
        order = _order(
            engine, root, "where are the scanner's ignore rules defined"
        )
        if "README.md" not in order:
            return  # nothing to compare against
        assert order.index("repository_scanner.py") < order.index("README.md"), (
            f"the readme outranked the code it describes: {order[:5]}"
        )
    finally:
        engine._graph_cache.pop(root, None)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
