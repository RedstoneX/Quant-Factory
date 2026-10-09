"""Compatibility imports for the Dashboard presentation layer.

State projection belongs to :mod:`dashboard.overview_projection`; this module
contains no persistence or lifecycle logic.
"""

from dashboard.overview_projection import (
    configured_database_path,
    load_dashboard_snapshot,
    load_drilldown_page,
)

__all__ = [
    "configured_database_path",
    "load_dashboard_snapshot",
    "load_drilldown_page",
]
