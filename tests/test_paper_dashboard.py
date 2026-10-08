"""Focused component proof for the inactive Quant Factory Paper destination."""

from typing import Any, Iterator

from dashboard.pages.paper_trading import layout


def _walk(component: Any) -> Iterator[Any]:
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float)):
        yield from _walk(children)


def _text(component: Any) -> str:
    children = getattr(component, "children", component)
    if isinstance(children, (list, tuple)):
        return " ".join(_text(child) for child in children)
    if children is None:
        return ""
    if hasattr(children, "children"):
        return _text(children)
    return str(children)


def test_paper_destination_is_inactive_and_separate_from_qamc() -> None:
    page = layout()
    rendered = _text(page)

    assert page.className == "page-container support-page pending-page paper-trading-page"
    assert "No paper lane is connected" in rendered
    assert "It is not QAMC" in rendered
    assert "Broker-observed P&L" in rendered
    assert "No orders" in rendered
    assert not any(getattr(item, "id", "").startswith("order-") for item in _walk(page))
