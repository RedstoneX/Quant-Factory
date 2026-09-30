"""Execute the one fixed MES overnight-gap reversal development screen."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import pandas as pd

from backtesting.screening import ScreeningConfig, screen_metrics
from backtesting.vectorbt_runtime import require_vectorbtpro
from market_data import (
    DataAudit,
    DatasetManifest,
    load_data_locations,
    load_dataset_manifest,
    verify_dataset_file,
)
from strategies.models import SignalResult
from strategies.mes_overnight_gap_reversal import (
    DEVELOPMENT_SESSION_END,
    DEVELOPMENT_SESSION_START,
    FEE_PER_SIDE,
    INITIAL_CASH,
    MES_OVERNIGHT_GAP_REVERSAL_SPEC,
    MESGapSignalBundle,
    MESGapTrade,
    MESMappingInterval,
    POINT_VALUE,
    TICK_SIZE,
    generate_mes_overnight_gap_reversal_bundle,
    mes_mapping_checksum,
    normalize_mes_mapping,
)

DATASET_ID = "futures_MES_5m_databento"
DATASET_MANIFEST_REFERENCE = "data/manifests/futures_MES_5m_databento.json"
EXPECTED_DATASET_SHA256 = (
    "fe6bfe4ea3328660e70c2291fc76ea8039249dfb2d5bb35a6390bd8fc7bf4dd1"
)
EXPECTED_DATASET_ROWS = 476_042
EXPECTED_FIRST_TIMESTAMP = "2019-05-05T22:00:00+00:00"
EXPECTED_LAST_TIMESTAMP = "2026-02-13T21:55:00+00:00"
DEVELOPMENT_START = pd.Timestamp("2019-05-06T00:00:00Z")
DEVELOPMENT_END = pd.Timestamp("2023-12-30T00:00:00Z")
EXPERIMENT_ID = "r11_mes_overnight_gap_reversal_development"
SESSIONS_PER_YEAR = 252
RISK_FREE_RATE = 0.0
SCREENING_CONFIG = ScreeningConfig(
    minimum_trades=750,
    minimum_total_return=0.0,
    minimum_annualized_return=0.0,
    minimum_sharpe_ratio=0.5,
    maximum_drawdown=0.35,
    minimum_win_rate=None,
)
EVIDENCE_LABEL = "fixed_owner_accepted_development_screen"
EVIDENCE_CLASSIFICATION = (
    "development/reference evidence only; not independent, OOS, protected, or edge proof"
)
PROMOTION_BLOCKERS = (
    "The full source-file extent was previously inspected; this bounded slice is development evidence.",
    "No chronological OOS, walk-forward, robustness, Monte Carlo, or protected evidence was evaluated.",
    "A surviving MES signal requires later validation on the intended underlying before any options claim.",
)


@dataclass(frozen=True)
class MESGapInputs:
    data: pd.DataFrame
    audit: DataAudit
    manifest: DatasetManifest
    dataset_path: Path
    mapping_intervals: tuple[MESMappingInterval, ...]
    mapping_checksum: str


@dataclass(frozen=True)
class MESGapScreenExecution:
    result: Any
    portfolio: Any
    bundle: MESGapSignalBundle
    daily_equity: pd.Series
    daily_returns: pd.Series


def execution_assumptions() -> dict[str, Any]:
    return {
        "kind": "r11_mes_overnight_gap_reversal",
        "engine": "vectorbtpro",
        "broker_orders": "disabled",
        "initial_cash": INITIAL_CASH,
        "position_size_contracts": 1,
        "point_value_usd": POINT_VALUE,
        "fee_per_contract_per_side_usd": FEE_PER_SIDE,
        "slippage_ticks_per_side": 1.0,
        "tick_size_index_points": TICK_SIZE,
        "signal": "prior NYSE session 15:55 Close to current session 09:30 Open",
        "direction": "positive gap short; negative gap long; exact zero flat",
        "entry": "current NYSE session 09:35 raw Open",
        "exit": "current NYSE session 10:00 raw Open",
        "annualization": {
            "sessions_per_year": SESSIONS_PER_YEAR,
            "risk_free_rate": RISK_FREE_RATE,
            "basis": "every scheduled NYSE development session, including flat/excluded sessions",
        },
        "maximum_drawdown_basis": "schedule-complete end-of-session equity",
        "limitations": (
            "Margin, financing, queue position, fill probability, and spread beyond "
            "one adverse tick per side are not modeled."
        ),
    }


def market_data_identity() -> dict[str, Any]:
    return {
        "dataset_id": DATASET_ID,
        "manifest_reference": DATASET_MANIFEST_REFERENCE,
        "dataset_sha256": EXPECTED_DATASET_SHA256,
        "symbol": "MES",
        "continuous_symbol": "MES.c.0",
        "provider": "Databento",
        "provider_dataset": "GLBX.MDP3",
        "interval": "5m",
        "adjusted": False,
        "timestamp_timezone": "UTC",
        "session_calendar": "NYSE",
        "session_timezone": "America/New_York",
        "predicate_start_inclusive": DEVELOPMENT_START.isoformat(),
        "predicate_end_exclusive": DEVELOPMENT_END.isoformat(),
        "symbology_request": {
            "dataset": "GLBX.MDP3",
            "symbol": "MES.c.0",
            "stype_in": "continuous",
            "stype_out": "instrument_id",
            "start_date": DEVELOPMENT_SESSION_START.isoformat(),
            "end_date": DEVELOPMENT_END.date().isoformat(),
        },
    }


def saved_configuration_document() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "strategy_id": MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
        "strategy_version": MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
        "market_data": market_data_identity(),
        "parameters": {"fixed_rule_count": 1, "parameters": {}},
        "execution": execution_assumptions(),
        "ranking": {"columns": ("total_return",), "ascending": (False,)},
        "screening": SCREENING_CONFIG.to_dict(),
    }


def assert_exact_mes_manifest(manifest: DatasetManifest) -> None:
    metadata = manifest.metadata
    expected = {
        "dataset_id": DATASET_ID,
        "status": "validated",
        "sha256": EXPECTED_DATASET_SHA256,
        "row_count": EXPECTED_DATASET_ROWS,
        "earliest_timestamp": EXPECTED_FIRST_TIMESTAMP,
        "latest_timestamp": EXPECTED_LAST_TIMESTAMP,
        "continuous_symbol": "MES.c.0",
        "roll_rule": "calendar/front-expiry rank zero",
        "price_adjustment": "none; original unadjusted contract prices",
    }
    mismatches = {
        key: (metadata.get(key), expected_value)
        for key, expected_value in expected.items()
        if metadata.get(key) != expected_value
    }
    if mismatches:
        raise RuntimeError(f"MES dataset identity does not match the accepted R11 screen: {mismatches}")


def _audit_from_slice(manifest: DatasetManifest, data: pd.DataFrame) -> DataAudit:
    metadata = manifest.metadata
    return DataAudit(
        cache_schema_version=1,
        symbol="MES",
        provider="Databento",
        provider_implementation="verified local catalog manifest with predicate-bounded Parquet read",
        interval="5m",
        requested_start=DEVELOPMENT_START.isoformat(),
        requested_dynamic_end_policy=f"exclusive fixed boundary {DEVELOPMENT_END.isoformat()}",
        latest_completed_exchange_session=DEVELOPMENT_SESSION_END.isoformat(),
        prices_adjusted=False,
        adjustment_verification=(
            "Databento MES.c.0 calendar/front-expiry rank zero; original unadjusted prices"
        ),
        download_time=str(metadata["imported_at_utc"]),
        download_timezone="UTC",
        actual_first_row_date=data.index[0].isoformat(),
        actual_last_row_date=data.index[-1].isoformat(),
        row_count=len(data),
        duplicate_timestamp_count=int(data.index.duplicated().sum()),
        missing_open_count=int(data["Open"].isna().sum()),
        missing_high_count=int(data["High"].isna().sum()),
        missing_low_count=int(data["Low"].isna().sum()),
        missing_close_count=int(data["Close"].isna().sum()),
        missing_volume_count=int(data["Volume"].isna().sum()),
        expected_session_gap_count=0,
        unexpected_session_gaps=[],
        provider_warnings=[
            "Full-file SHA-256 was verified, but only the fixed pre-2024 predicate slice was materialized.",
            "Roll-crossing sessions are excluded using the separately checksummed symbology mapping.",
        ],
        cache_path=str(manifest.canonical_relative_path),
        cache_action="verified and predicate-bounded reuse",
        cache_decision_reason=f"SHA-256 matched manifest {manifest.sha256}",
    )


def load_mes_gap_inputs(
    *,
    mapping_response: Mapping[str, Any],
    manifest_dir: Path | None = None,
    locations_path: Path | None = None,
) -> MESGapInputs:
    """Verify the owned file and materialize only the fixed development slice."""
    intervals = normalize_mes_mapping(mapping_response)
    mapping_digest = mes_mapping_checksum(intervals)
    manifest = load_dataset_manifest(
        DATASET_ID,
        **({"manifest_dir": manifest_dir} if manifest_dir is not None else {}),
    )
    assert_exact_mes_manifest(manifest)
    locations = load_data_locations(
        **({"path": locations_path} if locations_path is not None else {})
    )
    path = verify_dataset_file(manifest, locations, require_validated=True)
    value_columns = ["open", "high", "low", "close", "volume"]
    columns = [*value_columns, "ts_event"]
    frame = pd.read_parquet(
        path,
        engine="pyarrow",
        columns=columns,
        filters=[
            ("ts_event", ">=", DEVELOPMENT_START.to_pydatetime()),
            ("ts_event", "<", DEVELOPMENT_END.to_pydatetime()),
        ],
    )
    if tuple(frame.columns) != tuple(value_columns) or frame.index.name != "ts_event":
        raise RuntimeError(
            "MES predicate slice schema is invalid: "
            f"columns={tuple(frame.columns)}, index={frame.index.name!r}"
        )
    if frame.empty:
        raise RuntimeError("MES predicate slice is empty")
    frame = frame.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    frame.index = pd.DatetimeIndex(frame.index)
    if frame.index.tz is None:
        raise RuntimeError("MES predicate slice timestamps must be timezone-aware")
    frame.index = frame.index.tz_convert("UTC")
    frame.index.name = "Timestamp"
    if (
        frame.index[0] < DEVELOPMENT_START
        or frame.index[-1] >= DEVELOPMENT_END
        or not frame.index.is_monotonic_increasing
        or not frame.index.is_unique
    ):
        raise RuntimeError("MES predicate slice violates its fixed timestamp boundary")
    return MESGapInputs(
        data=frame,
        audit=_audit_from_slice(manifest, frame),
        manifest=manifest,
        dataset_path=path,
        mapping_intervals=intervals,
        mapping_checksum=mapping_digest,
    )


def exact_execution_prices(data: pd.DataFrame, bundle: MESGapSignalBundle) -> pd.Series:
    """Build the exact adverse raw-open fills in dollar-per-contract units."""
    price = data["Close"].astype(float).copy() * POINT_VALUE
    for trade in bundle.completed_trades:
        price.at[trade.entry_timestamp] = trade.entry_fill * POINT_VALUE
        price.at[trade.exit_timestamp] = trade.exit_fill * POINT_VALUE
    if not price.index.equals(data.index) or not price.map(math.isfinite).all() or (price <= 0).any():
        raise RuntimeError("MES execution prices must be positive finite values aligned to data")
    return price


def build_vectorbt_portfolio(
    data: pd.DataFrame,
    bundle: MESGapSignalBundle,
    *,
    vbt: Any | None = None,
) -> Any:
    """Use the existing licensed engine only at the candidate execution boundary."""
    engine = require_vectorbtpro() if vbt is None else vbt
    signals = bundle.signals
    return engine.Portfolio.from_signals(
        close=data["Close"].astype(float) * POINT_VALUE,
        entries=signals.entries,
        exits=signals.exits,
        short_entries=signals.short_entries,
        short_exits=signals.short_exits,
        price=exact_execution_prices(data, bundle),
        size=1.0,
        direction=None,
        accumulate=False,
        leverage=1.0,
        init_cash=INITIAL_CASH,
        fees=0.0,
        slippage=0.0,
        fixed_fees=FEE_PER_SIDE,
    )


def _finite_number(value: object, *, label: str) -> float:
    if not isinstance(value, Real) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise RuntimeError(f"VectorBT {label} must be finite")
    return float(value)


def validate_vectorbt_against_manual(portfolio: Any, bundle: MESGapSignalBundle) -> tuple[dict[str, Any], ...]:
    """Fail closed unless the licensed-engine ledger matches exact manual accounting."""
    trades = portfolio.trades.records_readable
    orders = portfolio.orders.records_readable
    if not isinstance(trades, pd.DataFrame) or not isinstance(orders, pd.DataFrame):
        raise RuntimeError("VectorBT must expose readable trade and order ledgers")
    expected = len(bundle.completed_trades)
    if len(trades) != expected or len(orders) != expected * 2:
        raise RuntimeError("VectorBT ledger counts disagree with manual MES sessions")
    required = {
        "Size",
        "Entry Index",
        "Exit Index",
        "Avg Entry Price",
        "Avg Exit Price",
        "Entry Fees",
        "Exit Fees",
        "PnL",
        "Status",
        "Direction",
    }
    if not required.issubset(trades.columns):
        raise RuntimeError("VectorBT trade ledger lacks required exact-accounting fields")
    order_required = {"Fill Index", "Size", "Price", "Fees", "Side"}
    if not order_required.issubset(orders.columns):
        raise RuntimeError("VectorBT order ledger lacks required exact-accounting fields")
    trade_records = trades.to_dict(orient="records")
    order_records = orders.to_dict(orient="records")
    for position, (observed, manual) in enumerate(zip(trade_records, bundle.completed_trades)):
        status = str(observed["Status"]).strip().lower()
        direction = str(observed["Direction"]).strip().lower()
        entry_order, exit_order = order_records[position * 2 : position * 2 + 2]
        expected_entry_side = "buy" if manual.direction == "long" else "sell"
        expected_exit_side = "sell" if manual.direction == "long" else "buy"
        checks = {
            "status": status == "closed",
            "direction": direction == manual.direction,
            "trade size": math.isclose(
                _finite_number(observed["Size"], label="trade size"), 1.0, abs_tol=1e-12
            ),
            "entry timestamp": pd.Timestamp(observed["Entry Index"]) == manual.entry_timestamp,
            "exit timestamp": pd.Timestamp(observed["Exit Index"]) == manual.exit_timestamp,
            "entry fill": math.isclose(
                _finite_number(observed["Avg Entry Price"], label="entry price") / POINT_VALUE,
                manual.entry_fill,
                abs_tol=1e-9,
            ),
            "exit fill": math.isclose(
                _finite_number(observed["Avg Exit Price"], label="exit price") / POINT_VALUE,
                manual.exit_fill,
                abs_tol=1e-9,
            ),
            "entry fees": math.isclose(
                _finite_number(observed["Entry Fees"], label="entry fees"),
                FEE_PER_SIDE,
                abs_tol=1e-9,
            ),
            "exit fees": math.isclose(
                _finite_number(observed["Exit Fees"], label="exit fees"),
                FEE_PER_SIDE,
                abs_tol=1e-9,
            ),
            "net P&L": math.isclose(
                _finite_number(observed["PnL"], label="PnL"),
                manual.net_pnl,
                abs_tol=1e-8,
            ),
            "entry order timestamp": pd.Timestamp(entry_order["Fill Index"]) == manual.entry_timestamp,
            "exit order timestamp": pd.Timestamp(exit_order["Fill Index"]) == manual.exit_timestamp,
            "entry order size": math.isclose(
                _finite_number(entry_order["Size"], label="entry order size"),
                1.0,
                abs_tol=1e-12,
            ),
            "exit order size": math.isclose(
                _finite_number(exit_order["Size"], label="exit order size"),
                1.0,
                abs_tol=1e-12,
            ),
            "entry order side": str(entry_order["Side"]).strip().lower()
            == expected_entry_side,
            "exit order side": str(exit_order["Side"]).strip().lower()
            == expected_exit_side,
            "entry order fill": math.isclose(
                _finite_number(entry_order["Price"], label="entry order price") / POINT_VALUE,
                manual.entry_fill,
                abs_tol=1e-9,
            ),
            "exit order fill": math.isclose(
                _finite_number(exit_order["Price"], label="exit order price") / POINT_VALUE,
                manual.exit_fill,
                abs_tol=1e-9,
            ),
            "entry order fee": math.isclose(
                _finite_number(entry_order["Fees"], label="entry order fee"),
                FEE_PER_SIDE,
                abs_tol=1e-9,
            ),
            "exit order fee": math.isclose(
                _finite_number(exit_order["Fees"], label="exit order fee"),
                FEE_PER_SIDE,
                abs_tol=1e-9,
            ),
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise RuntimeError(
                f"VectorBT/manual MES trade mismatch for {manual.session_date}: {failed}"
            )
    value_accessor = getattr(portfolio, "value", None)
    portfolio_value = value_accessor() if callable(value_accessor) else value_accessor
    if isinstance(portfolio_value, pd.DataFrame):
        if portfolio_value.shape[1] != 1:
            raise RuntimeError("VectorBT value must contain exactly one portfolio column")
        portfolio_value = portfolio_value.iloc[:, 0]
    if not isinstance(portfolio_value, pd.Series) or portfolio_value.empty:
        raise RuntimeError("VectorBT must expose a nonempty portfolio value series")
    expected_final_equity = INITIAL_CASH + sum(
        trade.net_pnl for trade in bundle.completed_trades
    )
    observed_final_equity = _finite_number(
        portfolio_value.iloc[-1], label="final portfolio value"
    )
    if not math.isclose(observed_final_equity, expected_final_equity, abs_tol=1e-8):
        raise RuntimeError("VectorBT/manual MES final equity mismatch")
    return (
        {
            "gate_id": "mes_gap.vectorbt_manual_trade_match",
            "status": "passed",
            "completed_trade_count": expected,
        },
        {
            "gate_id": "mes_gap.vectorbt_order_count",
            "status": "passed",
            "filled_order_count": len(orders),
        },
        {
            "gate_id": "mes_gap.vectorbt_manual_final_equity_match",
            "status": "passed",
            "final_equity": observed_final_equity,
        },
    )


def verify_mes_vectorbt_runtime(vbt: Any) -> tuple[dict[str, Any], ...]:
    """Exercise the exact installed-engine adapter on synthetic long/short fills."""
    index = pd.DatetimeIndex(
        [
            "2023-12-21T14:35:00Z",
            "2023-12-21T15:00:00Z",
            "2023-12-22T14:35:00Z",
            "2023-12-22T15:00:00Z",
        ]
    )
    data = pd.DataFrame(
        {
            "Open": [101.0, 100.0, 99.0, 100.0],
            "High": [101.5, 100.5, 99.5, 100.5],
            "Low": [100.5, 99.5, 98.5, 99.5],
            "Close": [101.0, 100.0, 99.0, 100.0],
            "Volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )
    short = MESGapTrade(
        session_date="2023-12-21",
        prior_session_date="2023-12-20",
        mapping_instrument_id="1",
        gap=0.01,
        direction="short",
        direction_value=-1,
        entry_timestamp=index[0],
        exit_timestamp=index[1],
        entry_raw=101.0,
        exit_raw=100.0,
        entry_fill=100.75,
        exit_fill=100.25,
        fee_per_side=FEE_PER_SIDE,
        net_pnl=1.26,
    )
    long = MESGapTrade(
        session_date="2023-12-22",
        prior_session_date="2023-12-21",
        mapping_instrument_id="1",
        gap=-0.01,
        direction="long",
        direction_value=1,
        entry_timestamp=index[2],
        exit_timestamp=index[3],
        entry_raw=99.0,
        exit_raw=100.0,
        entry_fill=99.25,
        exit_fill=99.75,
        fee_per_side=FEE_PER_SIDE,
        net_pnl=1.26,
    )
    signals = SignalResult(
        entries=pd.Series([False, False, True, False], index=index),
        exits=pd.Series([False, False, False, True], index=index),
        short_entries=pd.Series([True, False, False, False], index=index),
        short_exits=pd.Series([False, True, False, False], index=index),
        parameters={},
        metadata={"synthetic_runtime_probe": True},
    )
    bundle = MESGapSignalBundle(
        signals=signals,
        scheduled_sessions=("2023-12-21", "2023-12-22"),
        completed_trades=(short, long),
        excluded_sessions=(),
        daily_net_pnl=pd.Series(
            [short.net_pnl, long.net_pnl],
            index=pd.DatetimeIndex(["2023-12-21", "2023-12-22"]),
        ),
    )
    portfolio = build_vectorbt_portfolio(data, bundle, vbt=vbt)
    return validate_vectorbt_against_manual(portfolio, bundle)


def schedule_complete_metrics(
    bundle: MESGapSignalBundle,
) -> tuple[pd.Series, pd.Series, dict[str, float | int]]:
    """Compute only the predeclared daily metrics from exact realized net P&L."""
    pnl = bundle.daily_net_pnl.astype(float)
    if len(pnl) < 2:
        raise RuntimeError("at least two scheduled sessions are required")
    equity = INITIAL_CASH + pnl.cumsum()
    if not equity.map(math.isfinite).all() or (equity <= 0).any():
        raise RuntimeError("schedule-complete equity must remain positive and finite")
    previous = pd.Series(
        [INITIAL_CASH, *equity.iloc[:-1].tolist()], index=equity.index, dtype=float
    )
    daily_returns = equity / previous - 1.0
    volatility = float(daily_returns.std(ddof=1))
    if not math.isfinite(volatility) or volatility == 0.0:
        raise RuntimeError("daily-return sample standard deviation must be positive and finite")
    completed = len(bundle.completed_trades)
    if completed == 0:
        raise RuntimeError("win rate is undefined with zero completed trades")
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / INITIAL_CASH - 1.0
    annualized_return = (final_equity / INITIAL_CASH) ** (
        SESSIONS_PER_YEAR / len(equity)
    ) - 1.0
    sharpe = math.sqrt(SESSIONS_PER_YEAR) * float(daily_returns.mean()) / volatility
    equity_with_baseline = pd.concat(
        [pd.Series([INITIAL_CASH], dtype=float), equity.reset_index(drop=True)],
        ignore_index=True,
    )
    max_drawdown = float(
        (equity_with_baseline / equity_with_baseline.cummax() - 1.0).min()
    )
    win_rate = sum(item.net_pnl > 0 for item in bundle.completed_trades) / completed
    metrics: dict[str, float | int] = {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "number_of_trades": completed,
        "win_rate": win_rate,
    }
    if any(
        not isinstance(value, Real)
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        for value in metrics.values()
    ):
        raise RuntimeError("MES schedule-complete metrics must all be finite")
    equity.name = "equity"
    daily_returns.name = "daily_return"
    return equity, daily_returns, metrics


def execute_mes_overnight_gap_reversal(
    data: pd.DataFrame,
    audit: DataAudit,
    mapping_intervals: Sequence[MESMappingInterval],
    *,
    vbt: Any | None = None,
    schedule: pd.DataFrame | None = None,
) -> MESGapScreenExecution:
    """Execute, cross-check, and screen exactly one fixed parameterless row."""
    bundle = generate_mes_overnight_gap_reversal_bundle(
        data,
        mapping_intervals=mapping_intervals,
        schedule=schedule,
    )
    portfolio = build_vectorbt_portfolio(data, bundle, vbt=vbt)
    engine_validation = validate_vectorbt_against_manual(portfolio, bundle)
    daily_equity, daily_returns, metrics = schedule_complete_metrics(bundle)
    assumptions = execution_assumptions()
    screening = screen_metrics(
        experiment_id=EXPERIMENT_ID,
        strategy_id=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
        strategy_version=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
        parameters={},
        execution_assumptions=assumptions,
        metrics=metrics,
        config=SCREENING_CONFIG,
    )
    row = metrics | {
        "parameter_row_id": screening.parameter_row_id,
        "screening_status": "passed" if screening.passed else "screened_out",
        "screening_passed_rule_count": screening.passed_rule_count,
        "screening_failed_rule_count": screening.failed_rule_count,
        "screening_rejection_reasons": " | ".join(screening.rejection_reasons),
    }
    ranked = pd.DataFrame([row])
    result = SimpleNamespace(
        ranked_results=ranked,
        passing_results=ranked.copy() if screening.passed else ranked.iloc[0:0].copy(),
        screened_out_results=ranked.iloc[0:0].copy() if screening.passed else ranked.copy(),
        experiment_id=EXPERIMENT_ID,
        strategy_id=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
        strategy_name=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.name,
        strategy_version=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
        normalized_parameters=({},),
        market_data_audit=audit,
        execution_assumptions=assumptions,
        evaluated_combinations=1,
        rejected_combinations=0,
        rejections=(),
        validation_results=engine_validation,
        screening_config=SCREENING_CONFIG,
        screening_results=(screening,),
        parameter_plan_summary=None,
    )
    return MESGapScreenExecution(
        result=result,
        portfolio=portfolio,
        bundle=bundle,
        daily_equity=daily_equity,
        daily_returns=daily_returns,
    )
