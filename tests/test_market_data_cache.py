"""Cache compatibility and public loading behavior."""

import pandas as pd
import pytest

import market_data
from market_data import load_market_data
from market_data.cache import cache_compatibility, write_cache


def test_stale_2018_cache_rejected(market_config, market_frame_factory) -> None:
    frame = market_frame_factory("2018-01-01", "2018-01-05")
    audit = market_data._build_audit(
        frame,
        config=market_config,
        completed_through=pd.Timestamp("2018-01-05"),
        provider_warnings=[],
        cache_action="created",
        cache_decision_reason="fixture",
        download_time=pd.Timestamp("2018-01-05", tz=market_config.market_timezone),
    )
    values = audit.to_dict()
    values["requested_start"] = "2018-01-01"
    audit = type(audit).from_dict(values)
    compatible, reason, _ = cache_compatibility(
        frame,
        audit,
        market_config,
        pd.Timestamp("2018-01-05"),
        pd.Timestamp("2018-01-05").date(),
    )
    assert compatible is False
    assert "requested_start" in reason


def test_compatible_cache_reused_offline(
    market_config, market_frame_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = market_frame_factory(market_config.requested_start, "2016-07-08")
    audit = market_data._build_audit(
        frame,
        config=market_config,
        completed_through=pd.Timestamp("2016-07-08"),
        provider_warnings=["saved provider warning"],
        cache_action="created",
        cache_decision_reason="fixture",
        download_time=pd.Timestamp("2016-07-08 17:00", tz=market_config.market_timezone),
    )
    write_cache(frame, audit, market_config)
    monkeypatch.setattr(
        market_data,
        "download_yahoo_data",
        lambda *args, **kwargs: pytest.fail("compatible cache attempted download"),
    )
    result = load_market_data(
        market_config,
        now=pd.Timestamp("2016-07-08 17:00", tz=market_config.market_timezone),
    )
    assert result.audit.cache_action == "reused"
    assert "current" in result.audit.cache_decision_reason
    assert result.audit.provider_warnings == ["saved provider warning"]
