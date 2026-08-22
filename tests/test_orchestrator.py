"""
2B — Runtime Orchestrator tests.

Verifies repo registration, indexing lifecycle, context query orchestration,
and idempotent re-indexing on a synthetic in-memory project.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from astra.parser.python_adapter import PythonParserAdapter
from astra.parser.registry import ParserRegistry
from astra.runtime.models import RepoStatus
from astra.runtime.orchestrator import RuntimeOrchestrator


MAIN_PY = '''
from src.handlers import create_router
from src.models import Item

app = create_router()
'''

HANDLERS_PY = '''
from src.models import Item

def create_router():
    return None
'''

MODELS_PY = '''
class Item:
    name: str
'''


def _make_temp_repo() -> str:
    tmpdir = tempfile.mkdtemp(prefix="astra_test_")
    src = Path(tmpdir) / "src"
    src.mkdir()
    (src / "main.py").write_text(MAIN_PY)
    (src / "handlers.py").write_text(HANDLERS_PY)
    (src / "models.py").write_text(MODELS_PY)
    return tmpdir


def test_register_repo():
    repo_path = _make_temp_repo()

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    record = runtime.register_repo(repo_path, name="test-repo")

    assert record.root_path == str(Path(repo_path).resolve())
    assert record.name == "test-repo"
    assert record.status == RepoStatus.REGISTERED


def test_index_repo():
    repo_path = _make_temp_repo()

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    runtime.register_repo(repo_path)
    record = runtime.index_repo(repo_path)

    assert record.status == RepoStatus.ACTIVE
    assert record.file_count >= 3
    assert record.node_count >= 3
    assert record.edge_count >= 0
    assert record.last_indexed is not None


def test_query_context_from_indexed_repo():
    repo_path = _make_temp_repo()

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    runtime.register_repo(repo_path)
    runtime.index_repo(repo_path)

    # Find the actual file node id from the graph
    main_path = str(Path(repo_path).resolve() / "src" / "main.py")
    seed = f"file:{main_path}"

    pack = runtime.query_context(
        root_path=repo_path,
        seed_node_ids=[seed],
        query_intent="understand app entry",
    )

    assert len(pack.nodes) > 0
    assert pack.confidence > 0.0


def test_refresh_repo_idempotent():
    repo_path = _make_temp_repo()

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    runtime.register_repo(repo_path)

    record1 = runtime.index_repo(repo_path)
    n1, e1 = record1.node_count, record1.edge_count

    record2 = runtime.refresh_repo(repo_path)
    n2, e2 = record2.node_count, record2.edge_count

    assert record2.status == RepoStatus.ACTIVE
    assert n1 == n2
    assert e1 == e2


def test_query_without_indexing_raises():
    repo_path = _make_temp_repo()

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    runtime.register_repo(repo_path)

    try:
        runtime.query_context(repo_path, seed_node_ids=["any"])
        assert False, "Should have raised"
    except RuntimeError:
        pass


def test_list_repos():
    repo1 = _make_temp_repo()
    repo2 = _make_temp_repo()

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    runtime.register_repo(repo1)
    runtime.register_repo(repo2)

    repos = runtime.list_repos()
    assert len(repos) == 2