from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

class ExecutionJournal:
    """Append-only journal for runtime mutations."""

    def __init__(self, journal_path: str) -> None:
        self.journal_path = journal_path
        self._next_sequence: int | None = None

    def log_event(self, event_type: str, data: Any) -> None:
        if self._next_sequence is None:
            seqs = [e.get("sequence", 0) for e in self.read_events()]
            self._next_sequence = (max(seqs) + 1) if seqs else 1
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "data": data,
            "sequence": self._next_sequence,
        }
        self._next_sequence += 1
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def read_events(self) -> list[dict]:
        if not os.path.exists(self.journal_path):
            return []
        with open(self.journal_path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f]
