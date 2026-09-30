"""Astra command-line interface (stdlib argparse only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astra",
        description="SL-AstraCore: Repository Cognitive Intelligence Platform",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Scan, parse and index a repository")
    p_index.add_argument("path", help="Repository root path")

    p_ctx = sub.add_parser("context", help="Query a context pack for a task")
    p_ctx.add_argument("path", help="Registered repository root path")
    p_ctx.add_argument("query", help="Task description or query intent")

    p_serve = sub.add_parser("serve", help="Start the dashboard server")
    p_serve.add_argument("--port", type=int, default=8000, help="Port (default 8000)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "serve":
        uvicorn.run("dashboard_app:app", host="127.0.0.1", port=args.port)
        return 0

    from astra.runtime.orchestrator import RuntimeOrchestrator

    path = str(Path(args.path).resolve())
    orchestrator = RuntimeOrchestrator()

    if args.command == "index":
        orchestrator.register_repo(path)
        record = orchestrator.index_repo(path)
        print(f"{record.name}: status={record.status.value} files={record.file_count} "
              f"nodes={record.node_count} edges={record.edge_count}")
        if record.status.value == "failed":
            print(f"error: {record.error}", file=sys.stderr)
            return 1
        return 0

    existing = orchestrator.get_repo(path)
    if existing is not None and existing.status.value == "active":
        record = existing
    else:
        orchestrator.register_repo(path)
        fresh_record = orchestrator.index_repo(path)
        assert fresh_record is not None, "index_repo always returns a RepoRecord"
        record = fresh_record
        if fresh_record.status.value == "failed":
            print(f"error: {fresh_record.error}", file=sys.stderr)
            return 1
    pack = orchestrator.query_context(path, seed_node_ids=[], query_intent=args.query)
    print(f"task: {pack.task_summary}")
    print(f"nodes: {len(pack.nodes)}  edges: {len(pack.edges)}  "
          f"tokens~{pack.total_tokens}/{pack.token_budget}  confidence={pack.confidence:.2f}")
    for ref in pack.nodes[:20]:
        loc = f" ({ref.file_path})" if ref.file_path else ""
        print(f"  {ref.relevance_score:.2f}  {ref.node_id}  {ref.name}{loc}")
    if len(pack.nodes) > 20:
        print(f"  ... {len(pack.nodes) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def console_main() -> None:
    """The entry point the console script calls.

    setuptools calls the target and discards its return value, so a function
    returning 1 for a failed index left `astra index /bad/path` exiting 0 — a
    shell script wrapping the CLI could not tell success from failure.
    """
    raise SystemExit(main())
