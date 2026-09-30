from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass
class ReplayEvent:
    """A single event in the replay log."""
    event_type: str
    payload: Any
    timestamp: float
    sequence: int


class ReplayEngine:
    """Deterministic replay of execution journal."""

    def __init__(self, journal_path: str) -> None:
        self._journal_path = journal_path
        self._events: list[ReplayEvent] = []

    def load_journal(self) -> list[ReplayEvent]:
        """Load events from journal file.

        Accepts both bare replay lines ({event_type, payload, timestamp,
        sequence}) and ExecutionJournal entries ({type, data, timestamp,
        sequence}).
        """
        self._events = []
        if not os.path.exists(self._journal_path):
            return self._events

        with open(self._journal_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                ts = data.get("timestamp", 0.0)
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts).timestamp()
                    except ValueError:
                        ts = 0.0
                self._events.append(ReplayEvent(
                    event_type=data.get("event_type") or data.get("type", ""),
                    payload=data.get("payload", data.get("data", {})),
                    timestamp=float(ts),
                    sequence=data.get("sequence", 0),
                ))
        return self._events

    def replay(self, handler: Callable[[ReplayEvent], None]) -> int:
        """Replay all events through handler."""
        count = 0
        for event in self._events:
            handler(event)
            count += 1
        return count

    def replay_from_sequence(self, from_sequence: int, handler: Callable[[ReplayEvent], None]) -> int:
        """Replay events starting from a specific sequence number."""
        count = 0
        for event in self._events:
            if event.sequence >= from_sequence:
                handler(event)
                count += 1
        return count

    def get_last_sequence(self) -> int:
        """Get the last sequence number in the journal."""
        if not self._events:
            self.load_journal()
        return self._events[-1].sequence if self._events else -1

    def filter_events(self, event_types: list[str]) -> list[ReplayEvent]:
        """Filter events by type."""
        return [e for e in self._events if e.event_type in event_types]

    def export_replay(self, output_path: str) -> None:
        """Export replay log to JSON."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([
                {
                    "event_type": e.event_type,
                    "payload": e.payload,
                    "timestamp": e.timestamp,
                    "sequence": e.sequence,
                }
                for e in self._events
            ], f, indent=2)
