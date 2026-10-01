"""Measure what the suite exercises, with sys.settrace.

trace.Trace's localtrace hook is a no-op on this interpreter, so the
measurement uses sys.settrace directly and filters by filename. No
third-party dependency — coverage is not installable here.
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path("F:" + chr(92) + "SL-AstraCore")
PACKAGE = str(ROOT / "astra")


def executable_lines(path: Path) -> set:
    """Statement lines: what a test could plausibly exercise."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    continue  # a docstring, not code
            lines.add(node.lineno)
    return lines


class Collector:
    def __init__(self, package):
        self.package = package
        self.hits = {}

    def tracer(self, frame, event, arg):
        filename = frame.f_code.co_filename
        if not filename.startswith(self.package):
            return None
        if event == "line":
            self.hits.setdefault(filename, set()).add(frame.f_lineno)
        return self.tracer


def measure():
    import pytest

    collector = Collector(PACKAGE)
    previous = sys.gettrace()
    sys.settrace(collector.tracer)
    try:
        pytest.main([str(ROOT / "tests"), "-q", "--tb=no", "-p", "no:cacheprovider"])
    finally:
        sys.settrace(previous)

    per_file = {}
    total_exec = total_hit = 0
    for path in Path(PACKAGE).rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        executable = executable_lines(path)
        hit = collector.hits.get(str(path), set()) & executable
        per_file[str(path.relative_to(ROOT))] = {
            "executable": len(executable),
            "covered": len(hit),
            "percent": round(100 * len(hit) / max(len(executable), 1), 1),
        }
        total_exec += len(executable)
        total_hit += len(hit)

    return {
        "total": {
            "executable": total_exec,
            "covered": total_hit,
            "percent": round(100 * total_hit / max(total_exec, 1), 1),
        },
        "files": per_file,
    }


if __name__ == "__main__":
    report = measure()
    total = report["total"]
    print(f"\nCOVERAGE: {total['covered']}/{total['executable']} = {total['percent']}%")

    rows = [
        (name, data) for name, data in report["files"].items()
        if data["executable"] >= 40
    ]
    print("\nlowest covered (40+ lines):")
    for name, data in sorted(rows, key=lambda kv: kv[1]["percent"])[:15]:
        bar = "#" * int(data["percent"] / 5)
        print(f"  {data['percent']:5.1f}%  {data['covered']:4}/{data['executable']:<4} "
              f"{name:46} {bar}")

    zero = [
        name for name, data in report["files"].items()
        if data["executable"] >= 15 and data["covered"] == 0
    ]
    print(f"\nzero coverage (15+ lines): {len(zero)}")
    for name in sorted(zero):
        print(f"  {name}")

    (ROOT / "coverage-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")