from astra.graph.pattern_enricher import (
    detect_design_patterns,
    detect_naming_conventions,
)
from astra.ir.models import IRFileNode, NodeType


def _make_file(path: str) -> IRFileNode:
    return IRFileNode(
        id=f"file:{path}",
        type=NodeType.FILE,
        name=path,
        source="scanner",
        file_path=path,
    )


def test_design_patterns_found_when_multiple_matches():
    files = [
        _make_file("src/repository/user_repo.py"),
        _make_file("src/repository/order_repo.py"),
    ]

    patterns = detect_design_patterns(files)

    names = [p.name for p in patterns]
    assert "repository" in names
    repo_pattern = next(p for p in patterns if p.name == "repository")
    assert repo_pattern.confidence == 0.3
    assert len(repo_pattern.locations) == 2


def test_design_patterns_not_found_when_single_match():
    files = [_make_file("src/repository/user_repo.py")]

    patterns = detect_design_patterns(files)

    assert not patterns


def test_naming_convention_detected():
    files = [
        _make_file("user_service.py"),
        _make_file("order_service.py"),
        _make_file("product.py"),
    ]

    patterns = detect_naming_conventions(files)

    names = [p.name for p in patterns]
    assert "naming:snake_case" in names
    snake = next(p for p in patterns if p.name == "naming:snake_case")
    assert snake.confidence == 1.0


def test_naming_convention_not_detected_when_rare():
    files = [
        _make_file("user_service.py"),
        _make_file("OrderService.py"),
    ]

    patterns = detect_naming_conventions(files)

    assert not patterns


def test_idempotent_pattern_detection():
    files = [
        _make_file("src/repository/user_repo.py"),
        _make_file("src/repository/order_repo.py"),
    ]

    first = detect_design_patterns(files)
    second = detect_design_patterns(files)

    assert first == second


def test_deterministic_ordering():
    files = [
        _make_file("src/repository/z_repo.py"),
        _make_file("src/repository/a_repo.py"),
    ]

    patterns = detect_design_patterns(files)

    assert [p.name for p in patterns] == ["repository"]
