from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from backtesting.experiments import runner
from backtesting.experiments.models import ExecutionConfig
from orchestration import auto_campaign, auto_campaign_stocks as stocks
from orchestration.auto_campaign import (
    DatasetProfile,
    auto_test_definition,
    dataset_profile,
)
from backtesting.robustness.models import FractionalCostStressPlan
from orchestration.candidate_pipeline_parsing import parse_robustness_contract
from orchestration.candidate_pipeline_runtime import VALIDATION_RUNTIME_KEY

_SPEC = importlib.util.spec_from_file_location(
    "measure_stock_spreads", Path(__file__).resolve().parents[1] / "tools" / "measure_stock_spreads.py"
)
assert _SPEC and _SPEC.loader
spreads_tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(spreads_tool)

VARIABLES = {"lookback": {"values": [10, 20]}}


def _mes_main_profile() -> DatasetProfile:
    # The exact MES literal from main before this change.
    return DatasetProfile(
        dataset_id="futures_MES_5m_databento", symbol="MES", interval="5m",
        dataset_end="2026-02-13T21:55:00Z", requested_start="2019-05-06",
        end_date_policy="fixed verified catalog end 2026-02-13",
        cache_path=Path("futures/MES/5m/MES_5m_databento.parquet"),
        fixed_fee_per_contract_per_side=0.62, slippage_ticks=1.0, tick_size=0.25, price_multiplier=5.0,
        stress_fee_per_contract_per_side=1.24, stress_slippage_ticks=2.0, annualization_factor=252.0 * 78.0,
    )


def _mes_main_execution() -> ExecutionConfig:
    # auto_test_definition's ExecutionConfig call on main, verbatim.
    return ExecutionConfig.next_bar_open(
        initial_cash=100_000.0, fees=0.0, slippage=0.0, direction="both", leverage=1.0,
        accumulate=False, position_sizing="fixed_units", order_size=1.0,
        price_multiplier=5.0, fixed_fee_per_contract_per_side=0.62, slippage_ticks=1.0, tick_size=0.25,
    )


def _write_fixture(tmp_path: Path, symbols: dict[str, float]) -> tuple[Path, Path]:
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "equities_SPY_1m_alpaca_sip.json").write_text(json.dumps({
        "dataset_id": "equities_SPY_1m_alpaca_sip", "provider": "alpaca",
        "first_available_bar": "2016-01-04T14:30:00Z", "latest_timestamp": "2026-10-13T19:59:00Z",
        "canonical_relative_path": "equities/SPY/1m/SPY_1m_alpaca_sip.a.parquet",
    }))
    spreads = tmp_path / "spreads.json"
    spreads.write_text(json.dumps({
        "measured_at": "2026-10-14T00:00:00Z", "method": "test", "source": "test",
        "symbols": {sym: {"median_spread_bps": bps, "median_mid_price": 650.0, "samples": 9, "sessions": 20}
                    for sym, bps in symbols.items()},
    }))
    return manifests, spreads


def _stock_profile(tmp_path: Path) -> DatasetProfile:
    manifests, spreads = _write_fixture(tmp_path, {"SPY": 0.4})
    return DatasetProfile(**stocks.stock_profile_fields("SPY", manifest_dir=manifests, spreads_path=spreads))


def test_mes_profile_and_definition_are_identical_to_main() -> None:
    profile = dataset_profile("MES", "5m")
    assert profile == _mes_main_profile()
    definition = auto_test_definition(
        candidate_id="c1", strategy_id="s1", strategy_version="1", variables={}, profile=profile,
    )
    experiment = definition.experiment
    assert experiment.execution == _mes_main_execution()
    assert experiment.market_data.provider == "Databento"
    assert experiment.market_data.adjusted is False
    assert asdict(definition.validation.fixed_rule_cost_stress) == {
        "fixed_fee_per_contract_per_side": 1.24, "slippage_ticks": 2.0,
    }
    assert runner._whole_share_args(experiment.execution) == {}


