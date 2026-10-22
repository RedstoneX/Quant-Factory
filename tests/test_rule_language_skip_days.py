"""rule_spec ``skip_days``: no new entries on CPI release days / FOMC decision days."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rule_language import RuleSpecError, validate_rule_spec
from tests.test_rule_spec_strategy import DAYS, _frame, _run, _spec

LONG_AT_10 = [{"when": {"time_is": "10:00"}, "side": "long"}]
CALENDARS = Path(__file__).resolve().parent.parent / "market_data" / "calendars"
CPI_DAY = pd.Timestamp("2026-10-14")  # a CPI release day inside the fixture days


def _entry_days(signals) -> list[str]:
    return [stamp.tz_convert("America/New_York").strftime("%Y-%m-%d") for stamp in signals.entries[signals.entries].index]


@pytest.mark.parametrize("names", [[], ["cpi"], ["fomc"], ["cpi", "fomc"]])
def test_validation_accepts_known_calendars(names) -> None:
    assert validate_rule_spec(_spec(LONG_AT_10, skip_days=names), variables={}).get("skip_days", []) == names


@pytest.mark.parametrize("bad", [["nfp"], ["cpi", "cpi"], "cpi", [1], None])
def test_validation_rejects_unknown_duplicate_or_malformed(bad) -> None:
    with pytest.raises(RuleSpecError):
        validate_rule_spec(_spec(LONG_AT_10, skip_days=bad), variables={})


def test_entry_on_a_cpi_day_is_blocked_only_when_skip_days_names_cpi() -> None:
    frame = _frame([np.full(78, 100.0)] * len(DAYS))
    assert str(CPI_DAY.date()) in _entry_days(_run(_spec(LONG_AT_10), frame))
    for names in (["cpi"], ["cpi", "fomc"]):
        days = _entry_days(_run(_spec(LONG_AT_10, skip_days=names), frame))
        assert str(CPI_DAY.date()) not in days
        assert len(days) == len(DAYS) - 1
    assert len(_entry_days(_run(_spec(LONG_AT_10, skip_days=["fomc"]), frame))) == len(DAYS)


@pytest.mark.parametrize("name, must_contain", [("cpi_release_dates.txt", "2024-01-11"), ("fomc_decision_dates.txt", "2024-09-18")])
def test_shipped_calendars_parse_sorted_and_hold_known_dates(name, must_contain) -> None:
    dates = pd.read_csv(CALENDARS / name, header=None, comment="#")[0]
    parsed = pd.to_datetime(dates, format="%Y-%m-%d")
    assert parsed.is_monotonic_increasing and parsed.is_unique
    assert must_contain in set(dates)
