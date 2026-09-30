"""Does the ranking use the query at all?

These are the cases that were measurably broken: a hub file led every pack
because degree was weighted linearly, tests outranked the code they test, and
the snippet budget was spent on whichever node came first in set order.
"""

import logging

from astra.context.ranking import Ranking, _degree, _is_test_file
from astra.models.graph_node import GraphNode, NodeType


def _node(node_id, label, node_type=NodeType.FILE, confidence=0.5, meta=None, **props):
    node = GraphNode(
        id=node_id,
        label=label,
        node_type=node_type,
        confidence=confidence,
        properties=props,
    )
    node.metadata = meta or {}
    return node


def _ranking(nodes, edges=()):
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


def _edge(a, b):
    return type("E", (), {"from_node": a, "to_node": b})()


def test_degree_grows_logarithmically_not_linearly():
    logging.disable(logging.CRITICAL)
    assert _degree(1) < _degree(10) < _degree(100)
    # A hub must not be worth thirty times an ordinary file.
    assert _degree(178) / _degree(6) < 5, "degree is still effectively linear"


def test_a_hub_file_cannot_beat_the_file_the_query_names():
    """models.py has 88 edges and led every pack regardless of the question."""
    hub = _node("file:models.py", "models.py")
    answer = _node("file:duckdb_backend.py", "duckdb_backend.py")
    edges = [_edge("file:a.py", hub.id) for _ in range(40)]
    ranking = _ranking([hub, answer], edges)
    ranked = ranking.rank([hub.id, answer.id], terms=["duckdb"])
    assert ranked[0][0] == answer.id


def test_test_files_are_demoted_below_what_they_test():
    logging.disable(logging.CRITICAL)
    test = _node("file:test_config.py", "test_config.py", meta={"file_path": "tests/test_config.py"})
    real = _node("file:config.py", "config.py", meta={"file_path": "astra/core/config.py"})
    assert _is_test_file(test) and not _is_test_file(real)
    ranking = _ranking([test, real])
    ranked = ranking.rank([test.id, real.id], terms=["config"])
    assert ranked[0][0] == real.id


def test_test_detection_covers_the_usual_spellings():
    logging.disable(logging.CRITICAL)
    cases = {
        "test_thing.py": True,
        "thing_test.py": True,
        "tests/thing.py": False,
        "attestation.py": False,  # ends with "test.py" as a substring, not a name
        "contest.py": False,
    }
    for filename, expected in cases.items():
        node = _node("file:x", filename, meta={"file_path": f"pkg/{filename}"})
        assert _is_test_file(node) is expected, filename


def test_a_file_outranks_a_symbol_that_shares_only_one_word():
    """The file a question names beats a symbol that matches less of it.

    With stemming, a symbol built from the query's own words matches as much
    as the file does, and the file still leads — the unit an agent navigates
    by is the file, not one function inside someone else's. A symbol whose
    name *is* the question can still win, because then the file is not the
    answer to anything.
    """
    logging.disable(logging.CRITICAL)
    helper = _node("sym:some_helper", "some_helper", NodeType.FUNCTION)
    module = _node("file:import_resolver.py", "import_resolver.py", NodeType.FILE)
    ranking = _ranking([helper, module])
    ranked = ranking.rank([helper.id, module.id], terms=["imports", "resolves"])
    assert ranked[0][0] == module.id, "the file naming the query's words should lead"

    # Asked about the function itself, the function leads.
    precise = _node(
        "sym:resolve_imports_into_edges", "resolve_imports_into_edges", NodeType.FUNCTION
    )
    ranking2 = _ranking([precise, module])
    ranked2 = ranking2.rank([precise.id, module.id], terms=["resolve_imports_into_edges"])
    assert ranked2[0][0] == precise.id, "asking for the function by name should return it"


def test_analytic_labels_stay_demoted():
    logging.disable(logging.CRITICAL)
    pattern = _node("pattern:x", "naming:snake_case", NodeType.PATTERN)
    source = _node("file:real.py", "real.py", NodeType.FILE)
    edges = [_edge(f"file:f{i}.py", pattern.id) for i in range(20)]
    ranking = _ranking([pattern, source], edges)
    assert ranking.rank([pattern.id, source.id])[0][0] == source.id


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
