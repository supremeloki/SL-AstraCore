"""Applying a reviewed edit, and refusing one that no longer holds.

test_agent_roundtrip.py walks this through the CLI, which runs in a
subprocess and so is invisible to coverage — the module measured 40% while
its only real use was tested. These call it directly, and the point of most
of them is the refusals: applying is the one part of the loop that writes.
"""


import pytest

from astra.agent.apply import (
    ApplyError,
    apply_edit,
    apply_review,
    fingerprint_files,
)
from astra.agent.loop import EditReview, ProposedEdit


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "billing.py").write_text(
        "def charge(amount):\n    return amount - 1\n", encoding="utf-8"
    )
    (tmp_path / "tax.py").write_text("TAX = 0.2\n", encoding="utf-8")
    return tmp_path


def an_edit(path="billing.py", old="return amount - 1", new="return amount"):
    return ProposedEdit(path=path, old_text=old, new_text=new, reason="off by one")


# ── the happy path ─────────────────────────────────────────────────────────

def test_a_clean_review_writes_the_file(repo):
    edit = an_edit()
    applied = apply_review(EditReview(edits=(edit,), diffs=()), str(repo))

    assert applied == ["billing.py"]
    assert "return amount" in (repo / "billing.py").read_text(encoding="utf-8")


def test_two_edits_both_land(repo):
    edits = (
        an_edit(),
        ProposedEdit(path="tax.py", old_text="TAX = 0.2", new_text="TAX = 0.25"),
    )
    assert apply_review(EditReview(edits=edits), str(repo)) == ["billing.py", "tax.py"]
    assert "TAX = 0.25" in (repo / "tax.py").read_text(encoding="utf-8")


# ── the refusals ──────────────────────────────────────────────────────────

def test_a_dirty_review_is_not_applied_at_all(repo):
    before = (repo / "billing.py").read_text(encoding="utf-8")
    dirty = EditReview(edits=(an_edit(),), warnings=("the edit was not anchored",))

    with pytest.raises(ApplyError, match="not clean"):
        apply_review(dirty, str(repo))

    assert (repo / "billing.py").read_text(encoding="utf-8") == before


def test_an_edit_whose_anchor_is_gone_is_refused(repo):
    with pytest.raises(ApplyError, match="changes nothing"):
        apply_edit(an_edit(old="def never_existed(): ..."), str(repo))


def test_applying_the_same_edit_twice_fails(repo):
    review = EditReview(edits=(an_edit(),))
    apply_review(review, str(repo))

    with pytest.raises(ApplyError):
        apply_review(review, str(repo))


def test_a_file_that_changed_since_the_review_is_refused(repo):
    """The anchor can still be present and the edit still be wrong."""
    edit = an_edit()
    fingerprints = fingerprint_files(EditReview(edits=(edit,)), str(repo))

    # Someone else edits the same line region after the review.
    (repo / "billing.py").write_text(
        "def charge(amount, currency=None):\n    return amount - 1\n", encoding="utf-8"
    )
    before = (repo / "billing.py").read_text(encoding="utf-8")

    with pytest.raises(ApplyError, match="changed since it was reviewed"):
        apply_edit(edit, str(repo), expected_fingerprint=fingerprints["billing.py"])

    assert (repo / "billing.py").read_text(encoding="utf-8") == before


def test_a_matching_fingerprint_is_accepted(repo):
    edit = an_edit()
    fingerprints = fingerprint_files(EditReview(edits=(edit,)), str(repo))
    apply_edit(edit, str(repo), expected_fingerprint=fingerprints["billing.py"])
    assert "return amount" in (repo / "billing.py").read_text(encoding="utf-8")


def test_an_edit_to_a_missing_file_is_refused(repo):
    with pytest.raises(ApplyError, match="could not be read"):
        apply_edit(ProposedEdit(path="nowhere.py", old_text="", new_text="x = 1\n"), str(repo))


def test_it_stops_at_the_first_refusal(repo):
    """Two edits where the second is bad must not leave the first applied.

    Continuing would compound a state nobody reviewed, so the order matters:
    the good edit goes first only to prove the check runs before the write.
    """
    bad = ProposedEdit(path="billing.py", old_text="absent", new_text="replaced")
    with pytest.raises(ApplyError):
        apply_review(EditReview(edits=(bad, an_edit())), str(repo))

    assert "return amount - 1" in (repo / "billing.py").read_text(encoding="utf-8"), (
        "a write happened before the refusal"
    )


def test_a_review_with_no_edits_applies_nothing(repo):
    before = (repo / "billing.py").read_text(encoding="utf-8")
    assert apply_review(EditReview(), str(repo)) == []
    assert (repo / "billing.py").read_text(encoding="utf-8") == before


# ── fingerprints ───────────────────────────────────────────────────────────

def test_fingerprints_cover_the_edits_and_skip_unreadable_ones(repo):
    fingerprints = fingerprint_files(
        EditReview(edits=(an_edit(), ProposedEdit(path="gone.py", old_text="", new_text="x"))),
        str(repo),
    )
    assert "billing.py" in fingerprints
    assert "gone.py" not in fingerprints, "an unreadable file must not get a fingerprint"


def test_a_fingerprint_changes_when_the_file_does(repo):
    edit = an_edit()
    before = fingerprint_files(EditReview(edits=(edit,)), str(repo))["billing.py"]
    (repo / "billing.py").write_text("def charge(amount):\n    return 0\n", encoding="utf-8")
    after = fingerprint_files(EditReview(edits=(edit,)), str(repo))["billing.py"]

    assert before != after, "a fingerprint that ignores the content is useless"


def test_a_fingerprint_is_stable_across_reads(repo):
    edit = an_edit()
    first = fingerprint_files(EditReview(edits=(edit,)), str(repo))
    second = fingerprint_files(EditReview(edits=(edit,)), str(repo))
    assert first == second


def test_the_fingerprint_map_is_keyed_by_path(repo):
    """Applying one file's edit must not satisfy another file's check."""
    (repo / "refund.py").write_text(
        "def refund(amount):\n    return -amount\n", encoding="utf-8"
    )
    edit = an_edit()
    other = ProposedEdit(
        path="refund.py", old_text="return -amount", new_text="return 0"
    )
    prints = fingerprint_files(EditReview(edits=(edit, other)), str(repo))

    assert set(prints) == {"billing.py", "refund.py"}
    assert prints["billing.py"] != prints["refund.py"]

    apply_edit(other, str(repo), expected_fingerprint=prints["refund.py"])
    assert "return 0" in (repo / "refund.py").read_text(encoding="utf-8")
    assert "return amount - 1" in (repo / "billing.py").read_text(encoding="utf-8"), (
        "applying refund.py also touched billing.py"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
