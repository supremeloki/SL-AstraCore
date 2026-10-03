"""The cross-process lock, including what happens when a holder dies.

A lock file outlives the process that made it if that process is killed. The
stale check is the only thing standing between that and a database nobody can
open, so each branch is pinned here rather than left to the happy path.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import astra.runtime.repo_lock as repo_lock
from astra.runtime.repo_lock import (
    DEFAULT_TIMEOUT,
    LockTimeout,
    _break_stale,
    _is_stale,
    file_lock,
)


# ── the basics ────────────────────────────────────────────────────────────

def test_the_lock_is_exclusive(tmp_path):
    target = tmp_path / "repo.db"
    with file_lock(str(target), timeout=1.0), pytest.raises(LockTimeout), file_lock(str(target), timeout=0.2):
        pass


def test_the_lock_is_released_afterwards(tmp_path):
    target = tmp_path / "repo.db"
    with file_lock(str(target), timeout=1.0):
        pass
    assert not (tmp_path / "repo.db.lock").exists(), "the lock outlived the run"


def test_the_lock_is_released_even_when_the_body_raises(tmp_path):
    target = tmp_path / "repo.db"
    with pytest.raises(ValueError), file_lock(str(target), timeout=1.0):
        raise ValueError("boom")
    assert not (tmp_path / "repo.db.lock").exists(), "an exception leaked the lock"


def test_the_lock_file_records_the_owner(tmp_path):
    target = tmp_path / "repo.db"
    with file_lock(str(target), timeout=1.0):
        assert (tmp_path / "repo.db.lock").read_text().strip() == str(os.getpid())


def test_a_missing_parent_directory_is_created(tmp_path):
    target = tmp_path / "nested" / "deeper" / "repo.db"
    with file_lock(str(target), timeout=1.0):
        assert (tmp_path / "nested" / "deeper" / "repo.db.lock").exists()


def test_waiting_longer_than_the_timeout_raises(tmp_path):
    """The error names what is blocking, because the lock file alone does not."""
    target = tmp_path / "repo.db"
    with file_lock(str(target), timeout=1.0):
        started = time.monotonic()
        with pytest.raises(LockTimeout) as info, file_lock(str(target), timeout=0.3):
            pass
        assert time.monotonic() - started >= 0.3
    assert "another process" in str(info.value)


def test_the_default_timeout_is_long_enough_to_cover_an_index(tmp_path):
    assert DEFAULT_TIMEOUT >= 10.0, "a full index can take longer than this"


# ── the stale check ───────────────────────────────────────────────────────

def test_a_lock_from_this_process_is_not_stale(tmp_path):
    lock = tmp_path / "repo.db.lock"
    lock.write_text(str(os.getpid()))
    assert not _is_stale(lock)


def test_a_lock_from_a_dead_process_is_stale(tmp_path):
    lock = tmp_path / "repo.db.lock"
    # A pid that cannot be running: os.kill raises ProcessLookupError for it.
    lock.write_text("999999")
    assert _is_stale(lock)


def test_a_lock_from_a_live_process_is_not_stale(tmp_path):
    lock = tmp_path / "repo.db.lock"
    lock.write_text(str(os.getppid()))
    assert not _is_stale(lock)


def test_a_lock_with_no_readable_pid_is_not_stale(tmp_path):
    """Assuming live is the safe direction: wait rather than steal."""
    lock = tmp_path / "repo.db.lock"
    lock.write_text("not a pid")
    assert not _is_stale(lock)

    lock.write_text("")
    assert not _is_stale(lock)


def test_a_lock_whose_owner_cannot_be_signalled_is_not_stale(tmp_path, monkeypatch):
    """PermissionError means the process exists; stealing would be wrong."""
    monkeypatch.setattr(repo_lock.os, "name", "posix")
    lock = tmp_path / "repo.db.lock"
    lock.write_text("4242")

    def refuse(_pid, _signal):
        raise PermissionError(1, "operation not permitted")

    monkeypatch.setattr(repo_lock.os, "kill", refuse)
    assert not _is_stale(lock), "an unsignalable pid is assumed alive"


def test_an_unexpected_error_from_the_pid_check_is_not_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_lock.os, "name", "posix")
    lock = tmp_path / "repo.db.lock"
    lock.write_text("4242")

    def odd(_pid, _signal):
        raise OSError(87, "wrong argument")

    monkeypatch.setattr(repo_lock.os, "kill", odd)
    assert not _is_stale(lock)


def test_a_pid_outside_the_platform_range_cannot_be_running(tmp_path):
    """tasklist answers "no tasks" for a pid it cannot represent, which is
    the same answer as for a dead one: stale."""
    lock = tmp_path / "repo.db.lock"
    lock.write_text(str(2**40))
    assert _is_stale(lock)


def test_tasklist_failing_is_not_read_as_a_live_process(monkeypatch):
    """tasklist puts "The search filter cannot be recognized" on stderr.

    The signal is that the pid is outside the range tasklist can represent,
    so it cannot be running. Reading only stdout would miss it and the lock
    would never be reclaimed — which is what an out-of-range pid, or any pid
    tasklist cannot answer for, leaves behind.
    """
    class Refusal:
        returncode = 1
        stdout = ""
        stderr = "ERROR: The search filter cannot be recognized.\n\n"

    monkeypatch.setattr(repo_lock.subprocess, "run", lambda *a, **k: Refusal())

    assert not repo_lock._process_exists_windows(4242), (
        "tasklist refusing the filter means the pid cannot be running"
    )


def test_a_running_process_is_found_even_though_its_output_has_other_text(monkeypatch):
    """The negative cases all return False; this is the one that returns True.

    Without it a check that always answers "not running" would pass every
    other test while stealing the lock out from under a live index.
    """
    class Running:
        returncode = 0
        stdout = "python.exe                   4242 Console                  1     9,216 K"
        stderr = ""

    monkeypatch.setattr(repo_lock.subprocess, "run", lambda *a, **k: Running())

    assert repo_lock._process_exists_windows(4242)
    assert not repo_lock._process_exists_windows(1111), (
        "a pid tasklist did not list was reported as running"
    )


def test_a_pid_beyond_the_range_tasklist_accepts_is_stale(tmp_path):
    """End to end: an unrepresentable pid, not just the helper."""
    lock = tmp_path / "repo.db.lock"
    lock.write_text(str(2**40))
    assert _is_stale(lock), (
        "an out-of-range pid was read as a live process, so the lock never clears"
    )


def test_tasklist_saying_nothing_is_read_as_live(monkeypatch):
    """Silence means "cannot tell", and cannot-tell waits rather than steals."""
    class Silent:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(repo_lock.subprocess, "run", lambda *a, **k: Silent())

    assert repo_lock._process_exists_windows(4242), (
        "no answer at all means wait, not steal"
    )


def test_breaking_a_stale_lock_removes_it(tmp_path):
    lock = tmp_path / "repo.db.lock"
    lock.write_text("not a pid")
    _break_stale(lock)
    assert not lock.exists()


def test_breaking_a_lock_that_is_already_gone_is_fine(tmp_path):
    _break_stale(tmp_path / "never-existed.lock")


# ── the whole point: a killed holder does not wedge the database ──────────

def _library_root() -> str:
    import astra.runtime

    return str(Path(astra.runtime.__file__).parent.parent)


def test_a_killed_holder_releases_the_lock(tmp_path):
    """The lock file outlives a killed process; only the stale check clears it."""
    target = tmp_path / "repo.db"
    script = tmp_path / "holder.py"
    script.write_text(
        "import sys, time\n"
        f"sys.path.insert(0, {_library_root()!r})\n"
        "from astra.runtime.repo_lock import file_lock\n"
        f"with file_lock({str(target)!r}, timeout=5.0):\n"
        "    print('held', flush=True)\n"
        "    time.sleep(30)\n",
        encoding="utf-8",
    )

    process = subprocess.Popen(
        [sys.executable, str(script)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert process.stdout.readline().strip() == "held"
        # SIGKILL on POSIX, TerminateProcess on Windows: the finally block that
        # would remove the lock file never runs.
        process.kill()
        process.wait(timeout=30)

        assert (tmp_path / "repo.db.lock").exists(), (
            "the lock file was cleaned up by the OS, so this test proves nothing"
        )

        started = time.monotonic()
        with file_lock(str(target), timeout=10.0):
            pass
        assert time.monotonic() - started < 5.0, "it waited instead of reclaiming"
    finally:
        process.kill()
        process.wait(timeout=30)
