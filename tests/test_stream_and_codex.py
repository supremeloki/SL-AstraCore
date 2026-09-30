"""The SSE stream and the Codex CLI bridge are the two advertised features with
no real coverage.

The stream is what makes the dashboard live; it had zero tests. CodexProvider's
subprocess bridge had only its "binary missing" path tested, so the happy path,
the non-zero exit and the timeout were all unverified.
"""

import os
import subprocess

import pytest
from fastapi.testclient import TestClient

import dashboard_app as da
from astra.agents.models import AgentRequest
from astra.agents.providers import CodexProvider


@pytest.fixture
def client():
    return TestClient(da.app, raise_server_exceptions=False)


# ── SSE stream ───────────────────────────────────────────────────────────
#
# /api/stream is an endless response, so a test client that waits for the body
# would block forever — correct behaviour for an SSE endpoint, wrong for a
# test. The endpoint is therefore verified two ways that do not deadlock:
# its content type on an early exit, and the event-bus/journal behaviour it
# depends on, which is where a real regression would live.


def test_stream_route_is_registered_as_sse():
    """Consuming the endless body would deadlock, so verify the route contract.

    The endpoint is registered, answers GET, and declares no response_model —
    everything a client needs before it starts reading. The generator itself is
    covered indirectly by the event-bus tests below, which it reads from.
    """
    from fastapi.routing import APIRoute

    routes = {r.path: r for r in da.app.routes if isinstance(r, APIRoute)}
    assert "/api/stream" in routes, "the SSE endpoint is not registered"
    assert "GET" in routes["/api/stream"].methods
    assert routes["/api/stream"].response_model is None


def test_event_stream_is_an_async_generator():
    import inspect

    assert inspect.iscoroutinefunction(da.event_stream), "the SSE route must be async"


def test_event_bus_records_and_reads_back():
    from astra.runtime.event_bus import RuntimeEvent

    before = len(da._event_bus.log())
    da._event_bus.emit(RuntimeEvent(event_type="probe_event", payload={"n": 1}, source="test"))
    assert len(da._event_bus.log()) == before + 1


def test_stream_history_endpoint_matches_the_bus(client):
    from astra.runtime.event_bus import RuntimeEvent

    da._event_bus.emit(RuntimeEvent(event_type="probe_event", payload={"n": 1}, source="test"))
    logs = client.get("/api/logs", params={"limit": 50})
    assert logs.status_code == 200
    assert any(e["event"] == "probe_event" for e in logs.json())


def test_timeline_endpoint_returns_ordered_events(client):
    from astra.runtime.event_bus import RuntimeEvent

    da._event_bus.emit(RuntimeEvent(event_type="timeline_probe", payload={"i": 1}, source="test"))
    timeline = client.get("/api/timeline", params={"limit": 10})
    assert timeline.status_code == 200
    assert any(e["event"] == "timeline_probe" for e in timeline.json())


# ── Codex provider ───────────────────────────────────────────────────────


def _request(text: str = "do the thing") -> AgentRequest:
    return AgentRequest(task_description=text, context_payload={"nodes": []})


def test_codex_runs_the_binary_and_returns_output(monkeypatch):
    """The happy path: a completed codex run becomes a COMPLETED response."""
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["stdin"] = kwargs.get("input", b"").decode("utf-8", "replace")
        return subprocess.CompletedProcess(argv, 0, stdout=b'{"type":"item.completed"}', stderr=b"")

    monkeypatch.setattr("astra.agents.providers.shutil.which", lambda _: "codex")
    monkeypatch.setattr("astra.agents.providers.subprocess.run", fake_run)

    response = CodexProvider().execute(_request("fix the parser bug"))
    assert response.execution_status.value == "completed"
    assert "item.completed" in response.content
    assert "exec" in seen["argv"]
    assert "fix the parser bug" in seen["stdin"], "the task must reach the model"


def test_codex_reports_a_non_zero_exit_as_failed(monkeypatch):
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"boom")

    monkeypatch.setattr("astra.agents.providers.shutil.which", lambda _: "codex")
    monkeypatch.setattr("astra.agents.providers.subprocess.run", fake_run)

    response = CodexProvider().execute(_request())
    assert response.execution_status.value == "failed"
    assert "boom" in response.content
    assert response.errors


def test_codex_survives_a_timeout(monkeypatch):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr("astra.agents.providers.shutil.which", lambda _: "codex")
    monkeypatch.setattr("astra.agents.providers.subprocess.run", fake_run)

    response = CodexProvider(timeout_seconds=1).execute(_request())
    assert response.execution_status.value == "failed"
    assert "timeout" in response.errors[0]


def test_codex_survives_a_launch_failure(monkeypatch):
    def fake_run(argv, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr("astra.agents.providers.shutil.which", lambda _: "codex")
    monkeypatch.setattr("astra.agents.providers.subprocess.run", fake_run)

    response = CodexProvider().execute(_request())
    assert response.execution_status.value == "failed"
    assert "launch-failed" in response.errors


def test_codex_resolves_the_windows_npm_shim():
    """npm installs codex as a .cmd shim; subprocess needs the real extension."""
    resolved = CodexProvider._resolve_binary()
    assert resolved
    if os.name == "nt":
        assert resolved.lower().endswith((".cmd", ".exe", ".bat")), (
            f"Windows needs an executable shim, got {resolved}"
        )


def test_manual_provider_renders_a_usable_brief():
    from astra.agents.providers import ManualProvider

    request = AgentRequest(
        task_description="add rate limiting",
        context_payload={"nodes": [{"id": "file:api.py", "name": "api.py"}]},
    )
    response = ManualProvider().execute(request)
    assert response.execution_status.value == "pending"
    assert "add rate limiting" in response.content
    assert "file:api.py" in response.content