def test_stock_profile_builds_config_from_manifest_and_spreads(tmp_path: Path) -> None:
    profile = _stock_profile(tmp_path)
    definition = auto_test_definition(
        candidate_id="c1", strategy_id="s1", strategy_version="1", variables=VARIABLES, profile=profile,
    )
    market, execution = definition.experiment.market_data, definition.experiment.execution
    assert market.provider_implementation == "verified_local_catalog:equities_SPY_1m_alpaca_sip"
    assert (market.provider, market.interval, market.adjusted) == ("alpaca", "1m", True)
    assert market.requested_start == "2016-01-04T14:30:00Z"
    assert definition.validation.data_as_of == "2026-10-13T19:59:00Z"
    assert execution.initial_cash == 10_000.0
    assert execution.position_sizing == "all_cash_whole_shares" and execution.order_size == 1.0
    assert execution.slippage == pytest.approx(0.2 / 10_000)
    assert execution.fees == pytest.approx((20.60e-6 + 0.000195 / 650.0) / 2)
    stress = definition.validation.fixed_rule_cost_stress
    assert stress is None  # variables present -> neighbourhood test instead
    assert execution.fixed_fee_per_contract_per_side == 0.0 and execution.tick_size == 0.01
    assert definition.validation.robustness_regimes.annualization_factor == 252.0 * 390.0
    document = definition.configuration_document()
    assert json.loads(json.dumps(document, allow_nan=False))["execution"]["order_size"] == 1.0


def test_stress_is_twice_slippage_like_mes(tmp_path: Path) -> None:
    profile = _stock_profile(tmp_path)
    mes = dataset_profile("MES", "5m")
    assert mes.stress_slippage_ticks / mes.slippage_ticks == stocks.STRESS_SLIPPAGE_MULTIPLIER == 2.0
    assert profile.stress_slippage == pytest.approx(2.0 * profile.slippage)


def test_missing_spread_fails_plainly(tmp_path: Path) -> None:
    manifests, spreads = _write_fixture(tmp_path, {"QQQ": 0.5})
    with pytest.raises(stocks.StockCostsUnavailable, match="No measured bid/ask spread for SPY"):
        stocks.stock_profile_fields("SPY", manifest_dir=manifests, spreads_path=spreads)
    priceless = tmp_path / "priceless.json"
    priceless.write_text(json.dumps({"symbols": {"SPY": {"median_spread_bps": 0.4}}}))
    with pytest.raises(stocks.StockCostsUnavailable, match="No measured median_mid_price for SPY"):
        stocks.stock_profile_fields("SPY", manifest_dir=manifests, spreads_path=priceless)
    with pytest.raises(stocks.StockCostsUnavailable, match="No measured spreads file"):
        stocks.half_spread_fraction("SPY", tmp_path / "absent.json")


def test_dataset_profile_returns_none_without_spread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def missing(symbol: str) -> dict:
        raise stocks.StockCostsUnavailable("No measured bid/ask spread")

    monkeypatch.setattr(auto_campaign, "stock_profile_fields", missing)
    assert dataset_profile("SPY", "1m") is None
    assert dataset_profile("NOTREAL", "1m") is None


def test_parameter_free_stock_rule_gets_fractional_stress_that_round_trips(tmp_path: Path) -> None:
    profile = _stock_profile(tmp_path)
    definition = auto_test_definition(
        candidate_id="c1", strategy_id="s1", strategy_version="1", variables={}, profile=profile,
    )
    stress = definition.validation.fixed_rule_cost_stress
    assert isinstance(stress, FractionalCostStressPlan)
    assert (stress.fees, stress.slippage) == (profile.fees, 2.0 * profile.slippage)
    robustness = json.loads(json.dumps(definition.configuration_document(), allow_nan=False))
    robustness = robustness[VALIDATION_RUNTIME_KEY]["robustness"]
    _n, parsed, _r = parse_robustness_contract(robustness, SimpleNamespace(spec=SimpleNamespace(parameters={})), ({},))
    assert parsed == stress


