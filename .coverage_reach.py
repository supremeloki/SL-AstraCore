"""How much of astra does a real dashboard session actually touch?"""

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

SEP = chr(92)
logging.disable(logging.CRITICAL)

repo = Path(tempfile.mkdtemp(prefix="astra_dead_"))
(repo / "a.py").write_text("def f(): return 1\n", encoding="utf-8")

before = set(sys.modules)
import dashboard_app  # noqa: E402

orchestrator = dashboard_app._orchestrator
orchestrator.register_repo(str(repo))
orchestrator.index_repo(str(repo))
orchestrator.query_context(str(repo), seed_node_ids=[], query_intent="f", max_tokens=4000)
used = {m for m in set(sys.modules) - before if m.startswith("astra.")}

on_disk = set()
for root, dirs, names in os.walk("astra"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for name in names:
        if not name.endswith(".py"):
            continue
        stem = os.path.join(root, name)[:-3].replace(SEP, ".").replace("/", ".")
        on_disk.add(stem.replace(".__init__", ""))

print(f"modules imported by a real session : {len(used)}")
print(f"modules on disk                    : {len(on_disk)}")
print(f"never touched                      : {len(on_disk - used)}")

shutil.rmtree(repo, ignore_errors=True)
