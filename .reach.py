"""Which modules does a real run never touch? Measure, then delete carefully."""

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)
REPO = Path("F:" + chr(92) + "SL-AstraCore")
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import dashboard_app  # noqa: E402

work = Path(tempfile.mkdtemp(prefix="astra_reach_"))
(work / "a.py").write_text("def f(): return 1\n", encoding="utf-8")
orch = dashboard_app._orchestrator
orch.register_repo(str(work))
orch.index_repo(str(work))
orch.query_context(str(work), seed_node_ids=[], query_intent="f", max_tokens=4000)
# The index and one query is the whole product; anything absent is not in it.
touched = {m for m in sys.modules if m.startswith("astra.")}
shutil.rmtree(work, ignore_errors=True)

on_disk = {}
for directory, subdirs, names in os.walk(REPO / "astra"):
    subdirs[:] = [d for d in subdirs if d != "__pycache__"]
    for name in names:
        if not name.endswith(".py"):
            continue
        full = Path(directory) / name
        stem = str(full.relative_to(REPO))[:-3].replace(os.sep, ".")
        stem = stem.replace(".__init__", "")
        on_disk[stem] = full

untouched = sorted(set(on_disk) - touched)
dead_loc = 0
print(f"modules on disk : {len(on_disk)}")
print(f"touched by a run: {len(touched & set(on_disk))}")
print(f"never touched   : {len(untouched)}\n")
for module in untouched:
    full = on_disk[module]
    loc = len(full.read_text(encoding="utf-8", errors="replace").splitlines())
    dead_loc += loc
    print(f"  {module:52} {loc:5}")
print(f"\nTOTAL: {dead_loc} lines")
