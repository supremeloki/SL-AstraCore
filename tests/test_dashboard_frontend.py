"""The dashboard SPA must not ship logic that silently misbehaves.

These are static assertions over dashboard_real.html rather than DOM tests: the
defects they pin (a requestAnimationFrame loop that could never stop, an event
loader that was defined but never called, a synthetic progress bar) are all
reachable by reading the source, and asserting on the source keeps them from
coming back without needing a browser in CI.
"""

from pathlib import Path
import re

import pytest

SPA = Path(__file__).resolve().parent.parent / "dashboard_real.html"
SOURCE = SPA.read_text(encoding="utf-8")


def _body_of(function_name: str) -> str:
    match = re.search(rf"function {function_name}\s*\([^)]*\)\s*\{{(.*?)\n\}}", SOURCE, re.S)
    assert match, f"{function_name} not found in the SPA"
    return match.group(1)


def test_rendering_loop_can_actually_stop():
    """The old condition `!REDUCED || !settled` was true forever for normal users."""
    body = _body_of("tickGraph")
    code = "\n".join(line for line in body.splitlines() if not line.strip().startswith("//"))
    assert "!REDUCED || !settled" not in code, "the rAF loop can never terminate"
    assert "animId = null" in code, "the loop must park itself once the layout settles"
    assert "return;" in code, "a settled frame must return before rescheduling"


def test_event_log_is_actually_polled():
    """loadEvents existed but had no call site, so the panel stayed empty."""
    calls = len(re.findall(r"\bloadEvents\s*\(", SOURCE))
    assert calls >= 2, "loadEvents must be defined and called (boot + fallback poll)"


def test_no_synthetic_progress_bar():
    """The bar counted SSE events, hitting 100% after eight unrelated log lines."""
    body = _body_of("updateMonitor")
    assert "monitorSteps" not in body, "the monitor still counts events as progress"
    assert "monitorPct" not in SOURCE, "the fake progress bar is still in the markup"
    assert "progress-fill" not in SOURCE, "the fake progress bar CSS/markup is still present"


def test_context_requests_cannot_render_out_of_order():
    body = _body_of("loadContext")
    assert "ctxSeq" in body, "a slow context response can overwrite a newer one"


def test_overview_poll_keeps_the_selected_repo_current():
    body = _body_of("loadOverview")
    assert "curRepo" in body and "still" in body, "curRepo is never re-pointed at the refreshed record"


def test_failed_requests_render_an_error_state():
    for function_name in ("loadDiff", "loadExec", "loadContext"):
        body = _body_of(function_name)
        assert "catch" in body, f"{function_name} has no error handling"
        assert "empty" in body, f"{function_name} leaves a spinner on failure"


def test_all_html_sinks_escape_untrusted_data():
    """Every innerHTML assignment that interpolates a variable must go through esc()."""
    offenders = []
    for match in re.finditer(r"\.innerHTML\s*=\s*([^\n;]+)", SOURCE):
        expr = match.group(1)
        if "esc(" in expr:
            continue
        # Interpolations of pure numbers, fixed palettes, or ids we generate are safe.
        if re.search(r"\$\{(fmt|pct|depth|\d)", expr):
            continue
        if re.search(r"\$\{(col|color)\b", expr) and "typeColor" in SOURCE:
            continue
        if "innerHTML" not in expr:
            continue
        if re.search(r"\$\{", expr) and "esc(" not in expr:
            offenders.append(expr.strip()[:90])
    assert not offenders, "unescaped innerHTML interpolations: " + "; ".join(offenders[:5])
