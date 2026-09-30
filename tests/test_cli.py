"""Does the installed command work?

The CLI is the documented entry point and had no coverage. These run it the
way a user does — a real interpreter through the console-script entry point —
because the bug this caught only appears there: setuptools calls the target
and throws away its return value, so a failed index exited 0.

Every case runs in one subprocess because starting an interpreter costs about
1.8s on Windows, and five of them took 18s of a 90-second suite — which is
the difference between a suite that fits in a runner's budget and one that
does not.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Run once, in a child interpreter: build a sample repo, then invoke the
# console entry point once per case and report code + output for each.
RUNNER = r"""
import io, json, os, sys, tempfile
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, sys.argv[1])

repo = tempfile.mkdtemp(prefix="astra_cli_")
os.makedirs(os.path.join(repo, "pkg"), exist_ok=True)
with open(os.path.join(repo, "pkg", "billing.py"), "w") as handle:
    handle.write(json.loads(sys.argv[3]))

os.environ["ASTRA_TOKEN"] = "test-token"
os.environ["ASTRA_HOME"] = os.path.join(repo, "home")

results = {}
for name, argv in json.loads(sys.argv[2]).items():
    from astra.cli import console_main

    out, err = io.StringIO(), io.StringIO()
    sys.argv = ["astra", *[a.format(repo=repo) for a in argv]]
    try:
        with redirect_stdout(out), redirect_stderr(err):
            console_main()
        results[name] = {"code": 0, "out": out.getvalue(), "err": err.getvalue()}
    except SystemExit as exc:
        results[name] = {"code": exc.code, "out": out.getvalue(), "err": err.getvalue()}
    except BaseException as exc:  # noqa: BLE001 - a crash is a result
        results[name] = {"code": -1, "out": out.getvalue(), "err": repr(exc)}

print("<<<RESULTS>>>" + json.dumps(results))
"""

CASES = {
    "help": ["--help"],
    "index": ["index", "{repo}"],
    "context": ["context", "{repo}", "how does charging work"],
    "serve_help": ["serve", "--help"],
    "bad_repo": ["index", "{repo}/does-not-exist"],
    "bad_invocation": ["context"],
}

BILLING = json.dumps(
    '"""Charging customers."""\n\n\ndef charge(amount):\n    return amount\n'
)


@pytest.fixture(scope="module")
def cli():
    result = subprocess.run(
        [sys.executable, "-c", RUNNER, str(REPO), json.dumps(CASES), BILLING],
        capture_output=True, text=True, cwd=str(REPO), timeout=300,
        env={**os.environ, "ASTRA_HOME": tempfile.mkdtemp(prefix="astra_cli_home_")},
    )
    marker = "<<<RESULTS>>>"
    assert marker in result.stdout, (
        f"the runner produced no results; stdout={result.stdout[-400:]} "
        f"stderr={result.stderr[-600:]}"
    )
    return json.loads(result.stdout.split(marker, 1)[1])


def test_help_lists_the_subcommands(cli):
    assert cli["help"]["code"] == 0
    for command in ("index", "context", "serve"):
        assert command in cli["help"]["out"], f"{command} is not offered"


def test_index_then_context_on_a_small_repo(cli):
    assert cli["index"]["code"] == 0, cli["index"]["err"]
    assert "status=active" in cli["index"]["out"], cli["index"]["out"]
    assert cli["context"]["code"] == 0, cli["context"]["err"]
    assert "billing.py" in cli["context"]["out"], cli["context"]["out"][-400:]


def test_a_failed_index_exits_nonzero(cli):
    """The console script must propagate the failure, not swallow it."""
    assert cli["bad_repo"]["code"] != 0, "a failed index exited 0"
    assert "Traceback" not in cli["bad_repo"]["err"], "it should fail cleanly"


def test_a_bad_invocation_exits_nonzero(cli):
    assert cli["bad_invocation"]["code"] != 0
    assert "Traceback" not in cli["bad_invocation"]["err"]


def test_serve_help_needs_no_repository(cli):
    assert cli["serve_help"]["code"] == 0
    assert "--port" in cli["serve_help"]["out"]
