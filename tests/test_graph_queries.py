import os
import tempfile

from astra.graph.graph_engine import DomainGraphEngine
from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.graph.query_engine import GraphQueryEngine
from astra.ir.models import EdgeType, IREdge, IRNode, NodeType


def _chain_storage():
    storage = InMemoryGraphStorage()
    ids = ["file:a", "file:b", "file:c", "file:d"]
    for nid in ids:
        storage.add_node(IRNode(id=nid, type=NodeType.FILE, name=nid, source="parser"))
    storage.write_edges([
        IREdge(from_node="file:a", to_node="file:b", type=EdgeType.IMPORTS),
        IREdge(from_node="file:b", to_node="file:c", type=EdgeType.IMPORTS),
        IREdge(from_node="file:c", to_node="file:d", type=EdgeType.IMPORTS),
        IREdge(from_node="file:d", to_node="file:a", type=EdgeType.REFERENCES),
    ])
    return storage


def test_shortest_path_on_chain():
    engine = GraphQueryEngine(_chain_storage())
    path = engine.shortest_path("file:a", "file:c")
    assert path == ["file:a", "file:b", "file:c"]


def test_shortest_path_returns_none_when_unreachable():
    storage = InMemoryGraphStorage()
    storage.add_node(IRNode(id="file:x", type=NodeType.FILE, name="x", source="parser"))
    storage.add_node(IRNode(id="file:y", type=NodeType.FILE, name="y", source="parser"))
    path = GraphQueryEngine(storage).shortest_path("file:x", "file:y")
    assert path is None


def test_shortest_path_same_node():
    engine = GraphQueryEngine(_chain_storage())
    assert engine.shortest_path("file:a", "file:a") == ["file:a"]


def test_extract_subgraph_keeps_only_induced_edges():
    engine = GraphQueryEngine(_chain_storage())
    result = engine.extract_subgraph(["file:a", "file:b", "file:d"])
    node_ids = {n.id for n in result.nodes}
    assert node_ids == {"file:a", "file:b", "file:d"}
    edge_pairs = {(e.from_node, e.to_node) for e in result.edges}
    assert ("file:a", "file:b") in edge_pairs
    assert ("file:d", "file:a") in edge_pairs
    assert all(e.to_node != "file:c" and e.from_node != "file:c" for e in result.edges)


def test_impact_analysis_is_downstream_and_capped():
    engine = GraphQueryEngine(_chain_storage())
    result = engine.impact_analysis("file:a", depth=2)
    ids = {n.id for n in result.nodes}
    assert ids == {"file:b", "file:c"}
    full = {n.id for n in engine.impact_analysis("file:a", depth=10).nodes}
    assert full == {"file:b", "file:c", "file:d"}


def test_enricher_wiring_populates_conflicts_on_tmpdir_fixture():
    root = tempfile.mkdtemp()
    try:
        for rel in ("pkg/mod_a.py", "other/mod_a.py"):
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("def run():\n    return 1\n")
        pkg = os.path.join(root, "pkg", "__init__.py")
        with open(pkg, "w", encoding="utf-8") as f:
            f.write("\n")

        from astra.parser.universal_parser import UniversalParser
        from astra.scanner.repository_scanner import RepositoryScanner

        repository_index = RepositoryScanner(root).scan_repository()
        parse_index = UniversalParser().parse_repository(repository_index)
        graph = DomainGraphEngine().build(repository_index, parse_index)

        assert graph.conflicts.conflicts, "naming conflict between mod_a.py copies expected"
        naming = [c for c in graph.conflicts.conflicts if c.conflict_type.value == "naming"]
        assert naming
        assert any(c.source_a.startswith("pkg/") or c.source_b.startswith("pkg/") for c in naming)
        assert all(c.id.startswith("conflict:") for c in graph.conflicts.conflicts)

        symbol_labels = [n.label for n in graph.nodes]
        assert "run" in symbol_labels
        belongs_to = [e for e in graph.edges if e.edge_type.value == "belongs_to"]
        assert belongs_to
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def test_enricher_wiring_populates_patterns_and_vault_links():
    root = tempfile.mkdtemp()
    try:
        files = {
            "src/repository/user_repository.py": "class UserRepository:\n    pass\n",
            "src/repository/order_repository.py": "class OrderRepository:\n    pass\n",
            "docs/Idea.md": "# Idea\n\n[[src/repository/user_repository.py]]\n",
        }
        for rel, content in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        from astra.parser.universal_parser import UniversalParser
        from astra.scanner.repository_scanner import RepositoryScanner

        repository_index = RepositoryScanner(root).scan_repository()
        parse_index = UniversalParser().parse_repository(repository_index)
        graph = DomainGraphEngine().build(repository_index, parse_index)

        assert any(p.name == "repository" for p in graph.patterns.patterns)

        vault_refs = [
            e for e in graph.edges
            if e.from_node.startswith("vault:") and e.to_node.startswith("file:")
        ]
        assert vault_refs, "markdown heading should link to referenced code file"
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
