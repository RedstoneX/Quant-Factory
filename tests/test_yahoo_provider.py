"""Yahoo provider and audit metadata."""

import warnings
from types import SimpleNamespace

import pandas as pd

import market_data
from market_data.models import OHLCV_COLUMNS
from market_data.providers import yahoo


class FakeYFData:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.index = frame.index

    def __len__(self):
        return len(self.frame)

    def get(self, column):
        return self.frame[column]


def test_yahoo_adjustment_and_warning_capture(
    market_config, market_frame_factory, monkeypatch
) -> None:
    frame = market_frame_factory("2016-01-01", "2016-01-08")
    captured = {}

    def fake_pull(*args, **kwargs):
        captured.update(kwargs)
        warnings.warn("provider test warning")
        return FakeYFData(frame)

    monkeypatch.setattr(
        yahoo,
        "require_vectorbtpro",
        lambda: SimpleNamespace(YFData=SimpleNamespace(pull=fake_pull)),
    )
    downloaded, provider_warnings = yahoo.download_yahoo_data(
        market_config,
        pd.Timestamp("2016-01-08"),
    )
    assert list(downloaded.columns) == list(OHLCV_COLUMNS)
    assert captured["auto_adjust"] is True
    assert provider_warnings == ["provider test warning"]


def test_audit_fields_adjustment_provider_lag_and_cache_reason(
    market_config, market_frame_factory
) -> None:
    frame = market_frame_factory(market_config.requested_start, "2025-07-02")
    audit = market_data._build_audit(
        frame,
        config=market_config,
        completed_through=pd.Timestamp("2025-07-03"),
        provider_warnings=[],
        cache_action="refreshed",
        cache_decision_reason="stale coverage",
        download_time=pd.Timestamp("2025-07-03 14:00", tz=market_config.market_timezone),
    )
    assert audit.prices_adjusted is True
    assert "auto_adjust" in audit.adjustment_verification
    assert any("availability lag" in item for item in audit.provider_warnings)
    assert audit.cache_action == "refreshed"
    assert audit.cache_decision_reason == "stale coverage"
    assert set(market_data.AUDIT_FIELDS) == set(audit.to_dict())
