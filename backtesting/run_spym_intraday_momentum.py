"""Bounded SPYM intraday-momentum screen with a local mixed-price adapter."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pandas as pd

from backtesting.screening import ScreeningConfig, screen_metrics
from backtesting.vectorbt_runtime import require_vectorbtpro
from market_data import DataAudit, MarketDataConfig
from market_data.catalog import DatasetManifest, load_data_locations, load_dataset_manifest, verify_dataset_file
from market_data.equity_contract import SPYM_EQUITY_DATA_CONTRACT, validate_spym_manifest
from strategies.spym_intraday_momentum import (
    SPYM_INTRADAY_MOMENTUM_SPEC,
    generate_intraday_momentum_signal_bundle,
)

DATASET_ID = SPYM_EQUITY_DATA_CONTRACT.dataset_id
DATASET_MANIFEST_REFERENCE = SPYM_EQUITY_DATA_CONTRACT.manifest_reference
EXPECTED_DATASET_SHA256 = "0fac9de8cb97568c7ee5ae00532277d960c316989ccd65296c394f0dfa44a5ab"
EXPECTED_DATASET_ROWS = 53_528
EXPECTED_FIRST_TIMESTAMP = "2025-10-31T13:30:00+00:00"
EXPECTED_LAST_TIMESTAMP = "2026-07-13T19:59:00+00:00"
INITIAL_CASH = 10_000.0
FEE_RATE = 0.0005
SLIPPAGE_RATE = 0.0002
SESSIONS_PER_YEAR = 252
RISK_FREE_RATE = 0.0
EXPERIMENT_ID = "decision_296_spym_intraday_momentum"
EXPECTED_ELIGIBLE_SESSIONS = 133
EXPECTED_LONG_SESSIONS = 70
EXPECTED_SHORT_SESSIONS = 63
EXPECTED_ZERO_SIGNALS = 0
EVIDENCE_LABEL = "source_defined_development_screen"
EVIDENCE_CLASSIFICATION = (
    "development/reference evidence only; not independent, OOS, protected, or edge proof"
)

PROMOTION_BLOCKERS = (
    "The full stored extent was already inspected; this is development/reference evidence only.",
    "History is short and raw prices can make dividend gaps affect the signal.",
    "Databento EQUS.MINI is not the official closing auction and required boundary bars remain missing.",
    "Alpaca shortability and account eligibility are unverified.",
    "No protected, out-of-sample, walk-forward, paper, or live evidence was evaluated.",
)


@dataclass(frozen=True)
class SPYMMomentumExecution:
    data: pd.DataFrame
    audit: DataAudit
    manifest: DatasetManifest
    dataset_path: Path


def execution_assumptions() -> dict[str, Any]:
    return {
        "kind": "decision_296_spym_intraday_momentum",
        "engine": "vectorbtpro",
        "broker_orders": "disabled",
        "initial_cash": INITIAL_CASH,
        "leverage": 1.0,
        "position_sizing": "all_available_cash",
        "accumulate": False,
        "fees_per_transaction": FEE_RATE,
        "adverse_slippage_per_transaction": SLIPPAGE_RATE,
        "signal": "previous regular-session 15:59 Close to current 09:59 Close",
        "direction": "positive long; zero or negative short",
        "entry": "current 15:30 Open",
        "exit": "current 15:59 Close",
        "annualization": {
            "sessions_per_year": SESSIONS_PER_YEAR,
            "risk_free_rate": RISK_FREE_RATE,
            "basis": "end-of-session strategy equity and daily returns",
        },
        "max_drawdown_basis": "end-of-eligible-session strategy equity only",
        "max_drawdown_limitation": (
            "Intraday equity path between eligible session endpoints is not represented "
            "in the recorded maximum drawdown."
        ),
    }


def market_data_identity() -> dict[str, Any]:
    contract = SPYM_EQUITY_DATA_CONTRACT
    return {
        "dataset_id": contract.dataset_id,
        "manifest_reference": contract.manifest_reference,
        "symbol": contract.symbol,
        "provider": contract.provider,
        "dataset": contract.dataset,
        "schema": contract.schema,
        "timeframe": contract.timeframe,
        "calendar": contract.calendar,
        "session_policy": contract.session_policy,
        "timezone": contract.timestamp_timezone,
        "adjustment": contract.adjustment,
    }


def saved_configuration_document() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "strategy_id": SPYM_INTRADAY_MOMENTUM_SPEC.identity.strategy_id,
        "strategy_version": SPYM_INTRADAY_MOMENTUM_SPEC.identity.version,
        "market_data": market_data_identity(),
        "parameters": {"fixed_rule_count": 1, "parameters": {}},
        "execution": execution_assumptions(),
        "ranking": {"columns": ("total_return",), "ascending": (False,)},
        "screening": ScreeningConfig.provisional_defaults().to_dict(),
        "controlled_research": {
            "decision": 296,
            "evidence_scope": "development_reference_only",
            "promotion_eligible": False,
            "promotion_blockers": PROMOTION_BLOCKERS,
        },
    }


def _load_frame(path: Path, manifest: DatasetManifest) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    expected = ("timestamp", "open", "high", "low", "close", "volume")
    if tuple(frame.columns) != expected:
        raise RuntimeError(f"SPYM parquet columns do not match the manifest contract: {tuple(frame.columns)}")
    if len(frame) != manifest.row_count:
        raise RuntimeError("SPYM parquet row count does not match its manifest")
    frame = frame.rename(columns={
        "timestamp": "Timestamp", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
    }).set_index("Timestamp")
    if str(frame.index.tz) != "UTC" or frame.index.duplicated().any() or not frame.index.is_monotonic_increasing:
        raise RuntimeError("SPYM parquet timestamps must be unique, chronological UTC values")
    if frame[["Open", "High", "Low", "Close", "Volume"]].isna().any().any():
        raise RuntimeError("SPYM parquet contains null OHLCV values")
    return frame


def _audit_from_manifest(manifest: DatasetManifest) -> DataAudit:
    metadata = manifest.metadata
    nulls = metadata.get("null_counts", {})
    return DataAudit(
        cache_schema_version=2, symbol="SPYM", provider="Databento",
        provider_implementation=f"{metadata['dataset']} {metadata['schema']}", interval="1m",
        requested_start=metadata["coverage_start"], requested_dynamic_end_policy=metadata["coverage_end_policy"],
        latest_completed_exchange_session=metadata["latest_completed_session"], prices_adjusted=False,
        adjustment_verification="Databento manifest adjustment=raw", download_time=metadata["imported_at_utc"],
        download_timezone="UTC", actual_first_row_date=metadata["earliest_timestamp"],
        actual_last_row_date=metadata["latest_timestamp"], row_count=manifest.row_count,
        duplicate_timestamp_count=int(metadata["duplicate_timestamp_count"]),
        missing_open_count=int(nulls.get("open", 0)), missing_high_count=int(nulls.get("high", 0)),
        missing_low_count=int(nulls.get("low", 0)), missing_close_count=int(nulls.get("close", 0)),
        missing_volume_count=int(nulls.get("volume", 0)), expected_session_gap_count=int(metadata["missing_session_count"]),
        unexpected_session_gaps=list(metadata.get("missing_sessions", ())),
        provider_warnings=["Sparse EQUS.MINI bars are not forward-filled or made synthetic."],
        cache_path=str(manifest.canonical_relative_path), cache_action="verified",
        cache_decision_reason="checksum-matching approved manifest verified before use",
    )


def load_spym_intraday_momentum_inputs() -> SPYMMomentumExecution:
    manifest = load_dataset_manifest(DATASET_ID)
    validate_spym_manifest(manifest.metadata)
    if manifest.sha256 != EXPECTED_DATASET_SHA256 or manifest.row_count != EXPECTED_DATASET_ROWS:
        raise RuntimeError("SPYM manifest identity does not match Decision 296")
    dataset_path = verify_dataset_file(manifest, load_data_locations(), require_validated=True)
    data = _load_frame(dataset_path, manifest)
    _assert_exact_dataset(manifest.metadata, data)
    return SPYMMomentumExecution(data=data, audit=_audit_from_manifest(manifest), manifest=manifest, dataset_path=dataset_path)


def _assert_exact_dataset(metadata: Mapping[str, Any], data: pd.DataFrame) -> None:
    expected = {"dataset_id": DATASET_ID, "status": "validated", "sha256": EXPECTED_DATASET_SHA256,
                "row_count": EXPECTED_DATASET_ROWS, "earliest_timestamp": EXPECTED_FIRST_TIMESTAMP,
                "latest_timestamp": EXPECTED_LAST_TIMESTAMP, "symbol": "SPYM", "dataset": "EQUS.MINI",
                "schema": "ohlcv-1m", "adjustment": "raw"}
    mismatches = {key: (metadata.get(key), value) for key, value in expected.items() if metadata.get(key) != value}
    if mismatches:
        raise RuntimeError(f"SPYM dataset identity does not match Decision 296: {mismatches}")
    if len(data) != EXPECTED_DATASET_ROWS or data.index[0].isoformat() != EXPECTED_FIRST_TIMESTAMP or data.index[-1].isoformat() != EXPECTED_LAST_TIMESTAMP:
        raise RuntimeError("SPYM dataset extent does not match the already-inspected Decision-296 extent")


def exact_execution_prices(data: pd.DataFrame, signals) -> pd.Series:
    """Return the exact observed entry-open/exit-close price series for VectorBT."""
    price = data["Close"].astype(float).copy()
    long_entries = signals.entries.astype(bool)
    long_exits = signals.exits.astype(bool)
    short_entries = signals.short_entries.astype(bool)
    short_exits = signals.short_exits.astype(bool)
    buy_orders = long_entries | short_exits
    sell_orders = long_exits | short_entries
    if (buy_orders & sell_orders).any():
        raise RuntimeError("mixed-price adapter cannot price simultaneous buy and sell orders")
    price.loc[long_entries | short_entries] = data.loc[long_entries | short_entries, "Open"].astype(float)
    price.loc[long_exits | short_exits] = data.loc[long_exits | short_exits, "Close"].astype(float)
    return price


def assert_readiness(bundle) -> None:
    """Keep the approved dataset readiness measurement reproducible and fail closed."""
    expected = {
        "eligible_session_count": EXPECTED_ELIGIBLE_SESSIONS,
        "long_session_count": EXPECTED_LONG_SESSIONS,
        "short_session_count": EXPECTED_SHORT_SESSIONS,
        "zero_signal_count": EXPECTED_ZERO_SIGNALS,
    }
    observed = bundle.signals.metadata
    mismatches = {
        key: (observed.get(key), value)
        for key, value in expected.items()
        if observed.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"SPYM session readiness does not match Decision 296: {mismatches}")


def validate_candidate_execution(data: pd.DataFrame, bundle, price: pd.Series) -> tuple[dict[str, Any], ...]:
    """Fail closed on the local adapter's exact signal and price contract."""
    signals = bundle.signals
    pairs = {
        "long": (signals.entries, signals.exits),
        "short": (signals.short_entries, signals.short_exits),
    }
    for name, (entries, exits) in pairs.items():
        if entries is None or exits is None or not entries.index.equals(data.index) or not exits.index.equals(data.index):
            raise RuntimeError(f"{name} signal index does not match the SPYM data index")
        if entries.isna().any() or exits.isna().any() or entries.dtype != bool or exits.dtype != bool:
            raise RuntimeError(f"{name} signals must be non-null boolean series")
        if int(entries.sum()) != int(exits.sum()):
            raise RuntimeError(f"{name} signal entries and exits must be paired")
    if (signals.entries & signals.short_entries).any() or (signals.exits & signals.short_exits).any():
        raise RuntimeError("a session cannot contain simultaneous long and short signals")
    if int(signals.entries.sum() + signals.short_entries.sum()) != len(bundle.eligible_sessions):
        raise RuntimeError("each eligible session must have exactly one entry")
    if int(signals.exits.sum() + signals.short_exits.sum()) != len(bundle.eligible_sessions):
        raise RuntimeError("each eligible session must have exactly one exit")
    if not price.index.equals(data.index) or price.isna().any() or not price.map(math.isfinite).all() or (price <= 0).any():
        raise RuntimeError("mixed execution prices must be positive finite values aligned to SPYM data")
    for session in bundle.eligible_sessions:
        entry_is_long = bool(signals.entries.at[session.entry_timestamp])
        exit_is_long = bool(signals.exits.at[session.exit_timestamp])
        if entry_is_long != (session.signal == "long") or exit_is_long != (session.signal == "long"):
            raise RuntimeError("eligible session direction does not match its entry and exit signals")
        if price.at[session.entry_timestamp] != float(data.at[session.entry_timestamp, "Open"]):
            raise RuntimeError("entry price is not the observed 15:30 open")
        if price.at[session.exit_timestamp] != float(data.at[session.exit_timestamp, "Close"]):
            raise RuntimeError("exit price is not the observed 15:59 close")
    return (
        {"gate_id": "mixed_price.signal_pairs", "status": "passed", "eligible_session_count": len(bundle.eligible_sessions)},
        {"gate_id": "mixed_price.exact_prices", "status": "passed", "entry": "15:30 Open", "exit": "15:59 Close"},
    )


