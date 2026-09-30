"""Final measurements for the scorecard. No claims without numbers."""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SEP = chr(92)
logging.disable(logging.CRITICAL)
ROOT = "F:" + SEP + "SL-AstraCore"


def line(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


line("1. TEST SUITE")
start = time.time()
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:cacheprovider"],
    capture_output=True,
    text=True,
)
tail = [l for l in result.stdout.splitlines() if "passed" in l or "failed" in l]
print(f"  {tail[-1] if tail else 'no result'}  ({time.time() - start:.0f}s)")

line("2. LINT AND TYPES")
for command, label in (
    ([sys.executable, "-m", "ruff", "check", "astra/", "tests/", "dashboard_app.py"], "ruff"),
    ([sys.executable, "-m", "mypy", "astra/", "dashboard_app.py", "--python-version", "3.12"], "mypy"),
):
    out = subprocess.run(command, capture_output=True, text=True)
    last = [l for l in out.stdout.splitlines() if l.strip()][-1:] or ["(no output)"]
    print(f"  {label}: {last[0][:80]}")

line("3. CODE SIZE")
loc = subprocess.run(
    "find astra -name '*.py' | xargs wc -l | tail -1", shell=True, capture_output=True, text=True
).stdout.split()[0]
test_loc = subprocess.run(
    "find tests -name '*.py' | xargs wc -l | tail -1", shell=True, capture_output=True, text=True
).stdout.split()[0]
modules = subprocess.run(
    "find astra -name '*.py' | wc -l", shell=True, capture_output=True, text=True
).stdout.strip()
print(f"  code {loc} LOC | tests {test_loc} LOC | ratio {int(test_loc) / int(loc) * 100}%")
print(f"  modules on disk: {modules}")

line("4. RUNTIME REACHABILITY")
before = set(sys.modules)
repo_path = Path(tempfile.mkdtemp(prefix="astra_final_"))
(repo_path / "a.py").write_text("def f(): return 1\n", encoding="utf-8")
import dashboard_app  # noqa: E402

orch = dashboard_app._orchestrator
orch.register_repo(str(repo_path))
orch.index_repo(str(repo_path))
orch.query_context(str(repo_path), seed_node_ids=[], query_intent="f", max_tokens=4000)
used = {m for m in set(sys.modules) - before if m.startswith("astra.")}
on_disk = set()
for directory, subdirs, names in os.walk("astra"):
    for name in names:
        if name.endswith(".py"):
            stem = str(Path(directory) / name)[:-3].replace(SEP, ".").replace("/", ".")
            on_disk.add(stem.replace(".__init__", ""))
shutil.rmtree(repo_path, ignore_errors=True)
print(f"  loaded by a real session: {len(used)}")
print(f"  never loaded:            {len(on_disk - used)}  ({100 * len(on_disk - used) / len(on_disk):.0f}%)")

line("5. PERFORMANCE ON THE REAL REPO")
orch2 = dashboard_app._orchestrator
orch2.register_repo(ROOT)
start = time.time()
record = orch2.index_repo(ROOT)
index_seconds = time.time() - start
print(f"  index {record.file_count} files -> {record.node_count} nodes / {record.edge_count} edges")
print(f"    {index_seconds:.1f}s = {record.file_count / index_seconds:.0f} files/s")
start = time.time()
orch2.index_repo(ROOT)
print(f"  re-index unchanged: {time.time() - start:.1f}s")
start = time.time()
pack = orch2.query_context(ROOT, seed_node_ids=[], query_intent="how does ranking work", max_tokens=4000)
query_ms = (time.time() - start) * 1000
code = [n for n in pack.nodes if n.snippet]
print(f"  query: {query_ms:.0f}ms, {len(code)}/{len(pack.nodes)} nodes carry source")
print(f"  relevance spread: {len(set(n.relevance_score for n in pack.nodes))} distinct values")

line("6. RANKING ACCURACY")
questions = [
    ("duckdb staging table", "duckdb_backend.py"),
    ("how does the access token guard work", "dashboard_app.py"),
    ("how does ranking work", "ranking.py"),
    ("event bus log trimming", "event_bus.py"),
    ("where are config defaults defined", "config.py"),
]
hits = 0
for question, expected in questions:
    result = orch2.query_context(ROOT, seed_node_ids=[], query_intent=question, max_tokens=4000)
    with_code = [n for n in result.nodes if n.snippet]
    top = [n.name for n in sorted(with_code, key=lambda n: -n.relevance_score)[:5]]
    ok = expected in top
    hits += ok
    print(f"  {'HIT ' if ok else 'MISS'} {question[:40]:42} top: {top[:3]}")
print(f"  {hits}/{len(questions)} correct file in top 5")
