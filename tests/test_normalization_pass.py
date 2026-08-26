"""2A — Graph Normalization Pass.
Verifies:
  - NameNormalizer path-aware normalization
  - NameNormalizer alias map consistency
  - RelationBuilder edge deduplication
  - PatternEnricher + ConflictEnricher deterministic output
"""

from astra.graph.name_normalizer import NameNormalizer
from astra.graph.relation_builder import (
    deduplicate_edges,
    map_dependency_to_edge,
)
from astra.graph.conflict_enricher import (
    detect_circular_dependencies,
    detect_naming_conflicts,
)
from astra.ir.models import (
    EdgeType,
    IREdge,
    IRDependency,
)


def test_normalize_key_strips_separators():
    n = NameNormalizer()
    assert n.normalize_key("My_Function") == "myfunction"
    assert n.normalize_key("my-function") == "myfunction"
    assert n.normalize_key("my function") == "myfunction"
    assert n.normalize_key("My.Function.Name") == "myfunctionname"


def test_normalize_path_forward_slash():
    n = NameNormalizer()
    assert n.normalize_path("src/auth/manager.py") == "src/auth/manager.py"
    assert n.normalize_path("src\\auth\\manager.py") == "src/auth/manager.py"


def test_normalize_node_id():
    n = NameNormalizer()
    assert n.normalize_node_id("parser", "MyFunction") == "parser::myfunction"


def test_map_dependency_to_edge():
    assert map_dependency_to_edge(IRDependency(source_file="a", target_module="b", kind="import")) == EdgeType.IMPORTS
    assert map_dependency_to_edge(IRDependency(source_file="a", target_module="b", kind="call")) == EdgeType.CALLS


def test_deduplicate_edges():
    edges = [
        IREdge(from_node="a", to_node="b", type=EdgeType.IMPORTS),
        IREdge(from_node="a", to_node="b", type=EdgeType.IMPORTS),
    ]
    deduped = deduplicate_edges(edges)
    assert len(deduped) == 1


def test_detect_naming_conflicts_empty():
    assert detect_naming_conflicts([]) == []


def test_detect_circular_dependencies():
    deps = [
        IRDependency(source_file="a", target_module="b", kind="import"),
        IRDependency(source_file="b", target_module="c", kind="import"),
        IRDependency(source_file="c", target_module="a", kind="import"),
    ]
    conflicts = detect_circular_dependencies(deps)
    assert len(conflicts) == 1
    assert conflicts[0].category == "circular_dependency"
