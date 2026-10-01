"""Close the loop: a question in, a reviewed patch out.

Everything here already existed — the pack builder, the AST differ, the risk
scorer, the write endpoint — but nothing connected them, so the project
claimed to be "ready to hand to any AI coding agent" while containing no code
that an agent could be handed.

The loop is:

    question -> context pack -> model -> proposed edit -> analysed diff
             -> risk report -> the caller applies it or does not

Nothing here calls a model. The model is a callable the caller supplies, so
the loop is testable without a network and usable with any provider. The
safety property is the point: the model never writes a file. It returns text,
the edit is parsed and analysed, and applying it stays a separate decision the
caller makes.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from astra.ir.models import IRContextPack
from astra.patch.analyzer import AstDiff, diff_ast, read_source, score_risk


class Model(Protocol):
    """Anything that turns a prompt into text. A callable is enough."""

    def __call__(self, prompt: str) -> str: ...


@dataclass
class ProposedEdit:
    """One file the model wants changed."""

    path: str
    old_text: str
    new_text: str
    reason: str = ""

    def apply_to(self, source: str) -> str:
        """The new content, or unchanged when the anchor is not present.

        A model that quotes the code it was given should be right about it.
        One that paraphrases is not, and silently rewriting a file from a
        paraphrase is how an agent destroys work — so this is a no-op unless
        the old text appears verbatim.
        """
        if not self.old_text:
            return self.new_text
        if self.old_text not in source:
            return source
        return source.replace(self.old_text, self.new_text, 1)


@dataclass
class EditReview:
    """What the loop produced, before anything is written."""

    edits: tuple[ProposedEdit, ...] = ()
    diffs: tuple[tuple[str, AstDiff], ...] = ()
    risk: str = "unknown"
    confidence: float = 0.0
    downstream: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def applies_cleanly(self) -> bool:
        """True when every edit is anchored in the source it claims to change."""
        return not self.warnings


# The model is asked for JSON between markers rather than raw JSON, because
# every provider wraps or fences its output differently and a bare parse then
# fails on the wrapper rather than on the content.
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def render_pack(pack: IRContextPack, *, max_chars: int = 24000) -> str:
    """The pack as source text, in the order an agent should read it.

    Highest relevance first, and truncated per node so one large file cannot
    consume the whole budget and starve the file that answers the question.
    """
    from astra.runtime.orchestrator import _SNIPPET_MAX_LINES

    blocks: list[str] = []
    used = 0
    for ref in sorted(pack.nodes, key=lambda n: -n.relevance_score):
        if not ref.snippet:
            continue
        header = f"--- {ref.file_path or ref.name} ({ref.relevance_score:.2f}) ---"
        body = "\n".join(ref.snippet.splitlines()[:_SNIPPET_MAX_LINES])
        block = f"{header}\n{body}\n"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)

    summary = (
        f"task: {pack.task_summary}\n"
        f"type: {pack.task_type.value}\n"
        f"nodes: {len(pack.nodes)}  tokens~{pack.total_tokens}/{pack.token_budget}\n"
    )
    return summary + "\n".join(blocks)


def parse_edits(reply: str) -> tuple[list[ProposedEdit], tuple[str, ...]]:
    """Read proposed edits out of a model reply.

    Returns the edits and any warnings — an unparsable reply is a warning, not
    an exception, because a model that ignored the format has still produced
    no edit and there is nothing to roll back.
    """
    warnings: list[str] = []
    body = reply.strip()

    fenced = _FENCE.search(body)
    if fenced:
        body = fenced.group(1)
    else:
        # Some models emit the object with no fence at all.
        start = body.find("{")
        end = body.rfind("}")
        if start == -1 or end <= start:
            return [], ("the reply contained no JSON object",)
        body = body[start:end + 1]

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return [], (f"the reply was not valid JSON: {exc}",)

    raw_edits = payload.get("edits") if isinstance(payload, dict) else None
    if not isinstance(raw_edits, list) or not raw_edits:
        return [], ("the reply carried no edits",)

    edits: list[ProposedEdit] = []
    for entry in raw_edits:
        if not isinstance(entry, dict):
            warnings.append("an edit was not an object")
            continue
        path = str(entry.get("path", "")).strip()
        if not path:
            warnings.append("an edit had no path")
            continue
        if "old_text" not in entry or "new_text" not in entry:
            warnings.append(f"{path}: an edit needs both old_text and new_text")
            continue
        edits.append(
            ProposedEdit(
                path=path,
                old_text=str(entry["old_text"]),
                new_text=str(entry["new_text"]),
                reason=str(entry.get("reason", "")),
            )
        )

    return edits, tuple(warnings)


def review(
    edits: tuple[ProposedEdit, ...],
    root: str,
    *,
    downstream_counts: Optional[Callable[[str], int]] = None,
) -> EditReview:
    """Parse and score each edit against the real source, without writing."""
    from pathlib import Path

    review_result = EditReview(edits=edits)
    warnings: list[str] = list(review_result.warnings)
    diffs: list[tuple[str, AstDiff]] = []
    risks: list[str] = []
    confidences: list[float] = []
    downstream = 0

    for edit in edits:
        source_path = Path(root) / edit.path
        try:
            source = read_source(str(source_path))
        except OSError as exc:
            warnings.append(f"{edit.path}: could not be read ({exc})")
            continue

        if edit.old_text and edit.old_text not in source:
            warnings.append(
                f"{edit.path}: the quoted code is not in the file, so the edit "
                "was not applied"
            )
            continue

        proposed = edit.apply_to(source)
        if proposed == source:
            warnings.append(f"{edit.path}: the edit changes nothing")
            continue

        try:
            # Reject anything that does not parse before it is ever proposed.
            ast.parse(proposed)
        except SyntaxError as exc:
            warnings.append(f"{edit.path}: the result does not parse ({exc.msg})")
            continue

        diff = diff_ast(source, proposed)
        diffs.append((edit.path, diff))
        count = downstream_counts(edit.path) if downstream_counts else 0
        downstream += count
        report = score_risk(diff, downstream=count)
        risks.append(report.level)
        confidences.append(report.confidence)

    levels = ["low", "medium", "high"]
    overall = "low"
    for level in risks:
        if level in levels and levels.index(level) > levels.index(overall):
            overall = level

    return EditReview(
        edits=edits,
        diffs=tuple(diffs),
        risk=overall,
        confidence=min(confidences) if confidences else 0.0,
        downstream=downstream,
        warnings=tuple(warnings),
    )


def run(
    question: str,
    model: Model,
    pack: IRContextPack,
    root: str,
    *,
    downstream_counts: Optional[Callable[[str], int]] = None,
    max_chars: int = 24000,
) -> EditReview:
    """The loop: pack the repository, ask the model, review what came back.

    The model is never given a way to write. It returns text; this returns a
    review; the caller decides.
    """
    prompt = (
        "You are editing a Python repository. Below is the relevant source.\n"
        "Propose the smallest change that answers the question.\n\n"
        "Reply with a single JSON object and nothing else:\n"
        '{"edits": [{"path": "...", "old_text": "...", "new_text": "...", '
        '"reason": "..."}]}\n\n'
        "Rules:\n"
        "- old_text must appear verbatim in the file you name.\n"
        "- Change only what the task needs.\n"
        "- If no change is needed, reply {\"edits\": []}.\n\n"
        f"QUESTION: {question}\n\n"
        f"{render_pack(pack, max_chars=max_chars)}"
    )

    reply = model(prompt)
    edits, warnings = parse_edits(reply)
    if warnings:
        return EditReview(edits=tuple(edits), warnings=warnings)

    reviewed = review(tuple(edits), root, downstream_counts=downstream_counts)
    return EditReview(
        edits=reviewed.edits,
        diffs=reviewed.diffs,
        risk=reviewed.risk,
        confidence=reviewed.confidence,
        downstream=reviewed.downstream,
        warnings=reviewed.warnings,
    )


if __name__ == "__main__":
    # A model that returns exactly the requested shape.
    reply = json.dumps({
        "edits": [{
            "path": "sample.py",
            "old_text": "def add(a, b):\n    return a - b",
            "new_text": "def add(a, b):\n    return a + b",
            "reason": "add was subtracting",
        }]
    })

    import shutil
    import tempfile
    from pathlib import Path

    directory = tempfile.mkdtemp()
    Path(directory, "sample.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    assert parse_edits(reply)[0][0].path == "sample.py"
    assert parse_edits("not json at all")[1], "an unparsable reply must warn"
    assert parse_edits('{"edits": []}')[1], "an empty edit list must warn"

    parsed_edits, _ = parse_edits(reply)
    result = review(tuple(parsed_edits), root=directory)
    assert result.applies_cleanly, result.warnings
    assert result.risk in ("low", "medium", "high")
    assert result.diffs, "a valid edit produced no diff"

    # An edit whose anchor is not in the file must not be applied.
    bogus = (ProposedEdit(path="sample.py", old_text="def gone(): pass", new_text="x"),)
    assert not review(bogus, root=directory).applies_cleanly

    # An edit that does not parse must be rejected before it is proposed.
    broken = (ProposedEdit(path="sample.py", old_text="", new_text="def (: pass"),)
    assert not review(broken, root=directory).applies_cleanly

    shutil.rmtree(directory, ignore_errors=True)
    print("ok")
