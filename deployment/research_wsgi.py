"""Factory for the research dashboard with read-only application source.

The container entrypoint validates mounted paths before Gunicorn calls this
factory.  Keeping construction in a factory makes import inspection safe and
ensures the app receives explicit persistence paths rather than host defaults.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from persistence.database import LATEST_SCHEMA_VERSION


def _required_absolute_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError(f"{name} must be absolute")
    return path


def build_dashboard_app():
    """Build the Dash app with its external database and artifact root."""
    database = _required_absolute_path("QUANT_FACTORY_DB_PATH")
    artifact_root = _required_absolute_path("QUANT_FACTORY_ARTIFACT_ROOT")
    return create_app(
        review_database=database,
        run_detail_adapter=RunDetailDashboardAdapter(
            database=database,
            artifact_root=artifact_root,
        ),
    )


def _database_is_readable(database: Path) -> bool:
    if not database.is_file():
        return False
    try:
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                return False
            row = connection.execute(
                "SELECT schema_version FROM schema_metadata"
            ).fetchone()
            if row != (LATEST_SCHEMA_VERSION,):
                return False
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return True


def register_health_endpoint(server, database: Path) -> None:
    """Expose only revision and read-only SQLite availability for orchestration."""

    @server.get("/healthz")
    def healthz():
        if not _database_is_readable(database):
            return {"status": "unhealthy", "revision": os.getenv("QF_REVISION", "unknown")}, 503
        return {"status": "healthy", "revision": os.getenv("QF_REVISION", "unknown")}, 200


def create_server():
    """Gunicorn factory target; no dashboard application is created at import time."""
    dashboard_app = build_dashboard_app()
    database = _required_absolute_path("QUANT_FACTORY_DB_PATH")
    register_health_endpoint(dashboard_app.server, database)
    return dashboard_app.server
