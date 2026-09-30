"""Poll CI until a commit's run finishes, then report."""

import json
import re
import subprocess
import sys
import time
import urllib.request

token = subprocess.run(
    "printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill | grep '^password=' | cut -d= -f2",
    shell=True, capture_output=True, text=True,
).stdout.strip()
HEADERS = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "a"}
BASE = "https://api.github.com/repos/supremeloki/SL-AstraCore"


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS)))


prefix = sys.argv[1]
deadline = time.time() + 780
run = None
while time.time() < deadline:
    candidates = get(f"{BASE}/actions/runs?per_page=6")["workflow_runs"]
    run = next((r for r in candidates if r["head_sha"].startswith(prefix)), None)
    if run and run["status"] == "completed":
        break
    print(f"  {prefix}: {run['status'] if run else 'not started yet'}", flush=True)
    time.sleep(20)

if run is None or run["status"] != "completed":
    print("did not finish in time")
    sys.exit(0)

print(f"\nrun {run['head_sha'][:8]}: {run['conclusion']}")
for job in get(f"{BASE}/actions/runs/{run['id']}/jobs")["jobs"]:
    bad = [s["name"] for s in job.get("steps", []) if s["conclusion"] not in ("success", "skipped", None)]
    print(f"  [{str(job['conclusion']):8}] {job['name']:34} {bad}")

if run["conclusion"] == "failure":
    print()
    for issue in get(f"{BASE}/issues?state=all&per_page=40"):
        if "CI failure" in issue["title"] and run["head_sha"][:8] in issue["title"]:
            body = re.sub(r"\x1b\[[0-9;]*m", "", issue["body"])
            print("=" * 66)
            print(issue["title"])
            print("=" * 66)
            print(body[:2200])
            break