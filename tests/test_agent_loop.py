"""The loop that turns a question into a reviewed edit.

The model is a callable, so every case here runs with no network. What matters
is the safety property: the model returns text, the loop analyses it against
the real files, and nothing is written.
"""

import json

import pytest

from astra.agent.loop import (
    EditReview,
    ProposedEdit,
    parse_edits,
    render_pack,
    review,
    run,
)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "billing.py").write_text(
        "def charge(amount):\n    return amount - 1\n",
        encoding="utf-8",
    )
    (tmp_path / "notes.md").write_text("# notes\n", encoding="utf-8")
    return tmp_path


def a_reply(edits):
    return json.dumps({"edits": edits})


# ── parsing the model's reply ─────────────────────────────────────────────

def test_a_plain_json_object_is_read():
    edits, warnings = parse_edits(a_reply([
        {"path": "billing.py", "old_text": "x", "new_text": "y", "reason": "r"}
    ]))
    assert not warnings
    assert len(edits) == 1
    assert edits[0].path == "billing.py"
    assert edits[0].reason == "r"


def test_a_fenced_reply_is_read():
    reply = "Here you go:\n```json\n" + a_reply([
        {"path": "billing.py", "old_text": "x", "new_text": "y"}
    ]) + "\n```\nHope that helps."
    edits, warnings = parse_edits(reply)
    assert not warnings
    assert edits[0].path == "billing.py"


def test_prose_with_no_json_warns_rather_than_raises():
    edits, warnings = parse_edits("I looked at the code and it seems fine.")
    assert edits == []
    assert warnings, "an unparsable reply must say so"


def test_a_reply_with_no_edits_warns():
    edits, warnings = parse_edits('{"edits": []}')
    assert edits == []
    assert warnings, "an empty edit list is not a successful review"


def test_an_edit_missing_a_field_is_dropped_and_reported():
    edits, warnings = parse_edits(a_reply([
        {"path": "billing.py", "new_text": "y"},
        {"path": "", "old_text": "x", "new_text": "y"},
    ]))
    assert len(warnings) == 2
    assert edits == [] or all(e.path for e in edits)


def test_malformed_json_warns():
    edits, warnings = parse_edits('{"edits": [ {"path": }')
    assert edits == []
    assert warnings


# ── reviewing against the real source ─────────────────────────────────────

def test_a_well_anchored_edit_is_accepted(repo):
    source = (repo / "billing.py").read_text(encoding="utf-8")
    edit = ProposedEdit(
        path="billing.py",
        old_text="return amount - 1",
        new_text="return amount",
        reason="do not undercharge",
    )
    result = review((edit,), root=str(repo))

    assert result.applies_cleanly, result.warnings
    assert result.diffs, "a valid edit produced no diff"
    assert result.risk in ("low", "medium", "high")


def test_an_edit_whose_anchor_is_absent_is_rejected(repo):
    edit = ProposedEdit(
        path="billing.py",
        old_text="def this_function_does_not_exist(): ...",
        new_text="pass",
    )
    result = review((edit,), root=str(repo))

    assert not result.applies_cleanly
    assert any("not in the file" in w for w in result.warnings)
    assert not result.diffs, "an unanchored edit must produce no diff"


def test_an_edit_that_does_not_parse_is_rejected(repo):
    edit = ProposedEdit(
        path="billing.py",
        old_text="def charge(amount):",
        new_text="def charge(amount:\n    broken",
    )
    result = review((edit,), root=str(repo))

    assert not result.applies_cleanly
    assert any("does not parse" in w for w in result.warnings)


def test_an_edit_to_a_missing_file_is_reported(repo):
    edit = ProposedEdit(path="nowhere.py", old_text="", new_text="x = 1\n")
    result = review((edit,), root=str(repo))
    assert not result.applies_cleanly
    assert any("could not be read" in w for w in result.warnings)


