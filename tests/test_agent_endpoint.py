"""The dashboard endpoint that reviews a proposed edit.

The loop itself is covered in test_agent_loop.py. This checks the HTTP
surface: that it is reachable, that it is confined to a registered
repository, and that posting it writes nothing.
"""

import json

import pytest

import dashboard_app as da


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "billing.py").write_text(
        "def charge(amount):\n    return amount - 1\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def client(auth_client):
    return auth_client


def test_a_well_formed_edit_is_reviewed(client, repo):
    da._orchestrator.register_repo(str(repo))
    reply = json.dumps({"edits": [{
        "path": "billing.py",
        "old_text": "return amount - 1",
        "new_text": "return amount",
        "reason": "off by one",
    }]})

    response = client.post("/api/agent/propose", json={"path": str(repo), "reply": reply})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "reviewed", body
    assert body["edits"], body
    assert body["edits"][0]["path"] == "billing.py"
    assert body["risk"] in ("low", "medium", "high")


def test_proposing_writes_nothing(client, repo):
    da._orchestrator.register_repo(str(repo))
    before = (repo / "billing.py").read_text(encoding="utf-8")

    reply = json.dumps({"edits": [{
        "path": "billing.py", "old_text": "return amount - 1", "new_text": "return amount",
    }]})
    response = client.post("/api/agent/propose", json={"path": str(repo), "reply": reply})

    assert response.status_code == 200
    assert (repo / "billing.py").read_text(encoding="utf-8") == before, (
        "proposing an edit must not write it"
    )


def test_an_unanchored_edit_is_rejected(client, repo):
    da._orchestrator.register_repo(str(repo))
    reply = json.dumps({"edits": [{
        "path": "billing.py",
        "old_text": "def never_existed(): ...",
        "new_text": "pass",
    }]})

    body = client.post("/api/agent/propose", json={"path": str(repo), "reply": reply}).json()
    assert body["status"] == "rejected"
    assert any("not in the file" in w for w in body["warnings"]), body


def test_a_reply_that_is_not_json_is_rejected(client, repo):
    da._orchestrator.register_repo(str(repo))
    body = client.post(
        "/api/agent/propose", json={"path": str(repo), "reply": "sure, here you go"}
    ).json()
    assert body["status"] == "rejected"
    assert body["warnings"]


def test_a_path_outside_a_registered_repo_is_refused(client, tmp_path):
    stray = tmp_path / "elsewhere"
    stray.mkdir()
    (stray / "a.py").write_text("x = 1\n", encoding="utf-8")

    reply = json.dumps({"edits": [{"path": "a.py", "old_text": "", "new_text": "y = 2\n"}]})
    response = client.post("/api/agent/propose", json={"path": str(stray), "reply": reply})
    assert response.status_code != 200 or response.json().get("status") == "error"


def test_the_endpoint_requires_a_token(client, repo):
    """Proposing an edit must sit behind the same guard as everything else."""
    reply = json.dumps({"edits": []})
    response = client.post(
        "/api/agent/propose", json={"path": str(repo), "reply": reply},
        headers={"X-Astra-Token": "wrong"},
    )
    assert response.status_code in (401, 403), response.status_code


def test_it_appears_in_the_route_list():
    routes = {route.path for route in da.app.routes}
    assert "/api/agent/propose" in routes
