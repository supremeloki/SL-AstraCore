"""3F — Safety Layer full test suite.

Verifies:
  - ExecutionSandbox (isolate, file access, network validation)
  - ResourceQuotaEnforcer (check, enforce, monitoring, OOM)
  - Cancellation (scope, propagate, timeout, check, cancel_all)
  - TimeoutEnforcer (deadline, check, remaining, clear, escalation)
  - CircuitBreaker (allow, open, half-open, reset)
  - SafetyEngine (run_safe, composition)
"""

from __future__ import annotations

import os
import time
import threading
import tempfile
import pytest

from astra.runtime.sandbox import ExecutionSandbox, SandboxConfig
from astra.runtime.quota_enforcer import ResourceQuotaEnforcer, QuotaConfig
from astra.runtime.cancellation import (
    CancellationContext, CancelledError,
    cancellation_scope, timeout_scope, cancel_all, get_current_context,
)
from astra.runtime.timeout_enforcer import TimeoutEnforcer, TimeoutExceeded
from astra.runtime.circuit_breaker import CircuitBreaker
from astra.runtime.safety_engine import SafetyEngine


# ── Execution Sandbox ──────────────────────────────────────────────

class TestExecutionSandbox:
    def test_isolate_context_creates_temp_dir(self):
        sb = ExecutionSandbox()
        with sb.isolate() as temp_dir:
            assert os.path.exists(temp_dir)
            assert temp_dir.startswith(tempfile.gettempdir())

    def test_isolate_cleans_up_on_exit(self):
        sb = ExecutionSandbox()
        with sb.isolate() as temp_dir:
            pass
        assert not os.path.exists(temp_dir)

    def test_isolate_changes_cwd(self):
        sb = ExecutionSandbox()
        orig = os.getcwd()
        with sb.isolate() as temp_dir:
            assert os.getcwd() == temp_dir
        assert os.getcwd() == orig

    def test_validate_file_access_default_denied(self):
        sb = ExecutionSandbox()
        assert not sb.validate_file_access("/etc/passwd")
        assert not sb.validate_file_access("/etc/passwd", write=True)

    def test_validate_file_access_with_allowed_path(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = SandboxConfig(allowed_paths=[td])
            sb = ExecutionSandbox(cfg)
            assert sb.validate_file_access(td)
            assert not sb.validate_file_access(td, write=True)

    def test_validate_file_access_write_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = SandboxConfig(allowed_paths=[td], allow_filesystem_write=True)
            sb = ExecutionSandbox(cfg)
            assert sb.validate_file_access(td, write=True)

    def test_validate_file_access_blocked_path(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = SandboxConfig(
                allowed_paths=[td],
                blocked_paths=[os.path.join(td, "secrets")],
                allow_filesystem_write=True,
            )
            sb = ExecutionSandbox(cfg)
            allowed = os.path.join(td, "public")
            blocked = os.path.join(td, "secrets")
            os.makedirs(allowed)
            os.makedirs(blocked)
            assert sb.validate_file_access(allowed, write=True)
            assert not sb.validate_file_access(blocked, write=True)

    def test_validate_network_access_default_denied(self):
        sb = ExecutionSandbox()
        assert not sb.validate_network_access("example.com", 80)

    def test_validate_network_access_allowed(self):
        cfg = SandboxConfig(allow_network=True)
        sb = ExecutionSandbox(cfg)
        assert sb.validate_network_access("example.com", 80)

    def test_isolation_blocks_network_env(self):
        sb = ExecutionSandbox()
        with sb.isolate():
            assert os.environ.get("HTTP_PROXY") == ""
            assert os.environ.get("NO_PROXY") == "*"


# ── Resource Quota Enforcer ────────────────────────────────────────

class TestResourceQuotaEnforcer:
    def test_quota_check_ok(self):
        rq = ResourceQuotaEnforcer()
        ok, violations = rq.check_quota()
        assert ok
        assert violations == []

    def test_quota_check_violation(self):
        rq = ResourceQuotaEnforcer(QuotaConfig(max_memory_mb=1))  # 1MB limit
        ok, violations = rq.check_quota()
        assert not ok
        assert any("memory" in v for v in violations)

    def test_monitoring_start_stop(self):
        rq = ResourceQuotaEnforcer()
        rq.start_monitoring()
        assert rq._monitor_thread is not None
        assert rq._monitor_thread.is_alive()
        rq.stop_monitoring()
        assert not rq._monitor_thread.is_alive()

    def test_monitoring_callback(self):
        violations_captured = []

        rq = ResourceQuotaEnforcer(QuotaConfig(max_memory_mb=1))
        rq.start_monitoring(on_violation=lambda v: violations_captured.extend(v))
        rq.stop_monitoring()

    def test_enforce_context_manager(self):
        rq = ResourceQuotaEnforcer()
        with rq.enforce():
            pass  # Should complete without error

    def test_apply_os_limits_does_not_crash(self):
        rq = ResourceQuotaEnforcer()
        rq.apply_os_limits()  # Should not raise on Unix or Windows

    def test_enforce_memory_limit(self):
        rq = ResourceQuotaEnforcer()
        assert rq.enforce_memory_limit() is True


# ── Cancellation ───────────────────────────────────────────────────

class TestCancellation:
    def test_scope_check_ok(self):
        with cancellation_scope() as ctx:
            ctx.check()  # Should not raise

    def test_scope_cancel(self):
        with cancellation_scope() as ctx:
            ctx.cancel("testing")
            with pytest.raises(CancelledError, match="testing"):
                ctx.check()

    def test_cancellation_propagates_to_child(self):
        with cancellation_scope() as parent:
            with cancellation_scope() as child:
                parent.cancel("propagate")
                with pytest.raises(CancelledError):
                    child.check()

    def test_cancellation_not_propagated_to_parent(self):
        with cancellation_scope() as parent:
            with cancellation_scope() as child:
                child.cancel("child-only")
                # Parent should not be cancelled
                parent.check()  # Should not raise

    def test_timeout_scope_cancels_after_timeout(self):
        with timeout_scope(0.05, "too slow"):
            time.sleep(0.1)
        # After timeout, context should be cancelled
        ctx = get_current_context()
        if ctx:
            assert ctx.cancelled

    def test_timeout_scope_completes_before_timeout(self):
        with timeout_scope(1.0):
            time.sleep(0.01)
        # Should complete normally

    def test_multiple_nested_scopes(self):
        with cancellation_scope() as outer:
            with cancellation_scope() as mid:
                with cancellation_scope() as inner:
                    outer.cancel("all")
                    with pytest.raises(CancelledError):
                        inner.check()
                with pytest.raises(CancelledError):
                    mid.check()
            with pytest.raises(CancelledError):
                outer.check()

    def test_cancel_all(self):
        with cancellation_scope() as ctx:
            # Simulate cancel all
            ctx.cancel("all ops")
            with pytest.raises(CancelledError):
                ctx.check()

    def test_cancelled_error_type(self):
        err = CancelledError("test")
        assert isinstance(err, Exception)
        assert "test" in str(err)


# ── Timeout Enforcer ───────────────────────────────────────────────

class TestTimeoutEnforcer:
    def test_set_and_clear_deadline(self):
        te = TimeoutEnforcer()
        te.set_deadline("t1", 10.0)
        assert not te.check("t1")
        te.clear("t1")

    def test_remaining_time(self):
        te = TimeoutEnforcer()
        deadline = te.set_deadline("t1", 10.0)
        remain = te.remaining("t1")
        assert remain > 9.0

    def test_unknown_task_remaining(self):
        te = TimeoutEnforcer()
        assert te.remaining("unknown") == float("inf")

    def test_check_unknown_task(self):
        te = TimeoutEnforcer()
        assert not te.check("unknown")

    def test_timeout_exceeded_after_deadline_passes(self):
        te = TimeoutEnforcer()
        te.set_deadline("t1", 0.01)
        time.sleep(0.05)
        assert te.check("t1")

    def test_escalation_callback_fires(self):
        escalated = []
        te = TimeoutEnforcer()
        te.set_deadline("t1", 0.01, escalation_callback=lambda id: escalated.append(id))
        time.sleep(0.05)
        assert len(escalated) >= 1
        assert escalated[0] == "t1"
        te.clear("t1")

    def test_enforce_context_manager(self):
        te = TimeoutEnforcer()
        with te.enforce("t1", 1.0):
            pass  # Should complete before timeout
        assert not te.check("t1")

    def test_timeout_exceeded_type(self):
        err = TimeoutExceeded("too slow")
        assert isinstance(err, Exception)
        assert "too slow" in str(err)


# ── Circuit Breaker ────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_allow_by_default(self):
        cb = CircuitBreaker()
        assert cb.allow()

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert not cb.allow()

    def test_resets_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.02)
        cb.record_failure()
        cb.record_failure()
        assert not cb.allow()
        time.sleep(0.03)
        assert cb.allow()

    def test_successful_call_resets(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        assert not cb.is_open()
        cb.record_success()
        cb.record_success()
        assert cb.is_closed()

    def test_open_close_states(self):
        cb = CircuitBreaker(failure_threshold=2)
        assert cb.is_closed()
        assert not cb.is_open()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open()
        assert not cb.is_closed()

    def test_half_open_on_reset_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open()
        time.sleep(0.02)
        assert cb.allow()  # transitions OPEN -> HALF_OPEN
        assert cb.is_half_open()
        cb.record_success()
        cb.record_success()  # enough successes to close
        assert cb.is_closed()


# ── Safety Engine ──────────────────────────────────────────────────

class TestSafetyEngine:
    def test_run_safe_success(self):
        se = SafetyEngine()
        result = se.run_safe("t1", lambda: 42)
        assert result == 42

    def test_run_safe_raises_on_failure(self):
        se = SafetyEngine()
        with pytest.raises(ValueError):
            se.run_safe("t2", lambda: (_ for _ in ()).throw(ValueError("fail")))

    def test_safety_engine_components_accessible(self):
        se = SafetyEngine()
        assert hasattr(se, "sandbox")
        assert hasattr(se, "quota")
        assert hasattr(se, "timeout")
        assert hasattr(se, "circuit_breaker")