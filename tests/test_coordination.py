"""3E — Autonomous Runtime Coordination test suite.

Verifies:
  - AdaptiveScheduler (priority, backpressure, enqueue/dequeue, delay)
  - ResourceManager (quotas, can_accept_task, timeout, memory)
  - TaskArbitrator (concurrency limits, agent load, conflict resolution)
  - QueueBalancer (register, heartbeat, select_worker, task_completed)
  - CoordinationEngine (submit_task, complete_task, stats)
"""

from __future__ import annotations

import time
import pytest

from astra.runtime.scheduler import AdaptiveScheduler, Priority, ScheduledTask
from astra.runtime.resources import ResourceManager, ResourceQuota, get_total_memory_mb
from astra.runtime.arbitration import TaskArbitrator, AgentRequest, ArbitrationDecision
from astra.runtime.queue_balancer import QueueBalancer, WorkerStatus
from astra.runtime.coordination import CoordinationEngine


# ── Scheduler ──────────────────────────────────────────────────────


class TestAdaptiveScheduler:
    def test_enqueue_and_dequeue(self):
        s = AdaptiveScheduler()
        s.enqueue("t1", "index")
        task = s.dequeue()
        assert task is not None
        assert task.task_id == "t1"

    def test_priority_ordering(self):
        s = AdaptiveScheduler()
        s.enqueue("low", "index", priority=Priority.LOW)
        s.enqueue("high", "index", priority=Priority.HIGH)
        t1 = s.dequeue()
        assert t1.task_id == "high"
        t2 = s.dequeue()
        assert t2.task_id == "low"

    def test_delay_scheduling(self):
        s = AdaptiveScheduler()
        s.enqueue("delayed", "index", delay=10.0)
        # Should not be dequeued yet
        assert s.dequeue(time.time()) is None
        # Should be dequeued after delay
        assert s.dequeue(time.time() + 11) is not None

    def test_backpressure(self):
        s = AdaptiveScheduler(max_queue_depth=10)
        for i in range(5):
            s.enqueue(f"t{i}", "index")
        assert s.backpressure() == 0.5

    def test_queue_full_raises(self):
        s = AdaptiveScheduler(max_queue_depth=2)
        s.enqueue("a", "index")
        s.enqueue("b", "index")
        with pytest.raises(RuntimeError, match="Queue full"):
            s.enqueue("c", "index")

    def test_remove_task(self):
        s = AdaptiveScheduler()
        s.enqueue("a", "index")
        s.enqueue("b", "index")
        assert s.remove("a")
        task = s.dequeue()
        assert task.task_id == "b"

    def test_completed_and_failed_counts(self):
        s = AdaptiveScheduler()
        s.enqueue("a", "index")
        s.enqueue("b", "index")
        s.mark_completed("a")
        s.mark_failed("b", "timeout")
        assert s.completed_count() == 1
        assert s.failed_count() == 1


# ── Resources ──────────────────────────────────────────────────────


class TestResourceManager:
    def test_current_memory(self):
        rm = ResourceManager()
        mem = rm.current_memory_mb()
        assert mem > 0

    def test_quota_assignment(self):
        rm = ResourceManager()
        q = ResourceQuota(max_memory_mb=1024)
        rm.assign_quota("t1", q)
        rm.release_quota("t1")
        # No error

    def test_enforce_timeout(self):
        rm = ResourceManager()
        q = ResourceQuota(max_execution_seconds=0.01)
        rm.assign_quota("t1", q)
        time.sleep(0.02)
        assert rm.enforce_timeout("t1", 0.05)
        rm.release_quota("t1")

    def test_enforce_memory_within_limit(self):
        rm = ResourceManager()
        q = ResourceQuota(max_memory_mb=100000)  # huge limit
        rm.assign_quota("t1", q)
        ok, _ = rm.enforce_memory("t1")
        assert ok
        rm.release_quota("t1")

    def test_total_memory(self):
        mem = get_total_memory_mb()
        assert mem > 0


# ── Arbitration ────────────────────────────────────────────────────


