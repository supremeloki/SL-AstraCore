"""Shared test configuration.

The dashboard mints an access token at import time and refuses requests
without it. Tests pin a known token and send it, so they exercise the real
guard rather than switching it off.
"""

import os
import tempfile

os.environ.setdefault("ASTRA_TOKEN", "test-token")

# Every orchestrator writes a per-repo DuckDB under ASTRA_HOME. Left unset they
# share the real ~/.astra, so a test run left 1,700+ databases behind and two
# runs collided on the same files — DuckDB takes an exclusive lock, which is
# how the Windows CI job failed. Point it at a throwaway directory instead.
os.environ.setdefault(
    "ASTRA_HOME", os.path.join(tempfile.gettempdir(), "astra_pytest_home")
)

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
