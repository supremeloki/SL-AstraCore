"""Does the stored GitHub credential still work, and what does CI say?"""

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

token = subprocess.run(
    "printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill | grep '^password=' | cut -d= -f2",
    shell=True, capture_output=True, text=True,
).stdout.strip()
HEADERS = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "a"}
BASE = "https://api.github.com/repos/supremeloki/SL-AstraCore"


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS)))


try:
    runs = get(f"{BASE}/actions/runs?per_page=5")["workflow_runs"]
except urllib.error.HTTPError as exc:
    print(f"credential rejected: HTTP {exc.code}")
    print("The token stored in git's credential helper is no longer valid.")
    sys.exit(2)

print(f"credential works. latest runs:")
for run in runs[:3]:
    print(f"  {run['head_sha'][:8]}  {run['conclusion'] or run['status']}")

wanted = sys.argv[1] if len(sys.argv) > 1 else runs[0]["head_sha"][:8]
match = next((r for r in runs if r["head_sha"].startswith(wanted)), None)
if match is None:
    print(f"\nno run yet for {wanted}")
    sys.exit(0)

if match["status"] != "completed":
    print(f"\nrun {wanted} is still {match['status']}")
    sys.exit(0)

print(f"\nrun {match['head_sha'][:8]}: {match['conclusion']}")
for job in get(f"{BASE}/actions/runs/{match['id']}/jobs")["jobs"]:
    bad = [s["name"] for s in job.get("steps", []) if s["conclusion"] not in ("success", "skipped", None)]
    print(f"  [{str(job['conclusion']):8}] {job['name']:34} {bad}")

if match["conclusion"] == "failure":
    print()
    for issue in get(f"{BASE}/issues?state=all&per_page=40"):
        if "CI failure" in issue["title"] and match["head_sha"][:8] in issue["title"]:
            body = re.sub(r"\x1b\[[0-9;]*m", "", issue["body"])
            print("=" * 66)
            print(issue["title"])
            print("=" * 66)
            print(body[:2500])
            break