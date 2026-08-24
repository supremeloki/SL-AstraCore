from __future__ import annotations

from astra.runtime.journal import ExecutionJournal

class CrashRecovery:
    """Replays execution journal to restore runtime state."""

    def __init__(self, journal: ExecutionJournal) -> None:
        self._journal = journal

    def replay(self) -> list[dict]:
        return self._journal.read_events()
