"""Print the full body of every CI failure issue for the current run."""

import json
import re
import subprocess
import urllib.request

token = subprocess.run(
    "printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill | grep '^password=' | cut -d= -f2",
    shell=True, capture_output=True, text=True,
).stdout.strip()

HEADERS = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "a"}
BASE = "https://api.github.com/repos/supremeloki/SL-AstraCore"

issues = json.load(urllib.request.urlopen(
    urllib.request.Request(f"{BASE}/issues?state=all&per_page=30", headers=HEADERS)
))
print(f"total issues: {len(issues)}")
for issue in issues:
    if "CI failure" not in issue["title"]:
        continue
    body = re.sub(r"\x1b\[[0-9;]*m", "", issue["body"])
    # Only the ones that actually name a failing test are informative.
    if "FAILURES" not in body and "failed" not in body:
        continue
    print("=" * 70)
    print(issue["title"])
    print("=" * 70)
    print(body[:2600])
    print()
