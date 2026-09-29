"""3C — Resilience Layer test suite."""

from __future__ import annotations

import os
import tempfile
import time

from astra.runtime.retry import RetryOrchestrator
from astra.runtime.journal import ExecutionJournal
from astra.runtime.checkpoint import CheckpointManager
from astra.runtime.recovery import CrashRecovery
from astra.runtime.dead_letter import DeadLetterQueue
from astra.runtime.circuit_breaker import CircuitBreaker


class TestRetryOrchestrator:
    def test_retry_success_on_first_attempt(self):
        orchestrator = RetryOrchestrator()
        result = orchestrator.execute(lambda: 42)
        assert result == 42

    def test_retry_eventually_succeeds(self):
        orchestrator = RetryOrchestrator(max_attempts=5, base_delay=0.01)
        attempt = 0
        def flaky():
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ValueError("Not ready")
            return 99
        result = orchestrator.execute(flaky)
        assert result == 99

    def test_retry_exhausts_and_fails(self):
        orchestrator = RetryOrchestrator(max_attempts=3, base_delay=0.01)
        def always_fails():
            raise ValueError("Always fails")
        try:
            orchestrator.execute(always_fails)
            assert False, "Should raise"
        except ValueError:
            pass


class TestExecutionJournal:
    def test_journal_append_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "journal.jsonl")
            journal = ExecutionJournal(path)
            journal.log_event("test", {"key": "value"})
            events = journal.read_events()
            assert len(events) == 1
            assert events[0]["type"] == "test"
            assert events[0]["data"]["key"] == "value"

    def test_journal_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "missing.jsonl")
            journal = ExecutionJournal(path)
            assert journal.read_events() == []

    def test_journal_multiple_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "multi.jsonl")
            journal = ExecutionJournal(path)
            journal.log_event("a", {})
            journal.log_event("b", {})
            assert len(journal.read_events()) == 2


class TestCheckpointManager:
    def test_checkpoint_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            cm = CheckpointManager(tmp)
            state = {"nodes": 100, "edges": 200}
            path = cm.save("check1", state)
            assert os.path.exists(path)
            loaded = cm.load("check1")
            assert loaded == state

    def test_checkpoint_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            cm = CheckpointManager(tmp)
            cm.save("x", {"v": 1})
            cm.save("x", {"v": 2})
            loaded = cm.load("x")
            assert loaded["v"] == 2


class TestCrashRecovery:
    def test_replay_returns_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "journal.jsonl")
            journal = ExecutionJournal(path)
            journal.log_event("scan", {"files": 10})
            journal.log_event("parse", {"files": 10})
            recovery = CrashRecovery(journal)
            events = recovery.replay()
            assert len(events) == 2
            assert events[0]["type"] == "scan"
            assert events[1]["type"] == "parse"


class TestDeadLetterQueue:
    def test_push_and_list(self):
        dlq = DeadLetterQueue()
        dlq.push("timeout", {"task": "index_repo", "timeout": 30})
        dlq.push("error", {"error": "disk_full"})
        items = dlq.list()
        assert len(items) == 2
        assert items[0].reason == "timeout"
        assert items[1].reason == "error"

    def test_empty_dead_letter(self):
        dlq = DeadLetterQueue()
        assert dlq.list() == []


class TestCircuitBreaker:
    def test_circuit_breaker_allows_by_default(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.allow()

    def test_circuit_breaker_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert not cb.allow()

    def test_circuit_breaker_resets_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        assert not cb.allow()
        time.sleep(0.02)
        assert cb.allow()
