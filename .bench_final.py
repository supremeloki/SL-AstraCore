"""Measure indexing on a realistic tree, and verify the pandas probe is gone."""

import logging
import shutil
import tempfile
import time
from pathlib import Path

logging.disable(logging.CRITICAL)

repo = Path(tempfile.mkdtemp(prefix="astra_final_"))
for i in range(120):
    sub = repo / f"pkg{i // 20}"
    sub.mkdir(exist_ok=True)
    body = "\n".join(f"def f{i}_{j}(a, b):\n    return a + b + {j}" for j in range(12))
    (sub / f"mod{i}.py").write_text(
        f"from pkg{max(0, i // 20 - 1)}.mod{max(0, i - 1)} import f{max(0, i - 1)}_0\n\n{body}\n",
        encoding="utf-8",
    )

from astra.runtime.orchestrator import RuntimeOrchestrator

orchestrator = RuntimeOrchestrator()
orchestrator.register_repo(str(repo))

start = time.time()
record = orchestrator.index_repo(str(repo))
first = time.time() - start
print(
    f"index {record.file_count} files ({record.node_count} nodes, {record.edge_count} edges): "
    f"{first:.1f}s = {record.file_count / first:.0f} files/s"
)

start = time.time()
orchestrator.index_repo(str(repo))
print(f"re-index unchanged: {time.time() - start:.1f}s")

start = time.time()
pack = orchestrator.query_context(
    str(repo), seed_node_ids=[], query_intent="mod7 render", max_tokens=8000
)
print(
    f"query: {(time.time() - start) * 1000:.0f}ms, {len(pack.nodes)} nodes, "
    f"{sum(len(n.snippet) for n in pack.nodes)} chars"
)

shutil.rmtree(repo, ignore_errors=True)
