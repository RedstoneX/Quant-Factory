"""Dashboard route registry and pathname-derived presentation state."""

from __future__ import annotations

NAVIGATION_GROUPS = (
    (
        "Strategy Research",
        (
            ("/research/market-data", "Market Data"),
            ("/research/strategy-review", "Strategy Review"),
            ("/research/backtest-results", "Backtest Results"),
            ("/research/compare-backtests", "Compare Backtests"),
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
            ("/system", "System Status"),
            ("/system/providers", "Data Sources"),
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
    ("/research/market-data", "route-research-market-data"),
    ("/research/backtest-results", "route-research-backtest-results"),
    ("/research/strategy-review", "route-research-strategy-review"),
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
