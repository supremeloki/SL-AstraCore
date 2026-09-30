"""The patch analyser was inline in dashboard_app.py, so its risk arithmetic
had no test that could reach it. astra.patch.analyzer holds it now.
"""

import logging

import pytest

from astra.patch.analyzer import AstDiff, diff_ast, score_risk, top_level_names

BEFORE = """\
class Service:
    def start(self):
        return 1

def helper():
    return 2
"""

AFTER_REMOVED = """\
class Service:
    def start(self):
        return 1
"""

AFTER_ADDED = """\
class Service:
    def start(self):
        return 1

def helper():
    return 2

def extra():
    return 3
"""


def test_removed_symbol_is_reported():
    logging.disable(logging.CRITICAL)
    diff = diff_ast(BEFORE, AFTER_REMOVED)
    assert diff.removed == {"helper"}
    assert diff.added == set()
    assert diff.modified == {"Service", "start"}


def test_added_symbol_cannot_be_breaking():
    logging.disable(logging.CRITICAL)
    diff = diff_ast(BEFORE, AFTER_ADDED)
    assert diff.added == {"extra"}
    assert diff.removed == set()
    report = score_risk(diff)
    assert not report.is_breaking
    assert report.score < 20


def test_nested_definitions_count_as_symbols():
    logging.disable(logging.CRITICAL)
    # Moving a helper inside a class must not look like "nothing changed".
    nested = diff_ast("def inner():\n    pass\n", "class C:\n    def inner(self):\n        pass\n")
    assert "inner" in nested.modified


def test_removing_a_symbol_scores_far_higher_than_adding_one():
    logging.disable(logging.CRITICAL)
    removed = score_risk(AstDiff(removed={"a", "b", "c"}))
    added = score_risk(AstDiff(added={"a", "b", "c"}))
    assert removed.score > added.score * 5
    assert removed.is_breaking
    assert not added.is_breaking


def test_downstream_dependents_raise_the_score():
    logging.disable(logging.CRITICAL)
    diff = AstDiff(modified={"a"})
    assert score_risk(diff, downstream=10).score > score_risk(diff, downstream=0).score


def test_score_is_capped_at_100():
    logging.disable(logging.CRITICAL)
    report = score_risk(AstDiff(removed={f"s{i}" for i in range(50)}))
    assert report.score == 100
    assert report.level == "high"


def test_invalid_syntax_raises_rather_than_scoring_zero():
    logging.disable(logging.CRITICAL)
    with pytest.raises(SyntaxError):
        diff_ast("def ok():\n    pass\n", "def broken(:\n")


def test_top_level_names_reads_functions_and_classes():
    logging.disable(logging.CRITICAL)
    import ast

    names = top_level_names(ast.parse(BEFORE))
    assert names == {"Service", "start", "helper"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
