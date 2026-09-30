"""
2B — Runtime Orchestrator tests.

Verifies repo registration, indexing lifecycle, context query orchestration,
and idempotent re-indexing on a synthetic in-memory project.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

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


def test_query_without_indexing_indexes_first():
    """Querying a registered-but-unindexed repo used to raise.

    It no longer does: a query that arrives before the first index waits for
    one, because "Repository not active (status=registered)" was a race the
    caller could do nothing about. Indexing is idempotent, so the query
    triggers it.
    """
    repo_path = _make_temp_repo()

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    runtime.register_repo(repo_path)

    runtime.query_context(repo_path, seed_node_ids=[])

    assert runtime.get_repo(repo_path).status == RepoStatus.ACTIVE
    assert runtime.get_repo(repo_path).node_count > 0, "indexing did not produce nodes"


def test_querying_an_unregistered_repo_still_raises():
    """Indexing on demand must not paper over a path that was never registered."""
    with pytest.raises(ValueError, match="not registered"):
        RuntimeOrchestrator().query_context(
            _make_temp_repo() + "-never-registered", seed_node_ids=[]
        )


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


def test_index_nonexistent_path_fails_not_active():
    repo_path = _make_temp_repo()

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    record = runtime.register_repo(repo_path)
    import shutil
    shutil.rmtree(repo_path)

    record = runtime.index_repo(record.root_path)

    assert record.status == RepoStatus.FAILED
    assert "does not exist" in (record.error or "")


def test_reindex_removes_deleted_file_nodes():
    repo_path = _make_temp_repo()
    extra = Path(repo_path) / "src" / "extra.py"
    extra.write_text("class Extra:\n    pass\n")

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    runtime = RuntimeOrchestrator(parser_registry=registry)
    runtime.register_repo(repo_path)

    record1 = runtime.index_repo(repo_path)
    nodes_with_extra = record1.node_count
    files_before = record1.file_count

    extra.unlink()

    record2 = runtime.refresh_repo(repo_path)

    assert record2.status == RepoStatus.ACTIVE
    assert record2.file_count == files_before - 1
    assert record2.node_count < nodes_with_extra

    main_path = str(Path(repo_path).resolve() / "src" / "models.py")
    pack = runtime.query_context(
        root_path=repo_path,
        seed_node_ids=[f"file:{main_path}"],
    )
    assert all(n.node_id != f"file:{str(extra.resolve()).replace(os.sep, '/')}" for n in pack.nodes)


def test_gitignore_rules_skip_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "keep.py").write_text(MODELS_PY)
    (tmp_path / "src" / "generated").mkdir()
    (tmp_path / "src" / "generated" / "gen.py").write_text(MODELS_PY)
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "vendored.py").write_text(MODELS_PY)
    (tmp_path / ".gitignore").write_text("vendor/\nsrc/generated\n*.tmp\n")

    runtime = RuntimeOrchestrator(parser_registry=ParserRegistry())
    files = runtime._scan_repo_files(str(tmp_path))

    names = [Path(f).as_posix() for f in files]
    assert any(f.endswith("keep.py") for f in names)
    assert not any("generated" in f or "vendor" in f for f in names)
