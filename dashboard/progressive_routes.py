"""Build and preserve the active route for the progressive Dash shell."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from dash import Dash


INITIAL_PATH_COOKIE = "qf_dash_initial_pathname"


def create_progressive_dash_app(name: str) -> Dash:
    """Create the dashboard app with the path-preserving progressive shell."""

    app = Dash(
        name,
        prevent_initial_callbacks=True,
        suppress_callback_exceptions=True,
        meta_tags=[
            {
                "name": "viewport",
                "content": (
                    "width=device-width, initial-scale=1, "
                    "maximum-scale=5, user-scalable=yes"
                ),
            }
        ],
    )
    register_initial_path_cookie(app)
    app.title = "Quant Factory"
    return app


def request_pathname_for_initial_layout() -> str:
    try:
        from flask import request
    except RuntimeError:
        return "/"
    if not request:
        return "/"
    return request.cookies.get(INITIAL_PATH_COOKIE) or "/"


def register_initial_path_cookie(app: Dash) -> None:
    @app.server.after_request
    def remember_initial_dashboard_path(response):
        from flask import request

        if request.method == "GET" and not request.path.startswith(
            ("/_dash-", "/assets/", "/_favicon.ico")
        ):
            response.set_cookie(
                INITIAL_PATH_COOKIE,
                request.path or "/",
                max_age=30,
                samesite="Lax",
            )
        return response


def live_route_renderer(
    page_renderer: Callable[..., Any],
    context: Any,
    configurations: tuple[Any, ...] | None,
    runs: Any,
    layout_options: Mapping[str, Any],
    health_reader: Callable[..., Any],
    required_dataset_ids: frozenset[str],
) -> Callable[[str], Any]:
    """Return a renderer that builds only the newly active route."""

    def render(pathname: str) -> Any:
        health_readings = (
            health_reader(
                database=layout_options["dashboard_database"],
                artifact_root=layout_options["artifact_root"],
                catalog_snapshot=layout_options["catalog_snapshot"],
                catalog_checked_at=layout_options["catalog_checked_at"],
                required_dataset_ids=required_dataset_ids,
            )
            if pathname in {"/", "/system"}
            else ()
        )
        return page_renderer(
            pathname,
            context,
            configurations,
            recent_runs=runs.recent_runs(limit=20),
            recent_events=runs.recent_events(limit=20),
            selected_run_panel=layout_options["selected_run_panel"],
            selected_run_id=None,
            dashboard_database=layout_options["dashboard_database"],
            artifact_root=layout_options["artifact_root"],
            catalog_snapshot=layout_options["catalog_snapshot"],
            readiness_by_id=dict(layout_options["readiness_by_id"]),
            home_health_readings=health_readings,
            health_stale_after=layout_options["health_stale_after"],
            health_refresh_interval_ms=layout_options["health_refresh_interval_ms"],
        )

    return render
