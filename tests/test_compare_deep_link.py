"""Focused exact-pair Compare query and callback regressions."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from dash import Dash, no_update

from dashboard.callbacks.compare_backtests import register_compare_backtests_callbacks
from dashboard.compare_query import compare_query_href, parse_compare_search
from dashboard.pages.compare_backtests import layout
from tests.test_compare_adapter import _comparison_stack
from tests.test_compare_results import _CompareAdapter, _model


COMPARE_PATH = "/research/compare-backtests"


class _Runs:
    def all_history(self, *, artifact_root=None):
        return (
            {"run_id": "exact-old"},
            {"run_id": "exact-failed"},
        )


class _DetailAdapter:
    artifact_root = Path(".")


def _callback(app: Dash, output_fragment: str):
    entry = next(
        value for key, value in app.callback_map.items() if output_fragment in key
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def _app(adapter) -> Dash:
    app = Dash(__name__, suppress_callback_exceptions=True)
    register_compare_backtests_callbacks(
        app,
        runs=_Runs(),
        detail_adapter=_DetailAdapter(),
        dashboard_database=Path("unused.sqlite3"),
        artifact_root=Path("."),
        compare_adapter=adapter,
    )
    return app


def _walk(component):
    if component is None:
        return
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None:
        yield from _walk(children)


def _by_id(component, component_id: str):
    return next(
        item for item in _walk(component) if getattr(item, "id", None) == component_id
    )


def _text(component) -> str:
    if isinstance(component, str):
        return component
    return " ".join(
        child
        for item in _walk(component)
        if isinstance((child := getattr(item, "children", None)), str)
    )


def test_compare_query_preserves_order_and_href_round_trips() -> None:
    run_ids = ("run:target one", "failed/peer", "older?run", "fourth")
    href = compare_query_href(run_ids)

    assert href is not None
    request = parse_compare_search(href.split("?", 1)[1])
    assert request.valid
    assert request.run_ids == run_ids
    assert href.count("run_id=") == 4


def test_compare_query_rejects_ambiguous_or_unsafe_requests_safely() -> None:
    invalid = (
        "?run_id=only-one",
        "?run_id=a&run_id=b&run_id=c&run_id=d&run_id=e",
        "?run_id=same&run_id=same",
        "?run_id=a&unexpected=b",
        "?run_id=&run_id=b",
        "?run_id=a&run_id=%GG",
        "?run_id=a&run_id=%FF",
    )
    assert all(parse_compare_search(search).requested for search in invalid)
    assert all(not parse_compare_search(search).valid for search in invalid)

    control = parse_compare_search("?run_id=alpha%0Asecret&run_id=beta")
    assert not control.valid
    assert control.visible_tokens == ("alpha\\x0asecret", "beta")
    assert "\n" not in "".join(control.visible_tokens)

    unexpected = parse_compare_search("?not_run_id=visible")
    assert not unexpected.valid
    assert unexpected.visible_tokens == ("not_run_id=visible",)


def test_registered_compare_callbacks_adopt_query_without_writing_location() -> None:
    adapter = _CompareAdapter(_model())
    app = _app(adapter)
    query = "?" + urlencode(
        (("run_id", "exact-old"), ("run_id", "exact-failed"))
    )

    rows = _callback(app, "find-compare-grid.rowData")
    hydrate = _callback(app, "find-compare-grid.selectedRows")
    compare = _callback(app, "run-comparison-output.children")

    history = rows(0, COMPARE_PATH, query)
    assert hydrate(query, COMPARE_PATH, history) == history

    rendered, class_name = compare(
        0,
        COMPARE_PATH,
        query,
    )
    assert class_name == "run-comparison-output"
    assert _by_id(rendered, "comparison-read-model") is not None
    assert adapter.reads == [("exact-old", "exact-failed")]
    assert all("url." not in key for key in app.callback_map)


def test_invalid_query_clears_selector_and_never_reads_or_falls_back() -> None:
    adapter = _CompareAdapter(_model())
    app = _app(adapter)
    query = "?run_id=duplicate&run_id=duplicate"
    hydrate = _callback(app, "find-compare-grid.selectedRows")
    compare = _callback(app, "run-comparison-output.children")

    assert hydrate(query, COMPARE_PATH, [{"run_id": "duplicate"}]) == []

    rendered, _ = compare(
        0,
        COMPARE_PATH,
        query,
    )
    assert adapter.reads == []
    text = _text(rendered)
    assert "duplicate" in text
    assert "Comparison could not be read" in text


def test_grid_selection_builds_explicit_results_and_compare_links() -> None:
    app = _app(_CompareAdapter(_model()))
    actions = _callback(app, "find-compare-selection-message.children")

    def selected(count: int):
        return [
            {
                "run_id": f"session-{index}",
                "status": "Succeeded",
                "review": "Not reviewed",
                "metric_basis": (
                    "Top-ranked variation · Rank 1 · Screening Passed"
                ),
            }
            for index in range(count)
        ]

    zero = actions(selected(0), "", COMPARE_PATH)
    assert zero[2] is None and zero[4] is None

    one = actions(selected(1), "", COMPARE_PATH)
    assert one[2] == "/research/backtest-results?run_id=session-0"
    assert one[3] == {}
    assert one[5] == {"display": "none"}
    assert "Rank 1 · Screening Passed" in one[0]

    for count in (2, 3, 4):
        comparison = actions(selected(count), "", COMPARE_PATH)
        assert comparison[2] is None
        assert comparison[4].count("run_id=") == count
        assert comparison[5] == {}

    five = actions(selected(5), "", COMPARE_PATH)
    assert five[2] is None and five[4] is None
    assert "reduce the selection" in five[0]

    ordered = actions(
        [{"run_id": "second"}, {"run_id": "first"}],
        "?run_id=first&run_id=second",
        COMPARE_PATH,
    )
    assert ordered[4] == (
        "/research/compare-backtests?run_id=first&run_id=second"
    )


def test_unknown_valid_run_identity_reaches_read_only_adapter_as_unavailable(
    tmp_path: Path,
) -> None:
    database, artifact_root = _comparison_stack(tmp_path)
    from dashboard.compare_adapter import CompareDashboardAdapter

    model = CompareDashboardAdapter(
        database=database,
        artifact_root=artifact_root,
    ).compare(("unknown-a", "unknown-b"))

    assert model.requested_run_ids == ("unknown-a", "unknown-b")
    assert [run.run_id for run in model.runs] == ["unknown-a", "unknown-b"]
    assert all(not run.available for run in model.runs)
    assert all(
        run.results_href.endswith(f"run_id={run.run_id}") for run in model.runs
    )


def test_compare_page_mounts_exact_link_and_query_status_region() -> None:
    page = layout(history_rows=())

    assert _by_id(page, "find-compare-selection-message") is not None
    assert _by_id(page, "find-compare-grid") is not None
    link = _by_id(page, "find-compare-exact-link")
    assert link.href is None
    assert link.style == {"display": "none"}
