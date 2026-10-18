import json

import pandas as pd

from dashboard.data_freshness import stale_price_banner_text


def _write(folder, symbol, latest, provider="alpaca", timeframe="1m"):
    (folder / f"{symbol}.json").write_text(
        json.dumps({"provider": provider, "timeframe": timeframe, "latest_timestamp": latest}), encoding="utf-8"
    )


SUNDAY = pd.Timestamp("2026-10-18 12:00", tz="UTC")
FRIDAY_LAST_BAR = "2026-10-16T19:59:00Z"
THURSDAY_LAST_BAR = "2026-10-15T19:59:00Z"


def test_all_current_shows_nothing_on_weekend(tmp_path):
    _write(tmp_path, "A", FRIDAY_LAST_BAR)
    _write(tmp_path, "B", FRIDAY_LAST_BAR)
    assert stale_price_banner_text([tmp_path], now=SUNDAY) is None


def test_some_stale_gives_counts_and_dates(tmp_path):
    _write(tmp_path, "A", FRIDAY_LAST_BAR)
    _write(tmp_path, "B", THURSDAY_LAST_BAR)
    _write(tmp_path, "C", THURSDAY_LAST_BAR)
    _write(tmp_path, "FUT", "2020-01-01T00:00:00Z", provider="databento")
    text = stale_price_banner_text([tmp_path], now=SUNDAY)
    assert "2 of 3 stocks end on Thu 15 Oct" in text
    assert "latest trading day was Fri 16 Oct" in text


def test_holiday_uses_prior_session(tmp_path):
    # Thanksgiving 2026 is Thu 26 Nov: Wednesday's data is current that afternoon.
    _write(tmp_path, "A", "2026-11-25T20:59:00Z")
    now = pd.Timestamp("2026-11-26 15:00", tz="UTC")
    assert stale_price_banner_text([tmp_path], now=now) is None
