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
    def recent_runs(self, *, limit: int = 20):
        assert limit == 20
        return ()


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

    options = _callback(app, "comparison-run-selector.options")
    hydrate = _callback(app, "comparison-query-message.children")
    compare = _callback(app, "run-comparison-output.children")

    assert options(0, COMPARE_PATH, query) == [
        {"label": "Requested exact test · Test exact-old", "value": "exact-old"},
        {
            "label": "Requested exact test · Test exact-failed",
            "value": "exact-failed",
        },
    ]
    value, message, message_class, href, style = hydrate(
        query,
        COMPARE_PATH,
        0,
        ["newest-a", "newest-b"],
    )
    assert value == ["exact-old", "exact-failed"]
    assert "URL controls" in message
    assert "error-state" not in message_class
    assert href == f"{COMPARE_PATH}{query}"
    assert style == {}

    rendered, class_name = compare(
        0,
        0,
        COMPARE_PATH,
        query,
        ["newest-a", "newest-b"],
    )
    assert class_name == "run-comparison-output"
    assert _by_id(rendered, "comparison-read-model") is not None
    assert adapter.reads == [("exact-old", "exact-failed")]
    assert all("url." not in key for key in app.callback_map)


def test_invalid_query_clears_selector_and_never_reads_or_falls_back() -> None:
    adapter = _CompareAdapter(_model())
    app = _app(adapter)
    query = "?run_id=duplicate&run_id=duplicate"
    hydrate = _callback(app, "comparison-query-message.children")
    compare = _callback(app, "run-comparison-output.children")

    value, message, message_class, href, style = hydrate(
        query,
        COMPARE_PATH,
        0,
        ["newest-a", "newest-b"],
    )
    assert value == []
    assert "distinct" in message
    assert "error-state" in message_class
    assert href is None
    assert style == {"display": "none"}

    rendered, _ = compare(
        0,
        0,
        COMPARE_PATH,
        query,
        ["newest-a", "newest-b"],
    )
    assert adapter.reads == []
    text = _text(rendered)
    assert "duplicate" in text
    assert "Comparison could not be read" in text


def test_no_query_preserves_session_selector_and_builds_ordinary_link() -> None:
    app = _app(_CompareAdapter(_model()))
    hydrate = _callback(app, "comparison-query-message.children")

    value, message, _, href, style = hydrate(
        "",
        COMPARE_PATH,
        1,
        ["session-a", "session-b"],
    )

    assert value is no_update
    assert "link now matches" in message
    assert href == (
        "/research/compare-backtests?run_id=session-a&run_id=session-b"
    )
    assert style == {}


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
    page = layout(recent_runs=())

    assert _by_id(page, "comparison-query-message") is not None
    link = _by_id(page, "comparison-exact-link")
    assert link.href is None
    assert link.style == {"display": "none"}
