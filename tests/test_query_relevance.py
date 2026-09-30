"""Natural-language queries must reach the code they describe.

The context engine extracted keywords and matched them by substring only, so a
question phrased in prose ("how does indexing work") found nothing when the code
called it index_repo. Query words are now lightly stemmed on the way in.
"""

import pytest

from astra.context.graph_query import GraphQuery, _light_stem
from astra.models.graph_node import GraphNode, NodeType
from astra.models.knowledge_graph import KnowledgeGraph
from astra.runtime.orchestrator import RuntimeOrchestrator


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "indexer.py").write_text(
        "class Indexer:\n    def index_repository(self, root):\n        return 1\n", encoding="utf-8"
    )
    (tmp_path / "context_builder.py").write_text(
        "def build_context_pack(nodes):\n    return []\n", encoding="utf-8"
    )
    (tmp_path / "app.py").write_text(
        "from indexer import Indexer\n\ndef main():\n    return Indexer().index_repository('.')\n",
        encoding="utf-8",
    )
    orch = RuntimeOrchestrator()
    orch.register_repo(str(tmp_path))
    orch.index_repo(str(tmp_path))
    return tmp_path


def _orchestrator(repo):
    """A fresh orchestrator with the repo registered and indexed."""
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    orch.index_repo(str(repo))
    return orch


@pytest.mark.parametrize(
    "word,expected",
    [
        ("indexing", "index"),
        ("classes", "class"),
        ("running", "run"),
        ("files", "file"),
        ("edges", "edge"),
        ("passes", "pass"),
        # Short or already-stemmed words are left alone rather than mangled.
        ("index", ""),
        ("storage", ""),
        ("access", ""),
        ("does", ""),
    ],
)
def test_light_stem(word, expected):
    assert _light_stem(word) == expected


def test_stemmed_query_finds_the_file(repo):
    """'indexing' must reach indexer.py, which never contains that word."""
    orch = _orchestrator(repo)
    pack = orch.query_context(str(repo), seed_node_ids=[], query_intent="how does indexing work", max_tokens=4000)
    names = " ".join(n.name.lower() for n in pack.nodes)
    assert "indexer" in names, f"indexing did not reach indexer.py; got {names[:200]}"


def test_prose_query_is_not_empty(repo):
    orch = _orchestrator(repo)
    pack = orch.query_context(str(repo), seed_node_ids=[], query_intent="how does context building work", max_tokens=4000)
    assert pack.nodes, "a prose question returned an empty pack"
    assert any("context_builder" in n.name.lower() for n in pack.nodes)


def test_keyword_search_is_unaffected_by_stemming():
    """A literal match must still win; stemming only adds recall."""
    kg = KnowledgeGraph()
    for name in ("alpha.py", "beta.py"):
        node = GraphNode(id=f"file:{name}", label=name, node_type=NodeType.FILE)
        kg.nodes.append(node)
        kg.node_index[node.id] = node
    gq = GraphQuery(kg)
    assert gq.find_by_keyword("alpha") == ["file:alpha.py"]
