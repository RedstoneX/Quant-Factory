"""Strict browser diagnostics for Dash callback cancellation responses."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit


CALLBACK_STATUS_MARKER = "DASH_CALLBACK_STATUS "
_CALLBACK_PATH = "/_dash-update-component"


class PendingCallbackRequests:
    """Track callbacks across distinct Playwright wrappers for one request."""

    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str, str | None]] = Counter()

    @staticmethod
    def _signature(request: Any) -> tuple[str, str, str | None]:
        return (request.method, request.url, request.post_data)

    def add(self, request: Any) -> None:
        self._counts[self._signature(request)] += 1

    def discard(self, request: Any) -> None:
        signature = self._signature(request)
        if self._counts[signature] <= 1:
            self._counts.pop(signature, None)
        else:
            self._counts[signature] -= 1

    def __bool__(self) -> bool:
        return bool(self._counts)

    def __len__(self) -> int:
        return sum(self._counts.values())


def install_callback_status_recorder(server: Any) -> None:
    """Record enough server evidence to classify browser-side Dash aborts."""

    from flask import request

    @server.after_request
    def record_callback_status(response: Any) -> Any:
        if request.path != _CALLBACK_PATH:
            return response
        body = request.get_json(silent=True) or {}
        values = (*body.get("inputs", ()), *body.get("state", ()))

        def value(component_id: str, prop: str) -> Any:
            return next(
                (
                    item.get("value")
                    for item in values
                    if item.get("id") == component_id
                    and item.get("property") == prop
                ),
                None,
            )

        print(
            CALLBACK_STATUS_MARKER
            + json.dumps(
                {
                    "output": body.get("output"),
                    "pathname": value("url", "pathname"),
                    "search": value("url", "search"),
                    "status": response.status_code,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return response


def attach_browser_diagnostics(
    page: Any,
    events: list[dict[str, object]],
    action: Mapping[str, str],
) -> PendingCallbackRequests:
    """Capture browser failures while tracking in-flight Dash callbacks."""

    pending_requests = PendingCallbackRequests()

    def record(kind: str, **details: object) -> None:
        events.append(
            {
                "action": action["name"],
                "page_url": page.url,
                "kind": kind,
                **details,
            }
        )

    page.on("pageerror", lambda error: record("pageerror", message=str(error)))
    page.on(
        "console",
        lambda message: record("console", message=message.text)
        if message.type == "error"
        else None,
    )
    page.on(
        "response",
        lambda response: record(
            "http-error", status=response.status, url=response.url
        )
        if response.status >= 400
        else None,
    )
    page.on(
        "request",
        lambda request: pending_requests.add(request)
        if urlsplit(request.url).path == _CALLBACK_PATH
        else None,
    )
    page.on(
        "requestfinished",
        lambda request: pending_requests.discard(request)
        if urlsplit(request.url).path == _CALLBACK_PATH
        else None,
    )

    def request_failed(request: Any) -> None:
        if urlsplit(request.url).path == _CALLBACK_PATH:
            pending_requests.discard(request)
        record(
            "requestfailed",
            url=request.url,
            failure=request.failure,
            request_body=request.post_data,
        )

    page.on("requestfailed", request_failed)
    return pending_requests


def parse_callback_statuses(
    server_logs: Sequence[Path],
    *,
    marker: str = CALLBACK_STATUS_MARKER,
) -> list[dict[str, object]]:
    """Parse every callback JSON document, including adjacent log writes."""

    statuses: list[dict[str, object]] = []
    decoder = json.JSONDecoder()
    for server_log in server_logs:
        text = server_log.read_text(encoding="utf-8", errors="replace")
        for fragment in text.split(marker)[1:]:
            status, _ = decoder.raw_decode(fragment.lstrip())
            statuses.append(status)
    return statuses


def _value(
    values: Iterable[object], component_id: str, prop: str
) -> object | None:
    return next(
        (
            item.get("value")
            for item in values
            if isinstance(item, dict)
            and item.get("id") == component_id
            and item.get("property") == prop
        ),
        None,
    )


def _signature(record: Mapping[str, object]) -> tuple[object, object, object]:
    return (record.get("output"), record.get("pathname"), record.get("search"))


def assert_browser_diagnostics_clean(
    page: Any,
    events: Sequence[Mapping[str, object]],
    server_logs: Sequence[Path],
) -> int:
    """Reject every diagnostic unless an abort exactly matches a Dash 204."""

    assert page.locator("._dash-error-card").count() == 0
    assert page.locator("#_dash-error-container .dash-error-card").count() == 0

    statuses = parse_callback_statuses(server_logs)
    server_204s = Counter(
        _signature(status)
        for status in statuses
        if status.get("status") == 204
    )
    aborted_204s: Counter[tuple[object, object, object]] = Counter()
    rejected: list[Mapping[str, object]] = []

    for event in events:
        if event.get("kind") != "requestfailed":
            rejected.append(event)
            continue
        if (
            urlsplit(str(event.get("url", ""))).path != _CALLBACK_PATH
            or event.get("failure") != "net::ERR_ABORTED"
            or not event.get("request_body")
        ):
            rejected.append(event)
            continue
        try:
            body = json.loads(str(event["request_body"]))
        except (json.JSONDecodeError, TypeError):
            rejected.append(event)
            continue
        if not isinstance(body, dict) or not isinstance(body.get("output"), str):
            rejected.append(event)
            continue
        inputs = body.get("inputs", [])
        state = body.get("state", [])
        if not isinstance(inputs, list) or not isinstance(state, list):
            rejected.append(event)
            continue
        values = (*inputs, *state)
        aborted_204s[
            (
                body["output"],
                _value(values, "url", "pathname"),
                _value(values, "url", "search"),
            )
        ] += 1

    assert rejected == []
    assert aborted_204s == server_204s, {
        "browser_aborts": aborted_204s,
        "server_204s": server_204s,
    }
    return sum(aborted_204s.values())
