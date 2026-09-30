"""The ranking measured only how central a node was in the graph.

score() added confidence, degree, risk and complexity — properties of the
repository, not of the question. A query about DuckDB returned whatever files
were most connected, and the analytic label "pattern:naming:snake_case"
outranked real source because every file references it.

These tests pin that the query's own words move the order, and that analytic
labels no longer displace files.
"""

import logging

from astra.context.ranking import Ranking
from astra.models.graph_node import GraphNode, NodeType


def _node(
    node_id: str, label: str, node_type=NodeType.FILE, confidence: float = 0.5, **properties
) -> GraphNode:
    return GraphNode(
        id=node_id,
        label=label,
        node_type=node_type,
        confidence=confidence,
        properties=properties,
    )


def _ranking(nodes, edges=()) -> Ranking:
    ranking = Ranking.__new__(Ranking)
    ranking._kg = type("KG", (), {"node_index": {n.id: n for n in nodes}, "edges": list(edges)})()
    ranking._adj = {}
    ranking._reverse_adj = {}
    for edge in edges:
        ranking._adj[edge.from_node] = ranking._adj.get(edge.from_node, 0) + 1
        ranking._reverse_adj[edge.to_node] = ranking._reverse_adj.get(edge.to_node, 0) + 1
    ranking._files_indexed = max(len(nodes), 1)
    ranking._document_frequency = {}
    return ranking


def _edge(from_node: str, to_node: str):
    return type("E", (), {"from_node": from_node, "to_node": to_node})()


def test_query_words_outrank_structural_score():
    logging.disable(logging.CRITICAL)
    # Same confidence and no edges: the only difference is the text.
    central = _node("file:a.py", "a.py")
    matching = _node("file:duckdb_backend.py", "duckdb_backend.py")
    ranking = _ranking([central, matching])

    without_terms = ranking.rank([central.id, matching.id])
    assert without_terms[0][0] == central.id or without_terms[0][1] == without_terms[1][1]

    with_terms = ranking.rank([central.id, matching.id], terms=["duckdb"])
    assert with_terms[0][0] == matching.id, "the file named in the query did not win"


def test_an_unrelated_file_still_loses_to_a_matching_one():
    logging.disable(logging.CRITICAL)
    unrelated = _node("file:utils.py", "utils.py")
    matching = _node("file:staging.py", "staging.py")
    ranking = _ranking([unrelated, matching])
    ranked = ranking.rank([unrelated.id, matching.id], terms=["staging"])
    assert ranked[0][0] == matching.id


def test_analytic_labels_do_not_outrank_source():
    logging.disable(logging.CRITICAL)
    """A pattern node is referenced by every file, so degree alone floated it
    to the top of every pack."""
    pattern = _node("pattern:naming:snake_case", "naming:snake_case", NodeType.PATTERN)
    source = _node("file:real.py", "real.py", NodeType.FILE)
    edges = [_edge(f"file:f{i}.py", pattern.id) for i in range(20)]
    ranking = _ranking([pattern, source], edges)
    ranked = ranking.rank([pattern.id, source.id])
    assert ranked[0][0] == source.id, "an analytic label displaced a real file"


def test_file_path_counts_as_matchable_text():
    logging.disable(logging.CRITICAL)
    """file_path lives in metadata, not properties — reading only properties
    matched nothing and silently disabled the whole term."""
    node = _node("file:x", "helper.py")
    node.metadata = {"file_path": "src/payments/stripe_client.py"}
    ranking = _ranking([node])
    assert ranking._text_match(node, ["stripe"]) > 0
    assert ranking._text_match(node, ["kubernetes"]) == 0


def test_text_match_is_proportional_to_coverage():
    logging.disable(logging.CRITICAL)
    node = _node("file:x", "auth_token_guard.py")
    ranking = _ranking([node])
    one = ranking._text_match(node, ["auth", "kubernetes", "terraform"])
    two = ranking._text_match(node, ["auth", "token"])
    assert two > one, "matching more of the query should score higher"


def test_ranking_without_terms_is_unchanged():
    """Existing callers pass no terms; the structural order must still work."""
    logging.disable(logging.CRITICAL)
    a = _node("file:a.py", "a.py")
    b = _node("file:b.py", "b.py", NodeType.FILE, confidence=0.9)
    ranking = _ranking([a, b])
    ranked = ranking.rank([a.id, b.id])
    assert ranked[0][0] == b.id, "the higher-confidence node should lead"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
