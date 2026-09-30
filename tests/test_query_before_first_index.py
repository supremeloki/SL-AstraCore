"""A query on a never-indexed repository must work, not raise.

The lock serialises a query against an index, but nothing told the query the
index was coming: whichever arrived first held the lock, and a query that won
found status=registered and raised "Repository not active". It failed about
once in eight runs, which is why it reached CI before anything else did.
"""

import logging
import threading
from pathlib import Path

from astra.runtime.orchestrator import RuntimeOrchestrator


def _repo(path: Path, files: int = 30) -> None:
    for i in range(files):
        directory = path / f"pkg{i // 10}"
        directory.mkdir(exist_ok=True)
        (directory / f"mod{i}.py").write_text(
            f"def handler_{i}():\n    return {i}\n", encoding="utf-8"
        )


def test_querying_a_freshly_registered_repo_indexes_it(tmp_path):
    logging.disable(logging.CRITICAL)
    _repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    assert orchestrator.get_repo(str(tmp_path)).status.value == "registered"

    pack = orchestrator.query_context(
        str(tmp_path), seed_node_ids=[], query_intent="handler", max_tokens=4000
    )

    assert pack.nodes, "the query returned nothing"
    assert orchestrator.get_repo(str(tmp_path)).status.value == "active"


def test_a_query_racing_a_first_index_never_raises(tmp_path):
    logging.disable(logging.CRITICAL)
    _repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    outcomes: list[str] = []

    def index() -> None:
        orchestrator.index_repo(str(tmp_path))
        outcomes.append("indexed")

    def query() -> None:
        try:
            orchestrator.query_context(
                str(tmp_path), seed_node_ids=[], query_intent="handler", max_tokens=4000
            )
            outcomes.append("queried")
        except Exception as exc:  # noqa: BLE001 - the point is that it must not raise
            outcomes.append(f"failed: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=index), threading.Thread(target=query)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=90)

    assert "indexed" in outcomes
    assert "queried" in outcomes, f"a query racing the first index raised: {outcomes}"


def test_a_query_on_an_unindexed_repo_is_not_silently_empty(tmp_path):
    """The fix must actually return the graph, not an empty pack."""
    logging.disable(logging.CRITICAL)
    _repo(tmp_path)

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(tmp_path))
    pack = orchestrator.query_context(
        str(tmp_path), seed_node_ids=[], query_intent="handler", max_tokens=8000
    )

    names = {node.name for node in pack.nodes}
    assert any(name.endswith(".py") for name in names), f"no files in the pack: {names}"
