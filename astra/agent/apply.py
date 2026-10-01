"""Apply an edit that has already been reviewed.

Kept separate from astra.agent.loop on purpose: reviewing is pure, applying is
not. The caller reviews, sees the risk, and only then calls this — and this
re-reads the file and refuses if anything moved since the review, because an
edit anchored in code that has since changed is how a review stops meaning
anything.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from astra.agent.loop import EditReview, ProposedEdit


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class ApplyError(RuntimeError):
    """The edit no longer matches what was reviewed."""


def apply_edit(edit: ProposedEdit, root: str, *, expected_fingerprint: str | None = None) -> str:
    """Write one reviewed edit, or refuse and say why.

    expected_fingerprint is what the caller saw during the review. Passing it
    turns "the file changed under you" from a silent corruption into an error.
    """
    from astra.patch.analyzer import read_source

    path = Path(root) / edit.path
    try:
        source = read_source(str(path))
    except OSError as exc:
        raise ApplyError(f"{edit.path}: could not be read ({exc})") from exc

    if expected_fingerprint and _fingerprint(source) != expected_fingerprint:
        raise ApplyError(
            f"{edit.path}: the file changed since it was reviewed; "
            "review it again"
        )

    updated = edit.apply_to(source)
    if updated == source:
        raise ApplyError(f"{edit.path}: the edit changes nothing")

    path.write_text(updated, encoding="utf-8")
    return _fingerprint(updated)


def apply_review(reviewed: EditReview, root: str, *, fingerprints: dict[str, str] | None = None) -> list[str]:
    """Apply every edit in a review that came back clean.

    Stops at the first failure: a review with three edits where the second no
    longer matches has already left the repository in a state nobody reviewed,
    so continuing would compound it.
    """
    if not reviewed.applies_cleanly:
        raise ApplyError(f"the review was not clean: {reviewed.warnings}")

    applied: list[str] = []
    for edit in reviewed.edits:
        expected = fingerprints.get(edit.path) if fingerprints else None
        apply_edit(edit, root, expected_fingerprint=expected)
        applied.append(edit.path)
    return applied


def fingerprint_files(reviewed: EditReview, root: str) -> dict[str, str]:
    """The fingerprints to pass back to apply_review.

    Taken during the review, so apply_review can prove the file is still the
    one that was reviewed.
    """
    from astra.patch.analyzer import read_source

    out: dict[str, str] = {}
    for edit in reviewed.edits:
        try:
            out[edit.path] = _fingerprint(read_source(str(Path(root) / edit.path)))
        except OSError:
            continue
    return out


if __name__ == "__main__":
    import shutil
    import tempfile

    directory = tempfile.mkdtemp()
    target = Path(directory, "billing.py")
    target.write_text("def charge(a):\n    return a - 1\n", encoding="utf-8")

    edit = ProposedEdit(
        path="billing.py", old_text="return a - 1", new_text="return a", reason="off by one"
    )
    reviewed = EditReview(edits=(edit,), diffs=())

    # A clean review writes the file.
    assert apply_review(reviewed, directory) == ["billing.py"]
    assert "return a" in target.read_text(encoding="utf-8")

    # Applying again fails, because the anchor is gone.
    try:
        apply_review(reviewed, directory)
        raise AssertionError("re-applying should have failed")
    except ApplyError:
        pass

    # A stale fingerprint is refused.
    target.write_text("def charge(a):\n    return a - 1\n", encoding="utf-8")
    try:
        apply_edit(edit, directory, expected_fingerprint="deadbeef")
        raise AssertionError("a stale fingerprint should have been refused")
    except ApplyError:
        pass

    # An edit that changes nothing is refused.
    try:
        apply_edit(ProposedEdit(path="billing.py", old_text="nope", new_text="x"), directory)
        raise AssertionError("an unanchored edit should have been refused")
    except ApplyError:
        pass

    # A dirty review is not applied at all.
    dirty = EditReview(edits=(edit,), warnings=("something was off",))
    try:
        apply_review(dirty, directory)
        raise AssertionError("a dirty review should not be applied")
    except ApplyError:
        pass

    shutil.rmtree(directory, ignore_errors=True)
    print("ok")
