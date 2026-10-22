"""Fail-closed cache-only behavior for dashboard candidate launches."""

from __future__ import annotations

import pandas as pd
import pytest

import market_data
from market_data import DatasetUnavailableError, load_market_data


def test_cache_only_loader_reuses_compatible_cache(
    market_config,
    market_frame_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = market_frame_factory(market_config.requested_start, "2016-07-08")
    audit = market_data._build_audit(
        frame,
        config=market_config,
        completed_through=pd.Timestamp("2016-07-08"),
        provider_warnings=[],
        cache_action="created",
        cache_decision_reason="fixture",
        download_time=pd.Timestamp("2016-07-08 17:00", tz=market_config.market_timezone),
    )
    market_data.write_cache(frame, audit, market_config)
    monkeypatch.setattr(
        market_data,
        "download_yahoo_data",
        lambda *_args, **_kwargs: pytest.fail("cache-only path attempted a download"),
    )

    result = load_market_data(
        market_config,
        now=pd.Timestamp("2016-07-08 17:00", tz=market_config.market_timezone),
        allow_download=False,
    )

    assert result.audit.cache_action == "reused"


def test_cache_only_loader_fails_before_provider_download(
    market_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        market_data,
        "download_yahoo_data",
        lambda *_args, **_kwargs: pytest.fail("cache-only path attempted a download"),
    )

    with pytest.raises(DatasetUnavailableError, match="downloads are disabled"):
        load_market_data(
            market_config,
            now=pd.Timestamp("2016-07-08 17:00", tz=market_config.market_timezone),
            allow_download=False,
        )


def test_market_data_default_still_allows_provider_download(
    market_config,
    market_frame_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = market_frame_factory(market_config.requested_start, "2016-07-08")
    calls: list[str] = []

    def provider(_config, _completed_through):
        calls.append("download")
        return frame, []

    monkeypatch.setattr(market_data, "download_yahoo_data", provider)

    result = load_market_data(
        market_config,
        now=pd.Timestamp("2016-07-08 17:00", tz=market_config.market_timezone),
    )

    assert calls == ["download"]
    assert result.audit.cache_action == "created"
