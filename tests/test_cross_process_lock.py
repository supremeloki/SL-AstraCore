"""Two processes indexing one repo must not collide.

threading.Lock only orders threads inside one interpreter, and DuckDB's own
lock is per-process, so a dashboard and a CLI run — or two dashboards — both
opened the same .db and one lost:

    IOException: IO Error: Cannot open file "...repo.db": The process cannot
    access the file because it is being used by another process.

Reproduced 3 times out of 3 before the file lock, 0 out of 3 after.
"""

import logging
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

WORKER = textwrap.dedent(
    """
    import logging, sys
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, {root!r})
    from astra.runtime.orchestrator import RuntimeOrchestrator

    orch = RuntimeOrchestrator()
    orch.register_repo({repo!r})
    record = orch.index_repo({repo!r})
    print(record.status.value + "|" + (record.error or ""))
    """
)


def test_two_processes_can_index_the_same_repo(tmp_path):
    logging.disable(logging.CRITICAL)
    from astra.runtime.orchestrator import RuntimeOrchestrator
    from astra.runtime.repo_lock import file_lock

    for i in range(60):
        (tmp_path / f"m{i}.py").write_text(f"def f{i}(): return {i}\n", encoding="utf-8")

    record = RuntimeOrchestrator().register_repo(str(tmp_path))

    # Two 60-file indexes can simply not overlap, which makes a bare race
    # flaky. Hold the lock while the workers start, so both are guaranteed to
    # find it taken and have to wait for it rather than arriving after it is
    # released.
    worker = tmp_path.parent / f"astra_worker_{os.getpid()}.py"
    worker.write_text(WORKER.format(root=str(REPO_ROOT), repo=str(tmp_path)), encoding="utf-8")
    processes = []
    try:
        with file_lock(record.db_path, timeout=30.0):
            processes = [
                subprocess.Popen(
                    [sys.executable, str(worker)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                for _ in range(2)
            ]
            # Let the workers actually reach the lock before releasing it.
            time.sleep(2.0)
        outputs = [p.communicate(timeout=180)[0].strip() for p in processes]
    finally:
        worker.unlink(missing_ok=True)

    for output in outputs:
        assert output.startswith("active"), f"a process could not take the lock: {output[:400]}"


def test_the_lock_file_is_released_after_a_run(tmp_path):
    logging.disable(logging.CRITICAL)
    (tmp_path / "a.py").write_text("def f(): return 1\n", encoding="utf-8")
    from astra.runtime.orchestrator import RuntimeOrchestrator

    orchestrator = RuntimeOrchestrator()
    record = orchestrator.register_repo(str(tmp_path))
    orchestrator.index_repo(str(tmp_path))
    assert not os.path.exists(record.db_path + ".lock"), "the lock outlived the run"


def test_a_lock_left_by_a_dead_process_is_reclaimed(tmp_path):
    """A crashed process must not wedge the next run forever."""
    logging.disable(logging.CRITICAL)
    lock_path = tmp_path / "repo.db.lock"
    lock_path.write_text("999999", encoding="ascii")  # a pid that cannot be running
    (tmp_path / "a.py").write_text("def f(): return 1\n", encoding="utf-8")

    from astra.runtime.orchestrator import RuntimeOrchestrator

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    result = orchestrator.index_repo(str(tmp_path))
    assert result.status.value == "active", result.error


def test_a_live_lock_makes_the_caller_wait_then_give_up(tmp_path):
    logging.disable(logging.CRITICAL)
    from astra.runtime.repo_lock import LockTimeout, file_lock

    target = str(tmp_path / "repo.db")
    with file_lock(target, timeout=5.0), pytest.raises(LockTimeout), file_lock(target, timeout=0.3):
        pass
    # Once released it is available again.
    with file_lock(target, timeout=1.0):
        pass


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