def test_whole_share_sizing_passes_size_granularity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    class Portfolio:
        @staticmethod
        def from_signals(**kwargs):
            calls.append(kwargs)
            return kwargs

    monkeypatch.setattr(runner, "require_vectorbtpro", lambda: SimpleNamespace(Portfolio=Portfolio))
    monkeypatch.setattr(runner, "build_execution_price", lambda data, aligned, execution: data["Open"])
    profile = _stock_profile(tmp_path)
    experiment = auto_test_definition(
        candidate_id="c1", strategy_id="s1", strategy_version="1", variables=VARIABLES, profile=profile,
    ).experiment
    data = pd.DataFrame({"Open": [1.0, 2.0], "Close": [1.0, 2.0]})
    flags = pd.Series([False, False])
    aligned = SimpleNamespace(entries=flags, exits=flags, short_entries=flags, short_exits=flags,
                              stop_loss=None, take_profit=None)
    runner._construct_portfolio(data, aligned, experiment)
    assert calls[0]["size_granularity"] == 1.0 and math.isinf(calls[0]["size"])
    with pytest.raises(ValueError, match="requires order_size 1.0"):
        ExecutionConfig.next_bar_open(initial_cash=1.0, fees=0.0, slippage=0.0, direction="both", leverage=1.0,
                                      accumulate=False, position_sizing="all_cash_whole_shares", order_size=5.0)


def test_spread_maths_with_canned_responses() -> None:
    assert spreads_tool.spread_bps({"bp": 99.99, "ap": 100.01}) == pytest.approx(2.0)
    assert spreads_tool.spread_bps({"bp": 0.0, "ap": 1.0}) is None
    assert spreads_tool.spread_bps({"bp": 1.0, "ap": 1.0}) is None
    pages = {
        None: {"quotes": [{"bp": 99.99, "ap": 100.01}, {"bp": 0, "ap": 5}], "next_page_token": "p2"},
        "p2": {"quotes": [{"bp": 49.99, "ap": 50.01}, {"bp": 9.99, "ap": 10.01}], "next_page_token": None},
    }
    seen: list[dict] = []

    def get(url, *, params, headers, timeout):
        seen.append(params)
        body = pages[params.get("page_token")]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)

    open_utc = datetime(2026, 10, 13, 13, 30, tzinfo=timezone.utc)
    sessions = [(open_utc, datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc))]
    limiter = spreads_tool.RateLimiter(clock_fn=lambda: 0.0, sleep=lambda s: None)
    result = spreads_tool.measure(["SPY"], sessions, get=get, headers={}, limiter=limiter)
    # 3 windows x (2.0, 4.0, 20.0) bps -> median 4.0 over 9 valid quotes.
    assert result == {"SPY": {"median_spread_bps": pytest.approx(4.0), "median_mid_price": pytest.approx(50.0),
                              "samples": 9, "sessions": 1}}
    assert seen[0]["feed"] == "sip" and seen[0]["limit"] == 10_000 and seen[0]["start"] == "2026-10-13T14:00:00Z"
    doc = spreads_tool.document(result, sessions, open_utc)
    assert set(doc) == {"measured_at", "method", "source", "symbols"}


def test_early_close_skips_late_sample_and_rate_limit_sleeps() -> None:
    open_utc = datetime(2026, 11, 27, 14, 30, tzinfo=timezone.utc)
    windows = spreads_tool.sample_windows([(open_utc, datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc))])
    assert len(windows) == 2
    slept: list[float] = []
    limiter = spreads_tool.RateLimiter(2, clock_fn=lambda: 10.0, sleep=slept.append)
    for _ in range(3):
        limiter.wait()
    assert slept == [60.0]
