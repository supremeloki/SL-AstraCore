"""Does the installed command work?

The CLI is the documented entry point and had no coverage. These run it the
way a user does — a real subprocess through the console-script entry point —
because the bug this caught only appears there: setuptools calls the target
and throws away its return value, so a failed index exited 0.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENTRY = "from astra.cli import console_main; console_main()"


def run(*args, home=None):
    env = dict(os.environ)
    env["ASTRA_TOKEN"] = "test-token"
    if home is not None:
        env["ASTRA_HOME"] = str(home)
    return subprocess.run(
        [sys.executable, "-c", ENTRY, *args],
        capture_output=True, text=True, cwd=str(REPO), timeout=120, env=env,
    )


@pytest.fixture
def sample_repo(tmp_path):
    repo = tmp_path / "sample"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "billing.py").write_text(
        '"""Charging customers."""\n\n\ndef charge(amount):\n    return amount\n',
        encoding="utf-8",
    )
    return repo


def test_help_lists_the_subcommands():
    result = run("--help")
    assert result.returncode == 0
    for command in ("index", "context", "serve"):
        assert command in result.stdout, f"{command} is not offered"


def test_index_then_context_on_a_small_repo(sample_repo, tmp_path):
    home = tmp_path / "home"
    indexed = run("index", str(sample_repo), home=home)
    assert indexed.returncode == 0, indexed.stderr
    assert "status=active" in indexed.stdout

    asked = run("context", str(sample_repo), "how does charging work", home=home)
    assert asked.returncode == 0, asked.stderr
    assert "billing.py" in asked.stdout


def test_a_failed_index_exits_nonzero(sample_repo, tmp_path):
    """The console script must propagate the failure, not swallow it."""
    result = run("index", str(sample_repo / "does-not-exist"), home=tmp_path / "home")
    assert result.returncode != 0, "a failed index exited 0"
    assert "Traceback" not in result.stderr, "it should fail cleanly, not crash"


def test_a_bad_invocation_exits_nonzero():
    result = run("context")
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_serve_help_needs_no_repository():
    result = run("serve", "--help")
    assert result.returncode == 0
    assert "--port" in result.stdout
