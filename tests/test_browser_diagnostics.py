"""Adversarial tests for strict browser diagnostic classification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.browser.dashboard_diagnostics import (
    CALLBACK_STATUS_MARKER,
    PendingCallbackRequests,
    assert_browser_diagnostics_clean,
    parse_callback_statuses,
)


class _Locator:
    def __init__(self, count: int = 0) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class _Page:
    def __init__(self, renderer_errors: int = 0) -> None:
        self.renderer_errors = renderer_errors

    def locator(self, _selector: str) -> _Locator:
        return _Locator(self.renderer_errors)


class _Request:
    def __init__(
        self,
        *,
        method: str = "POST",
        url: str = "http://127.0.0.1:8050/_dash-update-component",
        post_data: str | None = '{"output":"result.children"}',
    ) -> None:
        self.method = method
        self.url = url
        self.post_data = post_data


def _request_body(
    output: str = "result.children", *, search_in_state: bool = True
) -> str:
    inputs: list[dict[str, object]] = [
        {
            "id": "url",
            "property": "pathname",
            "value": "/research/backtest-results",
        },
    ]
    body: dict[str, object] = {
        "output": output,
        "inputs": inputs,
    }
    search = {"id": "url", "property": "search", "value": "?run_id=run-1"}
    if search_in_state:
        body["state"] = [search]
    else:
        inputs.append(search)
    return json.dumps(body)


def _abort(output: str = "result.children") -> dict[str, object]:
    return {
        "kind": "requestfailed",
        "url": "http://127.0.0.1:8050/_dash-update-component",
        "failure": "net::ERR_ABORTED",
        "request_body": _request_body(output),
    }


def _write_status(log: Path, *outputs: str) -> None:
    log.write_text(
        "".join(
            CALLBACK_STATUS_MARKER
            + json.dumps(
                {
                    "output": output,
                    "pathname": "/research/backtest-results",
                    "search": "?run_id=run-1",
                    "status": 204,
                },
                sort_keys=True,
            )
            + "\n"
            for output in outputs
        ),
        encoding="utf-8",
    )


def test_exact_callback_abort_and_server_204_are_accepted(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    _write_status(log, "result.children")

    assert assert_browser_diagnostics_clean(_Page(), [_abort()], (log,)) == 1


def test_callback_body_without_state_is_matched(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    _write_status(log, "result.children")
    event = _abort()
    event["request_body"] = _request_body(search_in_state=False)

    assert assert_browser_diagnostics_clean(_Page(), [event], (log,)) == 1


def test_pending_callback_settles_with_a_distinct_event_wrapper() -> None:
    pending = PendingCallbackRequests()

    pending.add(_Request())
    pending.discard(_Request())

    assert not pending
    assert len(pending) == 0


def test_pending_callback_tracker_preserves_duplicate_request_count() -> None:
    pending = PendingCallbackRequests()

    pending.add(_Request())
    pending.add(_Request())
    pending.discard(_Request())

    assert pending
    assert len(pending) == 1


def test_callback_status_parser_handles_adjacent_markers(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    first = {"output": "first.children", "status": 200}
    second = {"output": "second.children", "status": 204}
    marker = "COMPARE_CALLBACK_STATUS "
    log.write_text(
        marker + json.dumps(first) + marker + json.dumps(second) + "\n",
        encoding="utf-8",
    )

    assert parse_callback_statuses((log,), marker=marker) == [first, second]


@pytest.mark.parametrize(
    ("events", "statuses", "renderer_errors"),
    [
        ([_abort("unmatched.children")], ("result.children",), 0),
        ([_abort()], ("result.children", "extra.children"), 0),
        (
            [
                {
                    **_abort(),
                    "failure": "net::ERR_FAILED",
                }
            ],
            ("result.children",),
            0,
        ),
        ([{"kind": "console", "message": "boom"}], (), 0),
        ([{"kind": "pageerror", "message": "boom"}], (), 0),
        ([{"kind": "http-error", "status": 500}], (), 0),
        (
            [
                {
                    **_abort(),
                    "request_body": "not-json",
                }
            ],
            ("result.children",),
            0,
        ),
        ([], (), 1),
    ],
)
def test_unproven_or_real_browser_failures_remain_fatal(
    tmp_path: Path,
    events: list[dict[str, object]],
    statuses: tuple[str, ...],
    renderer_errors: int,
) -> None:
    log = tmp_path / "server.log"
    _write_status(log, *statuses)

    with pytest.raises(AssertionError):
        assert_browser_diagnostics_clean(
            _Page(renderer_errors), events, (log,)
        )
