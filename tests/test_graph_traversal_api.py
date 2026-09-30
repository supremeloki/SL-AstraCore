"""Graph traversal endpoints must report the real dependency direction.

GraphQueryEngine.shortest_path and impact_analysis were written and unit-tested
against an in-memory store, but nothing in the app called them, and
impact_analysis walked *outgoing* edges — so it answered "what does this file
import" when asked "what breaks if I change this file". Both are now reachable
over HTTP and the impact traversal follows reverse edges.
"""

from pathlib import Path

import pytest

import dashboard_app as da
from astra.graph.query_engine import GraphQueryEngine
from astra.storage.backend import StorageProvider


@pytest.fixture
def client(auth_client):
    return auth_client


@pytest.fixture
def indexed_repo(tmp_path):
    (tmp_path / "lib.py").write_text("def h():\n    return 1\n", encoding="utf-8")
    (tmp_path / "lib2.py").write_text("from lib import h\n\ndef g():\n    return h()\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("from lib2 import g\n\ndef main():\n    return g()\n", encoding="utf-8")
    # Register on the app's own orchestrator so the HTTP endpoints can see it too.
    da._orchestrator.register_repo(str(tmp_path))
    da._orchestrator.index_repo(str(tmp_path))
    return tmp_path


def _node_id(repo: Path, name: str) -> str:
    return f"file:{repo}{chr(92)}{name}"


def _record_for(repo: Path):
    records = [r for r in da._orchestrator.list_repos() if r.root_path == str(repo)]
    assert records, f"repo {repo} is not registered"
    return records[0]


def _with_storage(repo: Path):
    record = _record_for(repo)
    storage = StorageProvider(backend=record.storage_backend, db_path=record.db_path).create()
    storage.connect()
    return storage


def test_shortest_path_follows_imports(indexed_repo):
    storage = _with_storage(indexed_repo)
    try:
        route = GraphQueryEngine(storage).shortest_path(
            _node_id(indexed_repo, "app.py"), _node_id(indexed_repo, "lib.py")
        )
    finally:
        storage.close()
    assert route is not None, "app.py imports lib2 which imports lib; a path must exist"
    assert route[0].endswith("app.py") and route[-1].endswith("lib.py")
    assert len(route) == 3


def test_impact_follows_dependents_not_dependencies(indexed_repo):
    """Changing lib.py must surface lib2.py and app.py, never the other way round."""
    storage = _with_storage(indexed_repo)
    try:
        result = GraphQueryEngine(storage).impact_analysis(_node_id(indexed_repo, "lib.py"), depth=3)
    finally:
        storage.close()

    names = {n.name for n in result.nodes}
    assert "lib2.py" in names, "lib2.py imports lib.py, so it is affected"
    assert "app.py" in names, "app.py is transitively affected"
    assert "lib.py" not in names, "the seed must be excluded from its own impact"


def test_impact_and_path_endpoints_are_served(client, indexed_repo):
    impact = client.get(
        "/api/graph/impact",
        params={"path": str(indexed_repo), "node_id": _node_id(indexed_repo, "lib.py")},
    )
    assert impact.status_code == 200, impact.text
    assert impact.json()["affected_count"] > 0

    route = client.get(
        "/api/graph/path",
        params={
            "path": str(indexed_repo),
            "from_id": _node_id(indexed_repo, "app.py"),
            "to_id": _node_id(indexed_repo, "lib.py"),
        },
    )
    assert route.status_code == 200, route.text
    assert route.json()["length"] == 2


def test_traversal_endpoints_refuse_unregistered_repos(client, tmp_path):
    assert client.get("/api/graph/impact", params={"path": str(tmp_path), "node_id": "x"}).status_code == 404
    assert client.get(
        "/api/graph/path", params={"path": str(tmp_path), "from_id": "a", "to_id": "b"}
    ).status_code == 404
