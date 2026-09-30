"""Attach a failing test run to an issue so the detail is readable.

The job-log endpoint is not always accessible to the person fixing the repo,
and the step summary is not exposed through the REST API, so a red build was
effectively undiagnosable. This posts the tail of the run as an issue.
"""

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    token = os.environ.get("GH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")[:8]
    matrix = os.environ.get("CI_MATRIX", "unknown")
    if not token or not repo:
        print("no GH_TOKEN/GITHUB_REPOSITORY; nothing to publish", file=sys.stderr)
        return 0

    try:
        with open("pytest-output.txt", encoding="utf-8", errors="replace") as handle:
            output = handle.read()[-6000:]
    except OSError as exc:
        print(f"no pytest-output.txt: {exc}", file=sys.stderr)
        return 0

    body = {
        "title": f"CI failure: {matrix} @ {sha}",
        "body": f"Automated report from the CI run.\n\n```\n{output}\n```",
    }
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    try:
        urllib.request.urlopen(request)
    except urllib.error.HTTPError as exc:
        print(f"could not publish: {exc}", file=sys.stderr)
        return 0
    print(f"published CI failure report ({matrix} @ {sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
