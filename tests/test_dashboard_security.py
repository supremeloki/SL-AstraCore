r"""Cross-origin requests must not be able to drive the dashboard.

Every state-changing route is a GET with a `path` parameter, which auto-registered
and indexed an arbitrary directory. Any page the user happened to have open could
then pull e.g. C:\ into the graph (`<img src="http://localhost:8780/api/context?path=C:/">`)
and, because /api/patch/apply is confined to *registered* roots, write into it.
Registration is now explicit and foreign Origins are refused.
"""

import pytest
from fastapi.testclient import TestClient

import dashboard_app as da


@pytest.fixture
def client(auth_client):
    return auth_client


def test_foreign_origin_is_refused(client, tmp_path):
    for endpoint in ("/api/status", "/api/repos", "/api/explorer", "/api/context"):
        response = client.get(endpoint, params={"path": str(tmp_path)}, headers={"origin": "http://evil.example"})
        assert response.status_code == 403, f"{endpoint} accepted a cross-origin request"
        assert "cross-origin" in response.text


def test_local_origin_is_allowed(client):
    assert client.get("/api/status", headers={"origin": "http://localhost:8780"}).status_code == 200
    assert client.get("/api/status", headers={"origin": "http://127.0.0.1:8780"}).status_code == 200


def test_no_origin_header_is_allowed(client):
    """A direct navigation (curl, address bar) sends no Origin; that is legitimate."""
    assert client.get("/api/status").status_code == 200


def test_get_endpoints_do_not_register_unknown_paths(client, tmp_path):
    probe = tmp_path / "secret.txt"
    probe.write_text("sensitive", encoding="utf-8")
    before = len(da._orchestrator.list_repos())

    for endpoint in ("/api/context", "/api/execution", "/api/graph/sample", "/api/graph/node"):
        response = client.get(endpoint, params={"path": str(tmp_path), "query": "x", "node_id": "x"})
        assert response.status_code == 404, f"{endpoint} registered an unregistered repo"

    assert len(da._orchestrator.list_repos()) == before, "a GET created a repo registration"


def test_explicit_registration_still_works(client, tmp_path):
    (tmp_path / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    added = client.post("/api/repos/add", json={"path": str(tmp_path)})
    assert added.status_code == 200, added.text
    body = added.json()
    assert body["status"] == "active"
    assert body["files"] == 1

    # and it is now readable through the GET endpoints
    assert client.get("/api/context", params={"path": str(tmp_path), "query": "main"}).status_code == 200


# ── Access token ────────────────────────────────────────────────────────
#
# "Local" is not a boundary: any page open in the browser can reach
# localhost:8780, and the dashboard indexes arbitrary directories and writes
# into registered ones. A per-process token, minted at startup and sent as a
# bearer header, closes that.


def test_every_api_route_requires_a_token():
    from fastapi.routing import APIRoute

    unguarded = []
    for route in da.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in da._PUBLIC_PATHS or route.path.startswith("/static"):
            continue
        response = TestClient(da.app, raise_server_exceptions=False).get(route.path)
        if response.status_code != 401:
            unguarded.append(route.path)
    assert not unguarded, f"routes reachable without a token: {unguarded}"


def test_wrong_token_is_refused(client):
    response = client.get("/api/status", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_valid_token_is_accepted(auth_client):
    assert auth_client.get("/api/status").status_code == 200


def test_shell_hands_the_token_to_the_spa():
    """The first navigation has no header, so / must return the token in the body."""
    plain = TestClient(da.app, raise_server_exceptions=False)
    response = plain.get("/")
    assert response.status_code == 401
    assert response.json().get("token"), "the shell must hand the token to the SPA"


def test_assets_stay_public():
    plain = TestClient(da.app, raise_server_exceptions=False)
    assert plain.get("/manifest.webmanifest").status_code == 200
    assert plain.get("/favicon.ico").status_code == 200
