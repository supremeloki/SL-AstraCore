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
        # Lines the last load could not parse. A caller replaying a journal
        # wants to know the replay was incomplete.
        self.skipped_lines = 0

    def load_journal(self) -> list[ReplayEvent]:
        """Load events from journal file.

        Accepts both bare replay lines ({event_type, payload, timestamp,
        sequence}) and ExecutionJournal entries ({type, data, timestamp,
        sequence}).

        A process killed mid-write leaves a truncated final line, and json.loads
        raising on it made one interrupted write render the whole journal
        unreadable. An unparsable line is skipped and counted in
        self.skipped_lines; a journal is append-only, so the damage is always
        at the end and everything before it is still good.
        """
        self._events = []
        self.skipped_lines = 0
        if not os.path.exists(self._journal_path):
            return self._events

        with open(self._journal_path, encoding="utf-8", errors="replace") as f:
            content = f.read()

        # A JSON array is also accepted, because export_replay wrote one and
        # nothing could read it back: the loader only understood one object per
        # line, so every export produced a file that replayed as nothing.
        stripped = content.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                for entry in parsed:
                    self._append_event(entry)
                return self._events

        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                self.skipped_lines += 1
                continue
            self._append_event(data)
        return self._events

    def replay(self, handler: Callable[[ReplayEvent], None]) -> int:
        """Replay all events through handler."""
        count = 0
        for event in self._events_or_load():
            handler(event)
            count += 1
        return count

    def replay_from_sequence(self, from_sequence: int, handler: Callable[[ReplayEvent], None]) -> int:
        """Replay events starting from a specific sequence number."""
        # A caller that asks "replay from where I left off" has not loaded the
        # journal yet by construction, and used to get zero events back.
        count = 0
        for event in self._events_or_load():
            if event.sequence >= from_sequence:
                handler(event)
                count += 1
        return count

    def get_last_sequence(self) -> int:
        """The last sequence in the journal, or 0 when there is none.

        0 rather than -1: the result is meant to be fed back to
        replay_from_sequence, and -1 is below every real sequence, so a caller
        doing that on an empty journal gets nothing and cannot tell why.
        """
        events = self._events_or_load()
        return events[-1].sequence if events else 0

    def _append_event(self, data: Any) -> None:
        """Add one journal record, in either field naming, or skip it."""
        if not isinstance(data, dict):
            self.skipped_lines += 1
            return
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

    def _events_or_load(self) -> list[ReplayEvent]:
        """The events, loading the journal if nothing has been read yet.

        Every reader goes through this. filter_events and export_replay read
        _events directly, so a caller who never called load_journal — the
        obvious way to use them — silently got an empty result.
        """
        if not self._events:
            self.load_journal()
        return self._events

    def filter_events(self, event_types: list[str]) -> list[ReplayEvent]:
        """Filter events by type."""
        return [e for e in self._events_or_load() if e.event_type in event_types]

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
                for e in self._events_or_load()
            ], f, indent=2)
