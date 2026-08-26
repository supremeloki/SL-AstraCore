from astra.graph.vault_enricher import (
    build_vault_code_edges,
    build_vault_concept_edges,
    deduplicate_edges,
    detect_orphan_vault_concepts,
)
from astra.ir.models import (
    EdgeType,
    IRFileNode,
    NodeType,
    IRVaultConceptNode,
    VaultConceptKind,
)


def _make_concept(
    cid: str,
    linked: tuple[str, ...] = (),
    related: tuple[str, ...] = (),
    strength: float = 0.5,
) -> IRVaultConceptNode:
    return IRVaultConceptNode(
        id=cid,
        type=NodeType.VAULT_CONCEPT,
        name=cid,
        source="vault",
        concept_type=VaultConceptKind.DECISION,
        linked_code_paths=linked,
        related_concepts=related,
        strength=strength,
    )


def _make_file_node(id: str) -> IRFileNode:
    return IRFileNode(
        id=id,
        type=NodeType.FILE,
        name=id,
        source="scanner",
        file_path=id,
    )


def test_vault_code_edges_are_built():
    concepts = [_make_concept("c1", linked=("file:main.py",))]
    code_nodes = [_make_file_node("file:main.py")]

    edges = build_vault_code_edges(concepts, code_nodes)

    assert len(edges) == 1
    assert edges[0].from_node == "c1"
    assert edges[0].to_node == "file:main.py"
    assert edges[0].type == EdgeType.REFERENCES


def test_vault_code_edges_ignore_unresolved_links():
    concepts = [_make_concept("c1", linked=("file:missing.py",))]
    code_nodes = [_make_file_node("file:main.py")]

    assert build_vault_code_edges(concepts, code_nodes) == []


def test_vault_concept_edges_are_built():
    concepts = [
        _make_concept("vault:c1", related=("c2",)),
        _make_concept("vault:c2"),
    ]

    edges = build_vault_concept_edges(concepts)

    assert len(edges) == 1
    assert edges[0].type == EdgeType.LINKS_TO


def test_vault_concept_edges_ignore_unknown_targets():
    concepts = [_make_concept("c1", related=("nonexistent",))]

    assert build_vault_concept_edges(concepts) == []


def test_orphan_concepts_detected():
    concepts = [
        _make_concept("orphan"),
        _make_concept("connected", linked=("file:x.py",)),
    ]
    code_nodes = [_make_file_node("file:x.py")]

    orphans = detect_orphan_vault_concepts(concepts, code_nodes)

    assert orphans == ["orphan"]


def test_no_orphans_when_all_connected():
    concepts = [
        _make_concept("vault:c1", linked=("file:x.py",)),
        _make_concept("vault:c2", related=("c1",)),
    ]
    code_nodes = [_make_file_node("file:x.py")]

    assert detect_orphan_vault_concepts(concepts, code_nodes) == []


def test_deduplication_removes_exact_duplicates():
    edges = [
        build_vault_code_edges(
            [_make_concept("c1", linked=("f1",))],
            [_make_file_node("f1")],
        )[0],
        build_vault_code_edges(
            [_make_concept("c1", linked=("f1",))],
            [_make_file_node("f1")],
        )[0],
    ]

    assert len(deduplicate_edges(edges)) == 1


def test_deduplication_preserves_different_edge_types():
    from astra.ir.models import IREdge

    edges = [
        IREdge(from_node="a", to_node="b", type=EdgeType.REFERENCES),
        IREdge(from_node="a", to_node="b", type=EdgeType.LINKS_TO),
    ]

    assert len(deduplicate_edges(edges)) == 2