def validate_completed_trades(portfolio, bundle) -> tuple[dict[str, Any], ...]:
    """Fail closed unless VectorBT reports one closed trade for every eligible session."""
    trades = portfolio.trades.records_readable
    if not isinstance(trades, pd.DataFrame):
        raise RuntimeError("VectorBT readable trades must be a dataframe")
    expected = len(bundle.eligible_sessions)
    if len(trades) != expected:
        raise RuntimeError(
            f"VectorBT completed-trade count {len(trades)} does not match {expected} eligible sessions"
        )
    if "Status" not in trades.columns:
        raise RuntimeError("VectorBT readable trades must expose Status for closed-trade validation")
    statuses = trades["Status"].astype(str).str.strip().str.lower()
    if not statuses.eq("closed").all():
        raise RuntimeError("VectorBT readable trades contain an open or non-closed trade")
    validation: list[dict[str, Any]] = [
        {
            "gate_id": "mixed_price.completed_trades",
            "status": "passed",
            "completed_trade_count": len(trades),
            "eligible_session_count": expected,
            "open_trade_count": 0,
        }
    ]
    if "Direction" not in trades.columns:
        raise RuntimeError("VectorBT readable trades must expose Direction for direction validation")
    directions = trades["Direction"].astype(str).str.strip().str.lower()
    observed = {"long": int(directions.eq("long").sum()), "short": int(directions.eq("short").sum())}
    expected_directions = {
        "long": int(bundle.signals.metadata["long_session_count"]),
        "short": int(bundle.signals.metadata["short_session_count"]),
    }
    if observed != expected_directions or int((~directions.isin(("long", "short"))).sum()):
        raise RuntimeError(
            "VectorBT readable trade directions do not match the eligible long/short session counts"
        )
    validation.append(
        {
            "gate_id": "mixed_price.completed_trade_directions",
            "status": "passed",
            "long_trade_count": observed["long"],
            "short_trade_count": observed["short"],
        }
    )
    orders = portfolio.orders.records_readable
    if not isinstance(orders, pd.DataFrame):
        raise RuntimeError("VectorBT readable orders must be a dataframe")
    expected_orders = expected * 2
    if len(orders) != expected_orders:
        raise RuntimeError(
            f"VectorBT filled-order count {len(orders)} does not match {expected_orders} required entry/exit fills"
        )
    validation.append(
        {
            "gate_id": "mixed_price.filled_orders",
            "status": "passed",
            "filled_order_count": len(orders),
            "expected_entry_exit_fill_count": expected_orders,
        }
    )
    return tuple(validation)


