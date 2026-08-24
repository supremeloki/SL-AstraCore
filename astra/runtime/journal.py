from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

class ExecutionJournal:
    """Append-only journal for runtime mutations."""

    def __init__(self, journal_path: str) -> None:
        self.journal_path = journal_path

    def log_event(self, event_type: str, data: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "data": data
        }
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def read_events(self) -> list[dict]:
        if not os.path.exists(self.journal_path):
            return []
        with open(self.journal_path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f]
