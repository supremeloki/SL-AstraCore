"""Reproduce the Windows CI job locally.

The runner differs from this shell in four ways that matter: it checks out
with LF under core.autocrlf=true, HOME is empty, ASTRA_HOME does not exist
yet, and the working directory is a fresh clone. Running the suite under
those conditions is the only way to find the failure without the log.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SEP = chr(92)
REPO = Path("F:" + SEP + "SL-AstraCore")


def run(label, env_extra, cwd=REPO):
    env = dict(os.environ)
    env.update(env_extra)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(cwd), env=env,
    )
    lines = [l for l in result.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
    print(f"  {label:34} {lines[-1][:70] if lines else result.stdout[-200:]}")
    for line in result.stdout.splitlines():
        if line.startswith(("FAILED", "ERROR")):
            print(f"      {line}")
    return result.returncode


print("Windows CI simulation\n")

# 1. A clean HOME, which is where the runner keeps no config at all.
home = tempfile.mkdtemp(prefix="ci_home_")
run("clean HOME", {"HOME": home, "USERPROFILE": home, "ASTRA_HOME": home + SEP + "astra"})

# 2. The runner's strict KPI env, which the local suite usually omits.
run("STRICT_KPI=1", {"STRICT_KPI": "1"})

# 3. A fresh ASTRA_HOME that does not exist yet.
missing = tempfile.mkdtemp(prefix="ci_parent_") + SEP + "does_not_exist"
run("ASTRA_HOME does not exist", {"ASTRA_HOME": missing})

# 4. No source checkout on the import path, the way a runner sees it.
isolated = tempfile.mkdtemp(prefix="ci_cwd_")
run("no CWD on sys.path", {"PYTHONPATH": ""}, cwd=isolated)

# 5. The combination that matters most.
run("clean HOME + STRICT_KPI", {
    "HOME": home, "USERPROFILE": home, "STRICT_KPI": "1",
    "ASTRA_HOME": home + SEP + "astra2", "PYTHONPATH": "",
})

shutil.rmtree(home, ignore_errors=True)
shutil.rmtree(isolated, ignore_errors=True)
