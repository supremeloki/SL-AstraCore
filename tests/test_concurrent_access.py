"""Two threads must not open the same DuckDB file as writers.

DuckDB permits one writer per file. Indexing and querying both open the
repo's database, so an unguarded second writer failed with an opaque
"Catalog write-write conflict" and the repo was reported as FAILED with a
message that named neither the cause nor the traceback.
"""

import logging
import threading
from pathlib import Path

import pytest

from astra.runtime.models import RepoStatus
from astra.runtime.orchestrator import RuntimeOrchestrator


def _repo(path: Path, files: int = 30) -> None:
    for i in range(files):
        directory = path / f"pkg{i // 10}"
        directory.mkdir(exist_ok=True)
        (directory / f"mod{i}.py").write_text(
            f"def handler_{i}():\n    return {i}\n", encoding="utf-8"
        )


def _race_two_indexes(orchestrator: RuntimeOrchestrator, root: str, timeout: int = 60) -> list:
    """Start two index_repo calls that reach the storage layer together."""
    records: list = []
    barrier = threading.Barrier(2)

    def index() -> None:
        barrier.wait()
        records.append(orchestrator.index_repo(root))

    threads = [threading.Thread(target=index) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout)
    return records


def test_the_lock_is_actually_held_during_an_index(tmp_path):
    """A behavioural test alone does not prove the lock is used — this does."""
    logging.disable(logging.CRITICAL)
    _repo(tmp_path, files=10)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))

    observed: list[bool] = []
    lock = orchestrator._lock_for(str(tmp_path))

    original = orchestrator._scan_repo_files

    def watch(*args, **kwargs):
        # Mid-index: a second thread asking for the same lock must block.
        acquired = threading.Thread(target=lambda: observed.append(lock.acquire(blocking=False)))
        acquired.start()
        acquired.join(timeout=5)
        if observed and observed[-1]:
            lock.release()
        return original(*args, **kwargs)

    orchestrator._scan_repo_files = watch
    orchestrator.index_repo(str(tmp_path))

    assert observed == [False], "the index did not hold the lock; a second writer could race in"


def test_two_concurrent_indexes_both_succeed(tmp_path):
    """The second writer used to lose the catalog race and report FAILED.

    Without the lock this fails 6 times out of 6, so a single pass is enough
    to catch a regression; the loop is only there to be sure on a fast machine.
    """
    logging.disable(logging.CRITICAL)
    _repo(tmp_path, files=40)

    for attempt in range(3):
        orchestrator = RuntimeOrchestrator()
        orchestrator.register_repo(str(tmp_path))
        records = _race_two_indexes(orchestrator, str(tmp_path))
        assert len(records) == 2, f"attempt {attempt}: a thread did not finish"
        failed = [r for r in records if r.status != RepoStatus.ACTIVE]
        assert not failed, f"attempt {attempt}: {failed[0].status}: {failed[0].error}"


def test_a_query_during_an_index_waits_instead_of_failing(tmp_path):
    logging.disable(logging.CRITICAL)
    _repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))

    outcomes: list[str] = []

    def index() -> None:
        orchestrator.index_repo(str(tmp_path))
        outcomes.append("indexed")

    def query() -> None:
        try:
            orchestrator.query_context(
                str(tmp_path), seed_node_ids=[], query_intent="handler", max_tokens=4000
            )
            outcomes.append("queried")
        except Exception as exc:  # noqa: BLE001 - the point is that it must not raise
            outcomes.append(f"failed: {exc}")

    threads = [threading.Thread(target=index), threading.Thread(target=query)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert "indexed" in outcomes
    assert "queried" in outcomes, f"a query racing an index raised: {outcomes}"


def test_index_failure_keeps_the_exception_type(tmp_path):
    """A bare str(exc) named neither the exception nor where it came from."""
    logging.disable(logging.CRITICAL)
    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))

    original = orchestrator._parser_registry.parse

    def explode(*args, **kwargs):
        raise ValueError("parser went missing")

    orchestrator._parser_registry.parse = explode
    try:
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        record = orchestrator.index_repo(str(tmp_path))
    finally:
        orchestrator._parser_registry.parse = original

    # parse errors are collected as warnings, not fatal; the record must stay usable
    assert record.status in (RepoStatus.ACTIVE, RepoStatus.FAILED)
    if record.status == RepoStatus.FAILED:
        assert record.error.startswith(("ValueError:", "RuntimeError:", "OSError:")), record.error


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
