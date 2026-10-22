from datetime import datetime, timezone

import pytest

from dashboard.factory_projection import _display_timestamp
from dashboard.time_display import eastern_label, eastern_session, eastern_time_label


@pytest.mark.parametrize(
    ("utc_text", "expected"),
    [
        ("2026-01-15T14:40:00Z", "Jan 15, 2026 · 9:40 AM ET"),
        ("2026-10-15T01:40:00+00:00", "Oct 14, 2026 · 9:40 PM ET"),
        ("2026-07-04T16:05:00Z", "Jul 4, 2026 · 12:05 PM ET"),
    ],
)
def test_label_winter_and_summer(utc_text: str, expected: str) -> None:
    assert eastern_label(utc_text) == expected


def test_day_boundary_goes_to_previous_day() -> None:
    assert eastern_label("2026-07-05T03:30:00Z") == "Jul 4, 2026 · 11:30 PM ET"
    assert eastern_session("2026-01-05T03:30:00Z") == "2026-01-04"


def test_naive_input_is_treated_as_utc_and_clock_label() -> None:
    assert eastern_label(datetime(2026, 7, 1, 12, 0)) == "Jul 1, 2026 · 8:00 AM ET"
    assert eastern_time_label(datetime(2026, 1, 1, 17, 5, 9, tzinfo=timezone.utc)) == "12:05:09 PM ET"


def test_factory_grid_label_is_eastern() -> None:
    assert _display_timestamp("2026-10-15T01:40:00Z") == "Oct 14, 2026 · 9:40 PM ET"
    assert _display_timestamp(None) == "—"