class TestTaskArbitrator:
    def test_approve_when_agents_available(self):
        arb = TaskArbitrator()
        arb.register_agent("agent-1")
        req = AgentRequest(agent_id="agent-1", task_type="index")
        result = arb.request_execution(req)
        assert result.decision == ArbitrationDecision.APPROVE
        assert result.assigned_agent == "agent-1"

    def test_queue_when_concurrency_limit_reached(self):
        arb = TaskArbitrator(max_concurrent_per_type={"index": 1})
        arb.register_agent("a")
        arb.register_agent("b")
        req = AgentRequest(agent_id="a", task_type="index")
        arb.request_execution(req)
        req2 = AgentRequest(agent_id="b", task_type="index")
        result = arb.request_execution(req2)
        assert result.decision == ArbitrationDecision.QUEUE

    def test_release_task_decrements_load(self):
        arb = TaskArbitrator()
        arb.register_agent("agent-1")
        req = AgentRequest(agent_id="agent-1", task_type="index")
        arb.request_execution(req)
        assert arb.agent_load("agent-1") == 1
        arb.release_task("agent-1")
        assert arb.agent_load("agent-1") == 0

    def test_total_active(self):
        arb = TaskArbitrator()
        arb.register_agent("a")
        arb.register_agent("b")
        arb.request_execution(AgentRequest(agent_id="a", task_type="index"))
        arb.request_execution(AgentRequest(agent_id="b", task_type="parse"))
        assert arb.total_active() == 2

    def test_deny_when_no_agents(self):
        arb = TaskArbitrator()
        req = AgentRequest(agent_id="lonely", task_type="index")
        result = arb.request_execution(req)
        assert result.decision == ArbitrationDecision.DENY


# ── Queue Balancer ─────────────────────────────────────────────────


class TestQueueBalancer:
    def test_register_and_select(self):
        qb = QueueBalancer()
        qb.register_worker("w1")
        assert qb.select_worker() == "w1"

    def test_least_loaded_selection(self):
        qb = QueueBalancer()
        qb.register_worker("w1")
        qb.register_worker("w2")
        qb.heartbeat("w1", queue_depth=5, avg_latency_ms=10)
        qb.heartbeat("w2", queue_depth=1, avg_latency_ms=5)
        chosen = qb.select_worker()
        assert chosen == "w2"

    def test_task_completed_decrements_depth(self):
        qb = QueueBalancer()
        qb.register_worker("w1")
        qb.heartbeat("w1", queue_depth=3, avg_latency_ms=10)
        qb.task_completed("w1", 15.0)
        stats = qb.get_stats()
        assert stats["w1"]["queue_depth"] == 2

    def test_unregister(self):
        qb = QueueBalancer()
        qb.register_worker("w1")
        qb.unregister_worker("w1")
        assert qb.select_worker() is None

    def test_get_stats(self):
        qb = QueueBalancer()
        qb.register_worker("w1")
        stats = qb.get_stats()
        assert "w1" in stats

    def test_should_rebalance(self):
        qb = QueueBalancer(rebalance_interval=0.01)
        assert qb.should_rebalance()
        qb.rebalance()
        assert not qb.should_rebalance()


# ── Coordination Engine ────────────────────────────────────────────


class TestCoordinationEngine:
    def test_submit_task_full_flow(self):
        ce = CoordinationEngine()
        ce.balancer.register_worker("w1")
        ce.arbitration.register_agent("agent-1")
        worker, arb = ce.submit_task("t1", "index", "agent-1")
        assert worker == "w1"
        assert arb.decision == ArbitrationDecision.APPROVE

    def test_submit_task_complete_cycle(self):
        ce = CoordinationEngine()
        ce.balancer.register_worker("w1")
        ce.arbitration.register_agent("agent-1")
        worker, arb = ce.submit_task("t1", "index", "agent-1")
        ce.complete_task("t1", "agent-1", latency_ms=50.0)
        assert ce.scheduler.completed_count() == 1

    def test_submit_task_failure_cycle(self):
        ce = CoordinationEngine()
        ce.balancer.register_worker("w1")
        ce.arbitration.register_agent("agent-1")
        worker, arb = ce.submit_task("t1", "index", "agent-1")
        ce.complete_task("t1", "agent-1", latency_ms=100.0, success=False)
        assert ce.scheduler.failed_count() == 1

    def test_get_stats(self):
        ce = CoordinationEngine()
        stats = ce.get_stats()
        assert "scheduler" in stats
        assert "resources" in stats
        assert "arbitration" in stats
        assert "balancer" in stats

    def test_submit_denied_when_no_workers(self):
        ce = CoordinationEngine()
        ce.arbitration.register_agent("agent-1")
        worker, arb = ce.submit_task("t1", "index", "agent-1")
        assert worker is None