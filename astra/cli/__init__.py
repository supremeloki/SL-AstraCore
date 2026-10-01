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

    p_propose = sub.add_parser(
        "propose",
        help="Ask a question and review the edit a model proposes, without writing it",
    )
    p_propose.add_argument("path", help="Registered repository root path")
    p_propose.add_argument("query", help="Task description or query intent")
    p_propose.add_argument(
        "--reply",
        required=True,
        help="The model's reply, as JSON, or '-' to read it from stdin",
    )
    p_propose.add_argument("--budget", type=int, default=8000, help="Token budget (default 8000)")
    p_propose.add_argument(
        "--emit",
        help="Write the reviewed proposal to this file, for `astra apply`",
    )

    p_apply = sub.add_parser(
        "apply",
        help="Apply edits from a reviewed proposal file",
    )
    p_apply.add_argument("path", help="Registered repository root path")
    p_apply.add_argument(
        "proposal",
        help="The JSON the review produced, from astra propose --emit",
    )

    p_serve = sub.add_parser("serve", help="Start the dashboard server")
    p_serve.add_argument("--port", type=int, default=8000, help="Port (default 8000)")
    return parser


def _propose(path: str, args) -> int:
    """Review the edit a model proposes for a question. Writes nothing.

    The reply comes from stdin with `--reply -`, which is how a caller wires
    this to whatever model it uses: the CLI never calls one itself.
    """
    from astra.agent.loop import parse_edits, render_pack, review
    from astra.runtime.orchestrator import RuntimeOrchestrator

    if args.reply == "-":
        reply = sys.stdin.read()
    else:
        candidate = Path(args.reply)
        reply = candidate.read_text(encoding="utf-8") if candidate.exists() else args.reply

    orchestrator = RuntimeOrchestrator()
    if orchestrator.get_repo(path) is None:
        orchestrator.register_repo(path)
        record = orchestrator.index_repo(path)
        if record.status.value == "failed":
            print(f"error: {record.error}", file=sys.stderr)
            return 1

    pack = orchestrator.query_context(
        path, seed_node_ids=[], query_intent=args.query, max_tokens=args.budget
    )

    edits, warnings = parse_edits(reply)
    if warnings:
        print("the reply could not be used:", file=sys.stderr)
        for warning in warnings:
            print(f"  {warning}", file=sys.stderr)
        return 1

    result = review(tuple(edits), path)

    print(f"task: {pack.task_summary}")
    print(f"proposed: {len(result.edits)} edit(s)  risk: {result.risk}  "
          f"confidence: {result.confidence:.2f}")
    for (edited, (_edited_path, diff)) in zip(result.edits, result.diffs):
        print(f"  {edited.path}: +{diff.added} -{diff.removed} ~{diff.modified}"
              f"{'  ' + edited.reason if edited.reason else ''}")
    for warning in result.warnings:
        print(f"  rejected: {warning}", file=sys.stderr)
    if not result.applies_cleanly:
        return 1

    if args.emit:
        import json

        from astra.agent.apply import fingerprint_files

        Path(args.emit).write_text(
            json.dumps(
                {
                    "clean": True,
                    "risk": result.risk,
                    "edits": [
                        {
                            "path": edit.path,
                            "old_text": edit.old_text,
                            "new_text": edit.new_text,
                            "reason": edit.reason,
                        }
                        for edit in result.edits
                    ],
                    "fingerprints": fingerprint_files(result, path),
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"\nproposal written to {args.emit}")

    print("\nnothing was written. Apply with:")
    print(f"  astra apply {path} {args.emit or '<proposal.json>'}")
    return 0


def _apply(path: str, args) -> int:
    """Write the edits from a reviewed proposal. Refuses a stale one."""
    import json

    from astra.agent.apply import ApplyError, apply_edit
    from astra.agent.loop import EditReview, ProposedEdit

    try:
        payload = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read the proposal ({exc})", file=sys.stderr)
        return 1

    if not payload.get("clean"):
        print("error: the proposal was not reviewed clean", file=sys.stderr)
        for warning in payload.get("warnings", ()):
            print(f"  {warning}", file=sys.stderr)
        return 1

    fingerprints = payload.get("fingerprints") or {}
    for entry in payload.get("edits", ()):
        edit = ProposedEdit(
            path=entry.get("path", ""),
            old_text=entry.get("old_text", ""),
            new_text=entry.get("new_text", ""),
            reason=entry.get("reason", ""),
        )
        try:
            apply_edit(edit, path, expected_fingerprint=fingerprints.get(edit.path))
        except ApplyError as exc:
            # Stop at the first refusal: the repository is already partly
            # changed, and continuing would compound a state nobody reviewed.
            print(f"error: {exc}", file=sys.stderr)
            print("nothing further was written", file=sys.stderr)
            return 1
        print(f"applied {edit.path}")

    if not payload.get("edits"):
        print("the proposal carried no edits")
    return 0


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
    if args.command == "propose":
        return _propose(path, args)

    if args.command == "apply":
        return _apply(path, args)

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
