"""The replay engine, including the paths that only happen after a crash.

A journal is append-only and written by a process that can be killed
mid-write, so the damaged line is always at the end and everything before it
is intact. Reading it used to raise, which turned one interrupted write into
an unreadable journal for good.
"""

import json

import pytest

from astra.runtime.replay_engine import ReplayEngine


def write_journal(path, entries):
    lines = [
        json.dumps({
            "event_type": name,
            "payload": payload,
            "timestamp": index,
            "sequence": index,
        })
        for index, (name, payload) in enumerate(entries)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_a_well_formed_journal_loads_in_order(tmp_path):
    journal = write_journal(tmp_path / "j.jsonl", [("A", {"n": 1}), ("B", {"n": 2})])
    events = ReplayEngine(str(journal)).load_journal()

    assert [e.event_type for e in events] == ["A", "B"]
    assert [e.sequence for e in events] == [0, 1]
    assert events[0].payload == {"n": 1}


def test_a_truncated_final_line_does_not_lose_the_journal(tmp_path):
    """A process killed mid-write leaves half a line."""
    journal = write_journal(tmp_path / "j.jsonl", [("A", {}), ("B", {}), ("C", {})])
    with journal.open("a", encoding="utf-8") as handle:
        handle.write('{"event_type": "D", "payl')

    engine = ReplayEngine(str(journal))
    events = engine.load_journal()

    assert [e.event_type for e in events] == ["A", "B", "C"], (
        "a truncated line cost the events before it"
    )
    assert engine.skipped_lines == 1


def test_blank_lines_are_not_counted_as_skipped(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"event_type": "A", "payload": {}, "timestamp": 1.0, "sequence": 1})
        + "\n\n\n"
        + json.dumps({"event_type": "B", "payload": {}, "timestamp": 2.0, "sequence": 2})
        + "\n",
        encoding="utf-8",
    )
    engine = ReplayEngine(str(journal))
    assert len(engine.load_journal()) == 2
    assert engine.skipped_lines == 0


def test_a_json_value_that_is_not_an_object_is_skipped(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text('["not", "an", "object"]\n', encoding="utf-8")
    engine = ReplayEngine(str(journal))

    assert engine.load_journal() == []
    assert engine.skipped_lines == 3, "each unusable record is counted, not just the file"


def test_a_line_holding_a_bare_value_is_skipped(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text('42\n"a string"\n', encoding="utf-8")
    engine = ReplayEngine(str(journal))

    assert engine.load_journal() == []
    assert engine.skipped_lines == 2


def test_a_missing_journal_is_empty_not_an_error(tmp_path):
    engine = ReplayEngine(str(tmp_path / "never-written.jsonl"))
    assert engine.load_journal() == []
    assert engine.skipped_lines == 0


def test_journal_entries_use_their_own_field_names(tmp_path):
    """ExecutionJournal writes type/data, not event_type/payload."""
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"type": "SCAN_STARTED", "data": {"repo": "x"},
                    "timestamp": 1.0, "sequence": 1}) + "\n",
        encoding="utf-8",
    )
    events = ReplayEngine(str(journal)).load_journal()

    assert events[0].event_type == "SCAN_STARTED"
    assert events[0].payload == {"repo": "x"}


def test_an_iso_timestamp_is_converted(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"event_type": "A", "payload": None,
                    "timestamp": "2026-01-01T00:00:00", "sequence": 1}) + "\n",
        encoding="utf-8",
    )
    events = ReplayEngine(str(journal)).load_journal()

    assert events[0].timestamp > 0


def test_an_unparsable_timestamp_becomes_zero(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"event_type": "A", "payload": None,
                    "timestamp": "not a date", "sequence": 1}) + "\n",
        encoding="utf-8",
    )
    assert ReplayEngine(str(journal)).load_journal()[0].timestamp == 0.0


# ── the two API traps ──────────────────────────────────────────────────────

def test_replay_from_sequence_loads_the_journal_itself(tmp_path):
    """The caller asking "replay from where I left off" has not loaded it yet."""
    journal = write_journal(tmp_path / "j.jsonl", [("A", {}), ("B", {}), ("C", {})])
    engine = ReplayEngine(str(journal))

    seen = []
    count = engine.replay_from_sequence(1, seen.append)

    assert count == 2
    assert [e.event_type for e in seen] == ["B", "C"]


def test_replay_loads_the_journal_itself(tmp_path):
    journal = write_journal(tmp_path / "j.jsonl", [("A", {}), ("B", {})])
    engine = ReplayEngine(str(journal))

    seen = []
    assert engine.replay(seen.append) == 2
    assert len(seen) == 2


def test_get_last_sequence_on_an_empty_journal_is_zero(tmp_path):
    """It feeds replay_from_sequence, and -1 is below every real sequence."""
    engine = ReplayEngine(str(tmp_path / "missing.jsonl"))
    assert engine.get_last_sequence() == 0


def test_get_last_sequence_on_a_written_journal(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"event_type": "A", "payload": {}, "timestamp": 1.0, "sequence": 7}) + "\n",
        encoding="utf-8",
    )
    assert ReplayEngine(str(journal)).get_last_sequence() == 7


def test_filter_events_by_type(tmp_path):
    journal = write_journal(
        tmp_path / "j.jsonl", [("A", {}), ("B", {}), ("A", {}), ("C", {})]
    )
    # No load_journal: filtering is the obvious way to use this, so it has to
    # work on a fresh engine.
    engine = ReplayEngine(str(journal))
    assert [e.sequence for e in engine.filter_events(["A"])] == [0, 2]


def test_export_round_trips(tmp_path):
    journal = write_journal(tmp_path / "j.jsonl", [("A", {"n": 1}), ("B", {"n": 2})])
    engine = ReplayEngine(str(journal))
    engine.load_journal()

    out = tmp_path / "export.json"
    engine.export_replay(str(out))
    exported = json.loads(out.read_text(encoding="utf-8"))

    assert [e["event_type"] for e in exported] == ["A", "B"]
    assert exported[0]["payload"] == {"n": 1}

    # An exported journal reloads as the same events.
    reloaded = ReplayEngine(str(out)).load_journal()
    assert [e.event_type for e in reloaded] == ["A", "B"]


def test_export_of_an_empty_journal_writes_an_empty_list(tmp_path):
    out = tmp_path / "export.json"
    ReplayEngine(str(tmp_path / "missing.jsonl")).export_replay(str(out))
    assert json.loads(out.read_text(encoding="utf-8")) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
