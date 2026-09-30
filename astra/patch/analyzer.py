"""Semantic analysis of a proposed source edit.

Kept out of dashboard_app.py so it can be tested without an HTTP client, and
so the AST handling has one obvious home. The caller is responsible for
confining the path to a registered repository before calling in — this module
reads whatever it is handed.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AstDiff:
    added: set[str] = field(default_factory=set)
    removed: set[str] = field(default_factory=set)
    modified: set[str] = field(default_factory=set)


def top_level_names(tree: ast.AST) -> set[str]:
    """Function, class and async-function names anywhere in the tree.

    Nested definitions count: a helper moved inside a class is still a symbol
    a caller may depend on.
    """
    definition = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return {node.name for node in ast.walk(tree) if isinstance(node, definition)}


def diff_ast(before: str, after: str) -> AstDiff:
    """Symbols gained, lost and kept between two source strings.

    Raises SyntaxError if either side does not parse; the caller decides
    whether that is a user error or a bug.
    """
    old_names = top_level_names(ast.parse(before))
    new_names = top_level_names(ast.parse(after))
    return AstDiff(
        added=new_names - old_names,
        removed=old_names - new_names,
        modified=old_names & new_names,
    )


@dataclass
class RiskReport:
    score: int
    level: str
    confidence: float
    ast_diff: AstDiff

    @property
    def is_breaking(self) -> bool:
        return bool(self.ast_diff.removed)


def score_risk(diff: AstDiff, downstream: int = 0) -> RiskReport:
    """Weigh a diff by what it removes, what it touches, and what depends on it.

    Removing a symbol is what breaks callers, so it dominates; a new symbol
    cannot break anything that already existed.
    """
    score = (
        len(diff.removed) * 10
        + len(diff.modified) * 3
        + downstream * 2
        + len(diff.added)
    )
    score = min(100, score)
    level = "high" if score > 50 else "medium" if score > 20 else "low"
    return RiskReport(
        score=score,
        level=level,
        confidence=round(max(0.1, 1.0 - score / 100), 2),
        ast_diff=diff,
    )


def read_source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    before, after = "def a():\n    pass\n", "def b():\n    pass\n"
    report = score_risk(diff_ast(before, after))
    assert report.ast_diff.removed == {"a"}, report.ast_diff
    assert report.ast_diff.added == {"b"}, report.ast_diff
    assert report.is_breaking
    print("ok", report.level, report.score)
