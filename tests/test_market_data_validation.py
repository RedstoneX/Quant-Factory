"""Market-data integrity validation."""

import pandas as pd
import pytest

from market_data.validation import clean_and_validate_data, expected_session_gaps


def test_incomplete_session_excluded_and_prior_retained(
    market_config, market_frame_factory
) -> None:
    frame = market_frame_factory(market_config.requested_start, "2025-07-03")
    cleaned, _ = clean_and_validate_data(
        frame,
        config=market_config,
        completed_through=pd.Timestamp("2025-07-02"),
        current_date=pd.Timestamp("2025-07-03").date(),
    )
    assert cleaned.index[-1].date().isoformat() == "2025-07-02"


def test_duplicates_and_missing_values_rejected(market_config, market_frame_factory) -> None:
    frame = market_frame_factory(market_config.requested_start, "2016-01-08")
    with pytest.raises(RuntimeError, match="duplicate timestamps"):
        clean_and_validate_data(
            pd.concat([frame, frame.iloc[[-1]]]),
            market_config,
            pd.Timestamp("2016-01-08"),
            pd.Timestamp("2016-01-08").date(),
        )
    frame.loc[frame.index[-1], "Close"] = float("nan")
    with pytest.raises(RuntimeError, match="Close=1"):
        clean_and_validate_data(
            frame,
            market_config,
            pd.Timestamp("2016-01-08"),
            pd.Timestamp("2016-01-08").date(),
        )


def test_future_dates_rejected(market_config, market_frame_factory) -> None:
    frame = market_frame_factory(market_config.requested_start, "2016-01-11")
    with pytest.raises(RuntimeError, match="future-dated"):
        clean_and_validate_data(
            frame,
            market_config,
            pd.Timestamp("2016-01-08"),
            pd.Timestamp("2016-01-08").date(),
        )


def test_gap_analysis_uses_exchange_sessions(market_config, market_frame_factory) -> None:
    holiday_span = market_frame_factory("2025-01-17", "2025-01-21")
    assert expected_session_gaps(holiday_span, market_config) == []
    missing = market_frame_factory("2025-01-06", "2025-01-08").drop(
        pd.Timestamp("2025-01-07", tz=market_config.market_timezone)
    )
    assert expected_session_gaps(missing, market_config) == ["2025-01-07"]