def test_an_edit_that_changes_nothing_is_reported(repo):
    source = (repo / "billing.py").read_text(encoding="utf-8")
    edit = ProposedEdit(
        path="billing.py", old_text="return amount - 1", new_text="return amount - 1"
    )
    result = review((edit,), root=str(repo))
    assert not result.applies_cleanly
    assert any("changes nothing" in w for w in result.warnings)


def test_apply_to_is_a_no_op_when_the_anchor_is_missing():
    edit = ProposedEdit(path="x.py", old_text="absent", new_text="new")
    assert edit.apply_to("original") == "original"


def test_apply_to_replaces_one_occurrence():
    edit = ProposedEdit(path="x.py", old_text="a", new_text="b")
    assert edit.apply_to("a a a") == "b a a"


def test_downstream_count_reaches_the_risk_score(repo):
    edit = ProposedEdit(
        path="billing.py", old_text="return amount - 1", new_text="return amount"
    )
    def many_dependents(_path):
        return 12

    few = review((edit,), root=str(repo), downstream_counts=lambda _p: 0)
    many = review((edit,), root=str(repo), downstream_counts=many_dependents)

    assert many.downstream == 12
    assert few.downstream == 0


# ── rendering the pack for the model ──────────────────────────────────────

def test_the_prompt_carries_the_source_and_the_question(repo):
    from astra.runtime.orchestrator import RuntimeOrchestrator

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(repo))
    orchestrator.index_repo(str(repo))
    pack = orchestrator.query_context(
        str(repo), seed_node_ids=[], query_intent="charge", max_tokens=4000
    )

    seen = {}

    def model(prompt):
        seen["prompt"] = prompt
        return a_reply([])

    result = run("why does charge subtract one", model, pack, root=str(repo))

    prompt = seen["prompt"]
    assert "why does charge subtract one" in prompt
    assert "charge" in prompt
    assert '"edits"' in prompt, "the model must be told the reply shape"
    assert result.warnings, "an empty edit list is not a clean run"


def test_the_prompt_truncates_a_single_huge_node(tmp_path):
    from astra.ir.models import ContextNodeRef, IRContextPack

    huge = "\n".join(f"line {n}" for n in range(5000))
    pack = IRContextPack(
        task_summary="big",
        nodes=(
            ContextNodeRef(
                node_id="file:big.py",
                node_type=None,
                name="big.py",
                file_path="big.py",
                snippet=huge,
                relevance_score=1.0,
            ),
        ),
    )
    rendered = render_pack(pack, max_chars=1000)
    assert len(rendered) < 2000, "one enormous file consumed the whole budget"


# ── the loop end to end, with a scripted model ────────────────────────────

def test_the_loop_returns_a_review_and_writes_nothing(repo):
    before = (repo / "billing.py").read_text(encoding="utf-8")

    from astra.runtime.orchestrator import RuntimeOrchestrator

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(repo))
    orchestrator.index_repo(str(repo))
    pack = orchestrator.query_context(
        str(repo), seed_node_ids=[], query_intent="charge", max_tokens=4000
    )

    def model(_prompt):
        return a_reply([{
            "path": "billing.py",
            "old_text": "return amount - 1",
            "new_text": "return amount",
            "reason": "off by one",
        }])

    result = run("fix the charge", model, pack, root=str(repo))

    assert isinstance(result, EditReview)
    assert result.applies_cleanly, result.warnings
    assert result.diffs
    assert (repo / "billing.py").read_text(encoding="utf-8") == before, (
        "the loop wrote to a file; the caller is supposed to decide that"
    )


def test_a_model_returning_prose_produces_a_warning_not_a_crash(repo):
    from astra.runtime.orchestrator import RuntimeOrchestrator

    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(repo))
    orchestrator.index_repo(str(repo))
    pack = orchestrator.query_context(
        str(repo), seed_node_ids=[], query_intent="charge", max_tokens=4000
    )

    result = run("fix it", lambda _p: "I cannot help with that.", pack, root=str(repo))
    assert result.edits == ()
    assert result.warnings


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