def build_mixed_price_portfolio(data: pd.DataFrame, bundle):
    """Smallest candidate-local VectorBT call preserving the approved prices."""
    vbt = require_vectorbtpro()
    signals = bundle.signals
    price = exact_execution_prices(data, signals)
    validate_candidate_execution(data, bundle, price)
    return vbt.Portfolio.from_signals(
        close=data["Close"].astype(float), entries=signals.entries, exits=signals.exits,
        short_entries=signals.short_entries, short_exits=signals.short_exits,
        price=price, size=float("inf"), direction=None,
        accumulate=False, leverage=1.0, init_cash=INITIAL_CASH, fees=FEE_RATE,
        slippage=SLIPPAGE_RATE,
    )


def daily_equity_and_returns(value: pd.Series, eligible_sessions: tuple[Any, ...]) -> tuple[pd.Series, pd.Series]:
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise RuntimeError("expected one-column VectorBT strategy equity")
        value = value.iloc[:, 0]
    if not isinstance(value.index, pd.DatetimeIndex) or value.index.tz is None or value.empty:
        raise RuntimeError("strategy equity must be a non-empty timezone-aware time series")
    local_dates = value.index.tz_convert("America/New_York").normalize()
    daily_equity = value.groupby(local_dates).last().astype(float)
    daily_equity.index.name = "session"
    eligible_dates = {pd.Timestamp(item.session_date, tz="America/New_York").normalize() for item in eligible_sessions}
    daily_equity = daily_equity.loc[daily_equity.index.isin(eligible_dates)]
    if len(daily_equity) != len(eligible_sessions):
        raise RuntimeError("daily strategy equity does not cover every eligible session")
    baseline = pd.Series([INITIAL_CASH], index=[daily_equity.index[0] - pd.Timedelta(days=1)])
    returns = pd.concat([baseline, daily_equity]).pct_change().iloc[1:]
    return daily_equity, returns.astype(float)


