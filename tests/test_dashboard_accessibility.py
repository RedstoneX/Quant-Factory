"""Focused accessibility contracts for non-Results dashboard surfaces."""

from __future__ import annotations

from dash.development.base_component import Component

from dashboard.pages.setup import layout as setup_layout
from dashboard.shell import create_dashboard_layout


def _walk(component: object):
    if isinstance(component, Component):
        yield component
        children = getattr(component, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from _walk(child)
        elif children is not None:
            yield from _walk(children)


def _by_id(component: object, component_id: str) -> Component:
    return next(
        item
        for item in _walk(component)
        if getattr(item, "id", None) == component_id
    )


def test_shell_provides_a_keyboard_bypass_to_focusable_main_content() -> None:
    layout = create_dashboard_layout(
        context=None,
        configurations=(),
        page_factory=lambda *_args, **_kwargs: [],
    )
    root_children = layout.children

    skip_link = root_children[0]
    main = _by_id(layout, "page-content")

    assert skip_link.children == "Skip to main content"
    assert skip_link.href == "#page-content"
    assert skip_link.className == "skip-link"
    assert main.tabIndex == -1


def test_setup_selector_is_exposed_as_a_named_control_group() -> None:
    page = setup_layout(configurations=())
    label = _by_id(page, "configuration-selector-label")
    group = next(
        item
        for item in _walk(page)
        if getattr(item, "role", None) == "group"
        and getattr(item, "aria-labelledby", None) == "configuration-selector-label"
    )

    assert label.children == "Saved setup"
    assert label.htmlFor == "configuration-selector"
    assert _by_id(group, "configuration-selector").disabled is True
