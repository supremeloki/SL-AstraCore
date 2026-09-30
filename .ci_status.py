"""Print the current CI matrix state for this repository."""

import json
import subprocess
import sys
import urllib.request

TOKEN = subprocess.run(
    "printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill | grep '^password=' | cut -d= -f2",
    shell=True,
    capture_output=True,
    text=True,
).stdout.strip()

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "astra-ci-check",
}
BASE = "https://api.github.com/repos/supremeloki/SL-AstraCore"


def get(path: str):
    request = urllib.request.Request(f"{BASE}{path}", headers=HEADERS)
    return json.load(urllib.request.urlopen(request))


def main() -> int:
    run = get("/actions/runs?per_page=1")["workflow_runs"][0]
    print(f"run {run['head_sha'][:8]}: {run['conclusion'] or run['status']}")
    print(f"  {run['html_url']}")
    for job in get(f"/actions/runs/{run['id']}/jobs")["jobs"]:
        print(f"  [{str(job['conclusion'] or job['status']):9}] {job['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
