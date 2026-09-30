"""Dashboard API tests: validation, metrics wiring, timestamps, replay round-trip."""

import os
import tempfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import dashboard_app
from astra.runtime.event_bus import EventBus, RuntimeEvent


@pytest.fixture(scope="module")
def client():
    return TestClient(dashboard_app.app)


class TestReposAddValidation:
    def test_bogus_path_returns_400(self, client):
        resp = client.post("/api/repos/add", json={"path": "Z:/definitely/not/a/real/dir_xyz"})
        assert resp.status_code == 400

    def test_missing_path_returns_error(self, client):
        resp = client.post("/api/repos/add", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


class TestMetricsWiring:
    def test_metrics_nonempty_after_activity(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "pkg"))
            with open(os.path.join(tmp, "pkg", "m.py"), "w") as f:
                f.write("x = 1\n")
            add = client.post("/api/repos/add", json={"path": tmp})
            assert add.status_code == 200
            snap = client.get("/api/metrics/snapshot").json()
            assert snap, "metrics snapshot should not be empty after activity"
            status = client.get("/api/status").json()
            assert status["metrics"]["counters"].get("repos.added", 0) >= 1


class TestTimestamps:
    def test_timeline_iso_timestamps(self, client):
        timeline = client.get("/api/timeline").json()
        assert timeline, "timeline should have events after activity"
        for entry in timeline:
            ts = entry["timestamp"]
            assert ts, "timestamp must be present"
            datetime.fromisoformat(ts)

    def test_runtime_event_has_utc_default(self):
        e = RuntimeEvent(event_type="t", payload=None)
        assert e.timestamp.tzinfo is not None

    def test_control_plane_emits_typed_events(self):
        from astra.dashboard.control_plane import DashboardControlPlane

        bus = EventBus()
        received = []
        bus.subscribe("SCAN_STARTED", lambda ev: received.append(ev))
        cp = DashboardControlPlane(event_bus=bus)
        cp.emit_scan_started({"repo": "r"})
        assert len(received) == 1
        assert received[0].event_type == "SCAN_STARTED"
        # SCAN_PROGRESS is emitted by build(), not by emit_scan_started.
        assert not any(ev.event_type == "SCAN_PROGRESS" for ev in bus.log())


class TestReplayRoundTrip:
    def test_patch_apply_journaled_and_replayed(self, client, monkeypatch):
        # Confine journal + repo to a temp dir so we don't touch the real one.
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setattr(
                dashboard_app,
                "_journal",
                dashboard_app.ExecutionJournal(os.path.join(tmp, "journal.jsonl")),
            )
            src = os.path.join(tmp, "app.py")
            with open(src, "w") as f:
                f.write("value = 1\n")
            # Register the repo so _confine_to_registered_repo allows the write.
            reg = client.post("/api/repos/add", json={"path": tmp})
            assert reg.status_code == 200

            applied = client.post("/api/patch/apply", json={
                "path": tmp,
                "file_path": "app.py",
                "old_text": "value = 1",
                "new_text": "value = 2",
            })
            assert applied.json()["status"] == "applied"
            assert open(src).read() == "value = 2\n"

            entries = client.get("/api/executions/journal").json()
            patch_entries = [e for e in entries if e["type"] == "patch_apply"]
            assert patch_entries, "patch_apply must be journaled"

            replay = client.post("/api/executions/replay", json={"from_sequence": patch_entries[0]["sequence"]})
            body = replay.json()
            assert body["status"] == "replayed"
            assert body["count"] >= 1
            types = [e["event_type"] for e in body["events"]]
            assert "patch_apply" in types
