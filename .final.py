"""Final verification. Every number quoted in the docs comes from here."""

import logging
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SEP = chr(92)
logging.disable(logging.CRITICAL)
ROOT = Path("F:" + SEP + "SL-AstraCore")
sys.path.insert(0, str(ROOT))

from astra.runtime.orchestrator import RuntimeOrchestrator  # noqa: E402

QUESTIONS = [
    ("where are the scanner's ignore rules defined",
     ["orchestrator.py", "ignore_engine.py", "repository_scanner.py"]),
    ("which module creates the duckdb staging table", ["duckdb_backend.py"]),
    ("how does the access token guard api calls", ["dashboard_app.py"]),
    ("how are nodes ranked by relevance", ["ranking.py"]),
    ("how is the event log trimmed", ["event_bus.py"]),
    ("where are the default config values", ["config.py"]),
    ("how does sqlite store graph nodes", ["sqlite_backend.py"]),
    ("what resolves imports into edges",
     ["resolve_imports_into_edges", "import_resolver.py"]),
    ("how is the token budget enforced", ["token_budget.py", "context_engine.py"]),
    ("what detects naming conflicts",
     ["conflict_enricher.py", "conflict.py", "enrichment.py"]),
    ("how does the scanner use gitignore", ["orchestrator.py", "repository_scanner.py"]),
    ("where is the pack token budget decided", ["token_budget.py", "orchestrator.py"]),
]


def rule(title):
    print(f"\n{title}\n{'-' * 70}")


engine = RuntimeOrchestrator()
engine.register_repo(str(ROOT))

rule("INDEX")
start = time.time()
record = engine.index_repo(str(ROOT))
seconds = time.time() - start
print(f"  {record.file_count} files: {seconds:.1f}s ({record.file_count / seconds:.0f} f/s)")

big = Path(tempfile.mkdtemp(prefix="astra_final_"))
for i in range(3000):
    directory = big / f"pkg{i // 50}"
    directory.mkdir(exist_ok=True)
    (directory / f"m{i}.py").write_text(
        f"import pkg{max(0, i // 50 - 1)}.m{max(0, i - 1)}\n\ndef f{i}():\n    return {i}\n",
        encoding="utf-8",
    )
other = RuntimeOrchestrator()
other.register_repo(str(big))
start = time.time()
big_record = other.index_repo(str(big))
big_seconds = time.time() - start
print(f"  3000 files: {big_seconds:.1f}s ({big_record.file_count / big_seconds:.0f} f/s)")
import shutil

shutil.rmtree(big, ignore_errors=True)

rule("QUERY")
times = []
for _ in range(6):
    start = time.time()
    engine.query_context(str(ROOT), seed_node_ids=[], query_intent="ranking", max_tokens=8000)
    times.append((time.time() - start) * 1000)
print(f"  median {statistics.median(times):.0f}ms (min {min(times):.0f})")

rule("RANKING ACCURACY")
top1 = top3 = 0
for question, acceptable in QUESTIONS:
    pack = engine.query_context(
        str(ROOT), seed_node_ids=[], query_intent=question, max_tokens=8000
    )
    order = [
        n.name
        for n in sorted(
            [n for n in pack.nodes if n.snippet], key=lambda n: -n.relevance_score
        )
    ]
    rank = min((order.index(x) + 1 for x in acceptable if x in order), default=999)
    top1 += rank == 1
    top3 += rank <= 3
print(f"  top-1 {top1}/12   top-3 {top3}/12")

rule("PACK")
for budget in (2000, 4000, 16000):
    pack = engine.query_context(
        str(ROOT), seed_node_ids=[], query_intent="ranking", max_tokens=budget
    )
    code = [n for n in pack.nodes if n.snippet]
    print(
        f"  budget {budget:6}: {len(pack.nodes):3} nodes, {len(code):3} with source "
        f"({100 * len(code) // len(pack.nodes)}%), "
        f"{sum(len(n.snippet) for n in code):7} chars"
    )

rule("GATES")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:cacheprovider"],
    capture_output=True, text=True, cwd=str(ROOT),
)
for line in result.stdout.splitlines():
    if "passed" in line or "failed" in line:
        print("  " + line.strip())
for command, label in (
    ([sys.executable, "-m", "ruff", "check", "astra/", "tests/", "dashboard_app.py"], "ruff "),
    ([sys.executable, "-m", "mypy", "astra/", "dashboard_app.py", "--python-version", "3.12"], "mypy "),
):
    out = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT))
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    print(f"  {label} {lines[-1][:60] if lines else ''}")