def daily_metrics(portfolio, bundle) -> dict[str, float | int]:
    daily_equity, returns = daily_equity_and_returns(portfolio.value, bundle.eligible_sessions)
    if len(returns) < 2:
        raise RuntimeError("at least two daily equity observations are required for annualized metrics")
    total_return = float(daily_equity.iloc[-1] / INITIAL_CASH - 1.0)
    annualized_return = float((1.0 + total_return) ** (SESSIONS_PER_YEAR / len(returns)) - 1.0)
    volatility = float(returns.std(ddof=1))
    sharpe_ratio = 0.0 if volatility == 0 else float((returns.mean() - RISK_FREE_RATE / SESSIONS_PER_YEAR) / volatility * SESSIONS_PER_YEAR ** 0.5)
    equity_with_baseline = pd.concat([pd.Series([INITIAL_CASH]), daily_equity.reset_index(drop=True)], ignore_index=True)
    max_drawdown = float((equity_with_baseline / equity_with_baseline.cummax() - 1.0).min())
    trade_count = int(float(portfolio.trades.count()))
    return {"total_return": total_return, "annualized_return": annualized_return, "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown, "number_of_trades": trade_count,
            "win_rate": float(portfolio.trades.win_rate)}


def execute_spym_intraday_momentum(data: pd.DataFrame, audit: DataAudit) -> tuple[Any, Any, Any]:
    bundle = generate_intraday_momentum_signal_bundle(data)
    assert_readiness(bundle)
    portfolio = build_mixed_price_portfolio(data, bundle)
    adapter_validation = validate_candidate_execution(
        data, bundle, exact_execution_prices(data, bundle.signals)
    )
    trade_validation = validate_completed_trades(portfolio, bundle)
    metrics = daily_metrics(portfolio, bundle)
    screening = screen_metrics(experiment_id=EXPERIMENT_ID, strategy_id=SPYM_INTRADAY_MOMENTUM_SPEC.identity.strategy_id,
                              strategy_version=SPYM_INTRADAY_MOMENTUM_SPEC.identity.version, parameters={},
                              execution_assumptions=execution_assumptions(), metrics=metrics,
                              config=ScreeningConfig.provisional_defaults())
    row = metrics | {"parameter_row_id": screening.parameter_row_id,
                     "screening_status": "passed" if screening.passed else "screened_out",
                     "screening_passed_rule_count": screening.passed_rule_count,
                     "screening_failed_rule_count": screening.failed_rule_count,
                     "screening_rejection_reasons": " | ".join(screening.rejection_reasons)}
    result = SimpleNamespace(ranked_results=pd.DataFrame([row]), passing_results=pd.DataFrame([row]) if screening.passed else pd.DataFrame(columns=row),
                             screened_out_results=pd.DataFrame([row]) if not screening.passed else pd.DataFrame(columns=row),
                             experiment_id=EXPERIMENT_ID, strategy_id=SPYM_INTRADAY_MOMENTUM_SPEC.identity.strategy_id,
                             strategy_name=SPYM_INTRADAY_MOMENTUM_SPEC.identity.name, strategy_version=SPYM_INTRADAY_MOMENTUM_SPEC.identity.version,
                             normalized_parameters=({},), market_data_audit=audit, execution_assumptions=execution_assumptions(),
                             evaluated_combinations=1, rejected_combinations=0, rejections=(),
                             validation_results=adapter_validation + trade_validation,
                             screening_config=ScreeningConfig.provisional_defaults(), screening_results=(screening,), parameter_plan_summary=None)
    return result, portfolio, bundle


def market_data_config(dataset_path: Path) -> MarketDataConfig:
    return MarketDataConfig(symbol="SPYM", provider="Databento", provider_implementation="EQUS.MINI ohlcv-1m",
                            interval="1m", requested_start="2025-10-31", end_date_policy="latest_fully_completed_nyse_session",
                            adjusted=False, exchange_calendar="NYSE", market_timezone="UTC", cache_path=dataset_path)
