"""One runnable scorecard. Every number the audit quotes comes from here."""

import ast
import logging
import os
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
    ("how does the scanner use gitignore",
     ["orchestrator.py", "repository_scanner.py"]),
    ("where is the pack token budget decided", ["token_budget.py", "orchestrator.py"]),
]


def rule(title):
    print(f"\n{'-' * 72}\n{title}\n{'-' * 72}")


def accuracy(engine):
    rule("RANKING ACCURACY (12 questions about this repository)")
    top1 = top3 = top5 = 0
    for question, acceptable in QUESTIONS:
        pack = engine.query_context(
            str(ROOT), seed_node_ids=[], query_intent=question, max_tokens=4000
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
        top5 += rank <= 5
        print(f"  rank {str(rank) if rank < 999 else 'MISS':>4}  {acceptable[0][:26]:28}")
    print(f"\n  top-1 {top1}/12   top-3 {top3}/12   top-5 {top5}/12")
    return top1, top3


def pack_quality(engine):
    rule("PACK QUALITY — how much of a pack is usable")
    for question in ("ranking", "duckdb staging", "access token"):
        pack = engine.query_context(
            str(ROOT), seed_node_ids=[], query_intent=question, max_tokens=4000
        )
        code = [n for n in pack.nodes if n.snippet]
        chars = sum(len(n.snippet) for n in code)
        print(
            f"  {question:16} {len(pack.nodes):3} nodes, {len(code):2} with source "
            f"({100 * len(code) / len(pack.nodes):3.0f}%), {chars:6} chars, "
            f"budget {pack.token_budget}"
        )
    # A bigger budget must actually buy more source.
    small = engine.query_context(
        str(ROOT), seed_node_ids=[], query_intent="ranking", max_tokens=2000
    )
    large = engine.query_context(
        str(ROOT), seed_node_ids=[], query_intent="ranking", max_tokens=16000
    )
    small_chars = sum(len(n.snippet) for n in small.nodes if n.snippet)
    large_chars = sum(len(n.snippet) for n in large.nodes if n.snippet)
    print(
        f"\n  budget 2000 -> {small_chars} chars | budget 16000 -> {large_chars} chars "
        f"({large_chars / max(small_chars, 1):.1f}x for 8x the budget)"
    )


def performance(engine):
    rule("PERFORMANCE")
    start = time.time()
    record = engine.index_repo(str(ROOT))
    seconds = time.time() - start
    print(
        f"  index {record.file_count} files: {seconds:.1f}s "
        f"({record.file_count / seconds:.0f} f/s), {record.node_count} nodes"
    )
    start = time.time()
    engine.index_repo(str(ROOT))
    print(f"  re-index, nothing changed: {time.time() - start:.1f}s")
    times = []
    for _ in range(6):
        start = time.time()
        engine.query_context(str(ROOT), seed_node_ids=[], query_intent="ranking", max_tokens=4000)
        times.append((time.time() - start) * 1000)
    print(f"  query median {statistics.median(times):.0f}ms (min {min(times):.0f})")

    # A synthetic repo so the number is not this repo's particular shape.
    big = Path(tempfile.mkdtemp(prefix="astra_scale_"))
    for i in range(300):
        directory = big / f"pkg{i // 30}"
        directory.mkdir(exist_ok=True)
        body = "\n".join(f"def f{i}_{j}(a, b):\n    return a + b + {j}" for j in range(10))
        (directory / f"m{i}.py").write_text(
            f"import pkg{max(0, i // 30 - 1)}.m{max(0, i - 1)}\n\n{body}\n", encoding="utf-8"
        )
    other = RuntimeOrchestrator()
    other.register_repo(str(big))
    start = time.time()
    rec = other.index_repo(str(big))
    seconds = time.time() - start
    print(
        f"  index 300 synthetic files: {seconds:.1f}s ({rec.file_count / seconds:.0f} f/s), "
        f"{rec.node_count} nodes"
    )
    import shutil

    shutil.rmtree(big, ignore_errors=True)


def scale_check():
    rule("SCALE — a 3,000-file repository")
    big = Path(tempfile.mkdtemp(prefix="astra_big_"))
    for i in range(3000):
        directory = big / f"pkg{i // 50}"
        directory.mkdir(exist_ok=True)
        (directory / f"m{i}.py").write_text(
            f"import pkg{max(0, i // 50 - 1)}.m{max(0, i - 1)}\n\ndef f{i}():\n    return {i}\n",
            encoding="utf-8",
        )
    engine = RuntimeOrchestrator()
    engine.register_repo(str(big))
    start = time.time()
    record = engine.index_repo(str(big))
    seconds = time.time() - start
    print(f"  index 3000 files: {seconds:.1f}s ({record.file_count / seconds:.0f} f/s)")
    start = time.time()
    pack = engine.query_context(
        str(big), seed_node_ids=[], query_intent="function", max_tokens=8000
    )
    print(f"  first query: {(time.time() - start) * 1000:.0f}ms")
    start = time.time()
    engine.query_context(str(big), seed_node_ids=[], query_intent="import", max_tokens=8000)
    print(f"  second query: {(time.time() - start) * 1000:.0f}ms")
    import shutil

    shutil.rmtree(big, ignore_errors=True)


def test_quality():
    rule("TESTS")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    for line in result.stdout.splitlines():
        if "passed" in line or "failed" in line:
            print("  " + line.strip())

    asserts = 0
    for path in (ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        asserts += sum(1 for n in ast.walk(tree) if isinstance(n, ast.Assert))
    print(f"  assert statements: {asserts}")

    for command, label in (
        ([sys.executable, "-m", "ruff", "check", "astra/", "tests/", "dashboard_app.py"], "ruff "),
        ([sys.executable, "-m", "mypy", "astra/", "dashboard_app.py", "--python-version", "3.12"], "mypy "),
    ):
        out = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT))
        lines = [l for l in out.stdout.splitlines() if l.strip()]
        print(f"  {label} {lines[-1][:64] if lines else ''}")


def main():
    engine = RuntimeOrchestrator()
    engine.register_repo(str(ROOT))
    engine.index_repo(str(ROOT))

    accuracy(engine)
    pack_quality(engine)
    performance(engine)
    scale_check()
    test_quality()
    return 0


if __name__ == "__main__":
    sys.exit(main())
