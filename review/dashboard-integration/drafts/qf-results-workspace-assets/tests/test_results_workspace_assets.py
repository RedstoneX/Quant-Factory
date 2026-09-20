"""Static contracts for the isolated Results workspace asset layer."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "dashboard" / "assets" / "zz-results-workspace.css"
JS_PATH = ROOT / "dashboard" / "assets" / "zz-results-workspace.js"


def test_results_workspace_javascript_parses() -> None:
    completed = subprocess.run(
        ["node", "--check", str(JS_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_results_workspace_declares_stable_integration_hooks() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    javascript = JS_PATH.read_text(encoding="utf-8")

    assert ".results-workspace[data-results-run-id]" in javascript
    assert '[data-results-resize="chart-top|chart-report|report-bottom"]' in javascript
    assert "[data-results-reset-layout]" in javascript
    assert ".results-workspace__chart" in css
    assert ".results-workspace__report" in css
    assert "[data-results-report]" in css


def test_layout_state_is_session_only_and_scoped_by_run() -> None:
    javascript = JS_PATH.read_text(encoding="utf-8")

    assert 'const STORAGE_PREFIX = "qf.results.workspace.layout.v1:"' in javascript
    assert "root.dataset.resultsRunId" in javascript
    assert "window.sessionStorage.getItem(key)" in javascript
    assert "window.sessionStorage.setItem(key" in javascript
    assert "window.sessionStorage.removeItem(key)" in javascript
    assert "localStorage" not in javascript


def test_reset_and_resize_do_not_mutate_other_results_state() -> None:
    javascript = JS_PATH.read_text(encoding="utf-8")

    # The browser helper is deliberately limited to presentation dimensions.
    assert 'root.style.setProperty("--qf-results-chart-height"' in javascript
    assert 'root.style.setProperty("--qf-results-report-min-height"' in javascript
    for forbidden_write in (
        "resultsBarsCurrent",
        "resultsViewCurrent",
        "resultsReportTab",
        "resultsSelectedTrade",
        "resultsSelectedLeg",
        "window.location",
    ):
        assert forbidden_write not in javascript


def test_report_remains_in_page_flow_and_small_screens_disable_resizing() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    javascript = JS_PATH.read_text(encoding="utf-8")

    assert ".results-workspace__metrics," in css
    assert "overflow-y: visible;" in css
    assert "max-height: none;" in css
    assert "padding-bottom: clamp(2rem, 5vw, 3.25rem);" in css
    assert "@media (max-width: 1099px)" in css
    assert ".results-workspace__resize-handle" in css
    assert "display: none;" in css
    assert 'const DESKTOP_QUERY = "(min-width: 1100px)"' in javascript


def test_resize_handles_receive_keyboard_separator_semantics() -> None:
    javascript = JS_PATH.read_text(encoding="utf-8")

    for token in (
        'handle.setAttribute("role", "separator")',
        'handle.setAttribute("aria-orientation", "horizontal")',
        'handle.setAttribute("aria-valuemin"',
        'handle.setAttribute("aria-valuemax"',
        'handle.setAttribute("aria-valuenow"',
        '"ArrowUp"',
        '"ArrowDown"',
        '"Home"',
        '"End"',
    ):
        assert token in javascript


def test_dash_dom_hydration_does_not_reset_an_initialized_run() -> None:
    javascript = JS_PATH.read_text(encoding="utf-8")

    assert "const initializedRuns = new WeakMap()" in javascript
    assert "initializedRuns.get(root) === runId" in javascript
    assert "initializedRuns.set(root, runId)" in javascript
    assert "const minimumDelta = Math.max(" in javascript
    assert "const maximumDelta = Math.min(" in javascript
