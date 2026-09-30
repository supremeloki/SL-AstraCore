"""Which test fails here, with CI's STRICT_KPI set?"""

import os
import subprocess
import sys

REPO = "F:" + chr(92) + "SL-AstraCore"

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line", "-p", "no:cacheprovider"],
    capture_output=True, text=True, cwd=REPO,
    env={**os.environ, "STRICT_KPI": "1"},
)
for line in result.stdout.splitlines():
    if line.startswith(("FAILED", "ERROR")) or "passed" in line or "failed" in line:
        print(line)