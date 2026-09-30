"""Simulate a slow CI runner and see which assertions break.

The claim is that the wall-clock KPI budgets were written for a fast machine
and a shared runner trips them. This slows every path down and reports which
tests fail, rather than assuming.
"""

import os
import subprocess
import sys
import time

REPO = "F:" + chr(92) + "SL-AstraCore"

print("This machine, STRICT_KPI=1:\n")
start = time.time()
plain = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:cacheprovider"],
    capture_output=True, text=True, cwd=REPO,
    env={**os.environ, "STRICT_KPI": "1"},
)
print(f"  {(time.time() - start):.0f}s  " + [l for l in plain.stdout.splitlines() if "passed" in l or "failed" in l][-1])

# Now make every storage write slow, the way a contended runner would: wrap the
# DuckDB execute path with a fixed delay. This is the shape of the problem —
# wall-clock budgets against a machine you do not control.
print("\nUnder artificial slowness (each mutator apply_batch +4s):\n")
harness = REPO + chr(92) + ".slowconftest.py"
with open(harness, "w", encoding="utf-8") as handle:
    handle.write(
        "import time\n"
        "import astra.graph.mutator as m\n"
        "_orig = m.GraphMutator.apply_batch\n"
        "def slow(self, *a, **k):\n"
        "    r = _orig(self, *a, **k)\n"
        "    time.sleep(4)\n"
        "    return r\n"
        "m.GraphMutator.apply_batch = slow\n"
    )

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no",
     "-p", "no:cacheprovider", "-p", ".slowconftest"],
    capture_output=True, text=True, cwd=REPO,
    env={**os.environ, "STRICT_KPI": "1"},
)
for line in result.stdout.splitlines():
    if "passed" in line or "failed" in line:
        print("  " + line)
    if line.startswith("FAILED"):
        print("    " + line)

os.remove(harness)