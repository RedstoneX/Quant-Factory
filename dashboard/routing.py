"""Dashboard route registry and pathname-derived presentation state."""

from __future__ import annotations

NAVIGATION_GROUPS = (
    (
        "Research workflow",
        (
            ("/research/ideas", "Ideas"),
            ("/research/setup", "Set up"),
            ("/research/run-test", "Run test"),
            ("/research/backtest-results", "Results"),
            ("/research/compare-backtests", "Compare"),
        ),
    ),
    (
        "Research support",
        (
            ("/research/market-data", "Market data"),
        ),
    ),
    (
        "Paper Trading",
        (
            ("/paper/fleet", "Paper Trading Overview"),
            ("/paper/strategy", "Strategy Monitor"),
        ),
    ),
    (
        "System",
        (
            ("/system", "System status"),
            ("/system/providers", "Data sources"),
        ),
    ),
    (
        "Global",
        (
            ("/settings", "Settings"),
        ),
    ),
)

NAVIGATION_LINKS = tuple(
    (path, label)
    for _, links in NAVIGATION_GROUPS
    for path, label in links
)

ROUTE_REGISTRY = (
    ("/", "route-home"),
    ("/research/ideas", "route-research-ideas"),
    ("/research/setup", "route-research-setup"),
    ("/research/run-test", "route-research-run-test"),
    ("/research/market-data", "route-research-market-data"),
    ("/research/backtest-results", "route-research-backtest-results"),
    ("/research/compare-backtests", "route-research-compare-backtests"),
    ("/paper/fleet", "route-paper-fleet"),
    ("/paper/strategy", "route-paper-strategy"),
    ("/system", "route-system"),
    ("/system/providers", "route-system-providers"),
    ("/settings", "route-settings"),
)

ROUTE_PATHS = tuple(path for path, _ in ROUTE_REGISTRY)
ROUTE_CONTAINER_IDS = tuple(container_id for _, container_id in ROUTE_REGISTRY) + (
    "route-not-found",
)
VISIBLE_ROUTE_STYLE = {"display": "block"}
HIDDEN_ROUTE_STYLE = {"display": "none"}


def route_container_id(pathname: str) -> str:
    return dict(ROUTE_REGISTRY)[pathname]


def navigation_link_id(path: str) -> str:
    return f"navigation-link-{path.strip('/').replace('/', '-') or 'overview'}"


def navigation_item_id(path: str) -> str:
    return f"navigation-item-{path.strip('/').replace('/', '-') or 'overview'}"


def navigation_classes_for_path(pathname: str | None) -> tuple[str, ...]:
    route = pathname or "/"
    return tuple(
        (
            "navigation-link navigation-link-active"
            if path == route
            else "navigation-link"
        )
        for path, _ in NAVIGATION_LINKS
    )


def navigation_current_states_for_path(
    pathname: str | None,
) -> tuple[str | None, ...]:
    route = pathname or "/"
    return tuple("page" if path == route else None for path, _ in NAVIGATION_LINKS)


def route_container_styles_for_path(pathname: str | None) -> tuple[dict[str, str], ...]:
    route = pathname or "/"
    known_route = route if route in ROUTE_PATHS else None
    styles = [
        VISIBLE_ROUTE_STYLE if path == known_route else HIDDEN_ROUTE_STYLE
        for path, _ in ROUTE_REGISTRY
    ]
    styles.append(VISIBLE_ROUTE_STYLE if known_route is None else HIDDEN_ROUTE_STYLE)
    return tuple(styles)


def active_route(pathname: str | None, expected_pathname: str) -> bool:
    return (pathname or "/") == expected_pathname
