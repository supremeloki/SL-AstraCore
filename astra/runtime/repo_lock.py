"""Cross-process exclusion for a repo's database file.

DuckDB permits one writer per file and takes a process-level lock, so two
processes indexing the same repo collide:

    IOException: IO Error: Cannot open file "...repo.db": The process cannot
    access the file because it is being used by another process.

A threading.Lock cannot help: it lives in one interpreter. This is an
exclusive-create lock file, which the OS releases even if the process dies,
so a crashed run does not wedge the next one.

Deliberately not reentrant across processes. Same-process nesting re-enters
through the in-memory lock, which is what keeps a query issued from inside an
index from deadlocking against itself.
"""

from __future__ import annotations

import contextlib
import errno
import os
import time
from contextlib import contextmanager
from pathlib import Path

# How long to wait for the other process before giving up.
DEFAULT_TIMEOUT = 30.0
_POLL_SECONDS = 0.05


class LockTimeout(RuntimeError):
    """Another process held the lock for too long."""


@contextmanager
def file_lock(path: str, timeout: float = DEFAULT_TIMEOUT):
    """Hold an exclusive lock on `path`, waiting for a concurrent holder."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    acquired = False
    while True:
        try:
            handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _is_stale(lock_path):
                # The holder is gone; its lock file is not.
                _break_stale(lock_path)
                continue
            if time.monotonic() >= deadline:
                raise LockTimeout(
                    f"timed out after {timeout:g}s waiting for {lock_path.name}; "
                    "another process is indexing this repository"
                ) from None
            time.sleep(_POLL_SECONDS)
            continue
        except OSError as exc:  # pragma: no cover - platform specific
            if exc.errno != errno.EEXIST:
                raise
            time.sleep(_POLL_SECONDS)
            continue
        else:
            acquired = True
            os.write(handle, str(os.getpid()).encode("ascii"))
            os.close(handle)
            break

    try:
        yield
    finally:
        if acquired:
            with contextlib.suppress(OSError):
                lock_path.unlink()


def _is_stale(lock_path: Path) -> bool:
    """True when the lock file's owner is no longer running.

    Only meaningful where PIDs are integers; elsewhere the file is assumed
    live, which is the safe direction — it means waiting rather than stealing.
    """
    try:
        raw = lock_path.read_text(encoding="ascii", errors="ignore").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return False
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError:
        return False
    return False


def _break_stale(lock_path: Path) -> None:
    with contextlib.suppress(OSError):
        lock_path.unlink()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        target = os.path.join(directory, "repo.db")
        with file_lock(target, timeout=1.0):
            # A second attempt while held must time out, not succeed.
            try:
                with file_lock(target, timeout=0.2):
                    raise AssertionError("the lock was not exclusive")
            except LockTimeout:
                pass
        # Released, so it can be taken again.
        with file_lock(target, timeout=1.0):
            pass
        assert not os.path.exists(target + ".lock")
    print("ok")
