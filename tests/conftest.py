"""Shared test configuration.

The dashboard mints an access token at import time and refuses requests
without it. Tests pin a known token and send it, so they exercise the real
guard rather than switching it off.
"""

import os

os.environ.setdefault("ASTRA_TOKEN", "test-token")

import pytest  # noqa: E402


@pytest.fixture
def auth_client():
    """A TestClient that authenticates every request."""
    from fastapi.testclient import TestClient

    import dashboard_app as da

    da._ACCESS_TOKEN = os.environ["ASTRA_TOKEN"]

    class _AuthedClient(TestClient):
        def request(self, method, url, **kwargs):
            headers = dict(kwargs.pop("headers", {}) or {})
            headers.setdefault("Authorization", f"Bearer {da._ACCESS_TOKEN}")
            return super().request(method, url, headers=headers, **kwargs)

    return _AuthedClient(da.app, raise_server_exceptions=False)
