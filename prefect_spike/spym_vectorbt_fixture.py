"""Milestone 21C SPYM Databento VectorBT Pro execution fixture."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd
import vectorbtpro as vbt

from backtesting.experiments import (
    ExecutionConfig,
    ExperimentConfig,
    build_portfolio,
    execute_experiment,
)
from backtesting.screening.models import ScreeningConfig
from market_data import DataAudit, MarketDataConfig
from market_data.catalog import (
    DatasetManifest,
    load_data_locations,
    load_dataset_manifest,
    verify_dataset_file,
)
from market_data.equity_contract import (
    SPYM_EQUITY_DATA_CONTRACT,
    validate_spym_manifest,
)
from persistence import (
    ArtifactAvailability,
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    ReviewState,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document
from strategies import get_strategy
from strategies.spym_rsi_mean_reversion_fixture import (
    SPYM_RSI_ENTRY_THRESHOLD,
    SPYM_RSI_EXIT_THRESHOLD,
    SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC,
    SPYM_RSI_WINDOW,
)

SPYM_21C_FIXTURE_KIND = "spym_databento_rsi_vectorbt_21c"
SPYM_21C_EXPERIMENT_ID = "milestone_21c_spym_databento_vectorbt_fixture"
SPYM_21C_ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SPYMFixtureExecution:
    config: ExperimentConfig
    data: pd.DataFrame
    audit: DataAudit
    manifest: DatasetManifest
    dataset_path: Path
    artifact_root: Path


def is_spym_21c_fixture_request(
    *,
    saved_parameters: object | None,
    saved_execution_assumptions: object | None,
) -> bool:
    return (
        isinstance(saved_parameters, Mapping)
        and saved_parameters.get("fixture") == SPYM_21C_FIXTURE_KIND
        and isinstance(saved_execution_assumptions, Mapping)
        and saved_execution_assumptions.get("kind") == SPYM_21C_FIXTURE_KIND
    )


def spym_21c_execution_assumptions() -> dict[str, Any]:
    return {
        "kind": SPYM_21C_FIXTURE_KIND,
        "engine": "vectorbtpro",
        "broker_orders": "disabled",
        "signal_timing": "completed_bar_close",
        "execution_mode": "next_bar_open",
        "execution_timing": "next_observed_databento_bar_open",
        "execution_price": "Open",
        "initial_cash": 10_000.0,
        "fees": 0.0,
        "slippage": 0.0,
        "position_sizing": "fixed_units",
        "order_size": 1.0,
        "whole_share_sizing": True,
        "direction": "longonly",
        "leverage": 1.0,
        "accumulate": False,
        "price_multiplier": 1.0,
        "fixed_fee_per_contract_per_side": 0.0,
        "fixed_fee_per_order": 0.0,
        "slippage_points": 0.0,
        "slippage_ticks": 0.0,
        "tick_size": None,
        "strategy_fixture_only": True,
        "profitability_research": False,
    }


def spym_21c_parameters() -> dict[str, Any]:
    return {
        "fixture": SPYM_21C_FIXTURE_KIND,
        "strategy_parameters": {
            "window": SPYM_RSI_WINDOW,
            "entry_threshold": SPYM_RSI_ENTRY_THRESHOLD,
            "exit_threshold": SPYM_RSI_EXIT_THRESHOLD,
        },
    }


def spym_21c_market_data_identity() -> dict[str, Any]:
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
        "coverage_start": contract.coverage_start,
        "coverage_end_policy": contract.coverage_end_policy,
    }


def spym_21c_saved_configuration_document() -> dict[str, Any]:
    return normalized_configuration_document(
        experiment_id=SPYM_21C_EXPERIMENT_ID,
        strategy_id=SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC.identity.strategy_id,
        strategy_version=SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC.identity.version,
        market_data=spym_21c_market_data_identity(),
        parameters=spym_21c_parameters(),
        execution=spym_21c_execution_assumptions(),
        ranking={"columns": ("total_return",), "ascending": (False,)},
        screening={
            "minimum_trades": 0,
            "minimum_total_return": -1.0,
            "minimum_annualized_return": -1.0,
            "minimum_sharpe_ratio": -999.0,
            "maximum_drawdown": 1.0,
            "minimum_win_rate": None,
        },
    )


def ensure_spym_21c_saved_configuration(
    service: PersistenceService,
) -> str:
    spec = SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC
    service.register_strategy(
        strategy_id=spec.identity.strategy_id,
        strategy_version=spec.identity.version,
        display_name=spec.identity.name,
        description=spec.identity.description,
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        active=True,
    )
    configuration = service.upsert_configuration(
        spym_21c_saved_configuration_document()
    )
    return configuration.configuration_id


def load_spym_21c_fixture_inputs(
    *,
    database_path: str | Path,
    saved_execution_assumptions: Mapping[str, Any],
) -> SPYMFixtureExecution:
    manifest = load_dataset_manifest(SPYM_EQUITY_DATA_CONTRACT.dataset_id)
    validate_spym_manifest(manifest.metadata)
    locations = load_data_locations()
    dataset_path = verify_dataset_file(manifest, locations, require_validated=True)
    data = _load_spym_frame(dataset_path, manifest)
    audit = _audit_from_manifest(manifest)
    config = _experiment_config(
        dataset_path=dataset_path,
        output_path=_artifact_root(database_path) / "scratch" / "spym_21c_results.csv",
    )
    _assert_execution_document_matches_config(saved_execution_assumptions, config)
    return SPYMFixtureExecution(
        config=config,
        data=data,
        audit=audit,
        manifest=manifest,
        dataset_path=dataset_path,
        artifact_root=_artifact_root(database_path),
    )


def execute_spym_21c_fixture_on_active_run(
    service: PersistenceService,
    *,
    quant_factory_run_id: str,
    configuration_id: str,
    saved_execution_assumptions: Mapping[str, Any],
    database_path: str | Path,
    cancellation_check: Callable[[], None] | None = None,
) -> int:
    fixture = load_spym_21c_fixture_inputs(
        database_path=database_path,
        saved_execution_assumptions=saved_execution_assumptions,
    )
    result = execute_experiment(
        fixture.config,
        fixture.data,
        fixture.audit,
        write_output=False,
    )
    if cancellation_check is not None:
        cancellation_check()
    if result.evaluated_combinations != 1 or result.ranked_results.empty:
        raise RuntimeError("SPYM fixture did not produce exactly one result row")

    parameters = result.normalized_parameters[0]
    strategy = get_strategy(fixture.config.strategy_id)
    signals = strategy.generate_signals(fixture.data, parameters)
    portfolio = build_portfolio(fixture.data, signals, fixture.config)
    artifacts = _artifact_documents(
        run_id=quant_factory_run_id,
        configuration_id=configuration_id,
        fixture=fixture,
        result=result,
        portfolio=portfolio,
    )

    if cancellation_check is not None:
        cancellation_check()
    with transaction(service.connection):
        service.require_active_run_for_completion(quant_factory_run_id)
        service._persist_rows(quant_factory_run_id, result)
        service.results.set_data_provenance(
            _provenance_record(
                run_id=quant_factory_run_id,
                fixture=fixture,
            )
        )
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=quant_factory_run_id,
                assumptions_json=canonical_json(saved_execution_assumptions),
            )
        )
        service.reviews.update(
            target_type="run",
            target_id=quant_factory_run_id,
            state=ReviewState.INFRASTRUCTURE_FIXTURE,
            note="Milestone 21C deterministic SPYM VectorBT Pro fixture run.",
            operator="local-user",
        )

    for artifact in artifacts:
        path = fixture.artifact_root / artifact["location"]
        path.parent.mkdir(parents=True, exist_ok=True)
        content = _artifact_bytes(artifact["document"])
        path.write_bytes(content)
        service.register_artifact(
            run_id=quant_factory_run_id,
            artifact_type=artifact["artifact_type"],
            logical_name=artifact["logical_name"],
            media_type="application/json",
            format="json",
            location=artifact["location"],
            content=content,
            schema_version=SPYM_21C_ARTIFACT_SCHEMA_VERSION,
            availability_state=ArtifactAvailability.AVAILABLE,
        )
    manifest = service.build_run_manifest(quant_factory_run_id)
    service.persist_run_manifest(manifest)

    return int(result.ranked_results.iloc[0]["number_of_trades"])


def _artifact_root(database_path: str | Path) -> Path:
    database = Path(database_path).resolve()
    if database.parent.name == "state":
        return database.parent.parent
    return database.parent


def _load_spym_frame(path: Path, manifest: DatasetManifest) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    expected_columns = ("timestamp", "open", "high", "low", "close", "volume")
    if tuple(frame.columns) != expected_columns:
        raise RuntimeError(f"SPYM parquet columns do not match manifest contract: {tuple(frame.columns)}")
    if len(frame) != manifest.row_count:
        raise RuntimeError(
            f"SPYM parquet row count mismatch: expected {manifest.row_count}, got {len(frame)}"
        )
    renamed = frame.rename(
        columns={
            "timestamp": "Timestamp",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    ).set_index("Timestamp")
    if str(renamed.index.tz) != "UTC":
        raise RuntimeError("SPYM parquet timestamps must be UTC")
    if renamed.index.duplicated().any() or not renamed.index.is_monotonic_increasing:
        raise RuntimeError("SPYM parquet timestamps are not unique and ordered")
    if renamed[["Open", "High", "Low", "Close", "Volume"]].isna().any().any():
        raise RuntimeError("SPYM parquet contains null OHLCV values")
    return renamed


def _audit_from_manifest(manifest: DatasetManifest) -> DataAudit:
    metadata = manifest.metadata
    null_counts = metadata.get("null_counts", {})
    return DataAudit(
        cache_schema_version=2,
        symbol=metadata["symbol"],
        provider="Databento",
        provider_implementation=f"{metadata['dataset']} {metadata['schema']}",
        interval=metadata["timeframe"],
        requested_start=metadata["coverage_start"],
        requested_dynamic_end_policy=metadata["coverage_end_policy"],
        latest_completed_exchange_session=metadata["latest_completed_session"],
        prices_adjusted=False,
        adjustment_verification="Databento manifest adjustment=raw",
        download_time=metadata["imported_at_utc"],
        download_timezone=metadata["timezone"],
        actual_first_row_date=str(pd.Timestamp(metadata["earliest_timestamp"]).date()),
        actual_last_row_date=str(pd.Timestamp(metadata["latest_timestamp"]).date()),
        row_count=manifest.row_count,
        duplicate_timestamp_count=int(metadata["duplicate_timestamp_count"]),
        missing_open_count=int(null_counts.get("open", 0)),
        missing_high_count=int(null_counts.get("high", 0)),
        missing_low_count=int(null_counts.get("low", 0)),
        missing_close_count=int(null_counts.get("close", 0)),
        missing_volume_count=int(null_counts.get("volume", 0)),
        expected_session_gap_count=int(metadata["missing_session_count"]),
        unexpected_session_gaps=list(metadata.get("missing_sessions", ())),
        provider_warnings=[
            "Databento EQUS.MINI one-minute bars are sparse: no synthetic bars "
            "are generated for minutes without trades."
        ],
        cache_path=str(manifest.canonical_relative_path),
        cache_action="verified",
        cache_decision_reason="validated manifest and SHA-256 matched before use",
    )


def _experiment_config(*, dataset_path: Path, output_path: Path) -> ExperimentConfig:
    assumptions = spym_21c_execution_assumptions()
    parameters = spym_21c_parameters()["strategy_parameters"]
    return ExperimentConfig(
        experiment_id=SPYM_21C_EXPERIMENT_ID,
        strategy_id=SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC.identity.strategy_id,
        parameter_combinations=(parameters,),
        market_data=MarketDataConfig(
            symbol="SPYM",
            provider="Databento",
            provider_implementation="EQUS.MINI ohlcv-1m",
            interval="1m",
            requested_start="2025-10-31",
            end_date_policy="latest_fully_completed_nyse_session",
            adjusted=False,
            exchange_calendar="NYSE",
            market_timezone="UTC",
            cache_path=dataset_path,
        ),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=float(assumptions["initial_cash"]),
            fees=float(assumptions["fees"]),
            slippage=float(assumptions["slippage"]),
            direction="longonly",
            leverage=float(assumptions["leverage"]),
            accumulate=False,
            position_sizing="fixed_units",
            order_size=float(assumptions["order_size"]),
        ),
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        output_path=output_path,
        screening=ScreeningConfig(
            minimum_trades=0,
            minimum_total_return=-1.0,
            minimum_annualized_return=-1.0,
            minimum_sharpe_ratio=-999.0,
            maximum_drawdown=1.0,
            minimum_win_rate=None,
        ),
    )


def _assert_execution_document_matches_config(
    document: Mapping[str, Any], config: ExperimentConfig
) -> None:
    expected = spym_21c_execution_assumptions()
    if canonical_json(document) != canonical_json(expected):
        raise RuntimeError("saved execution assumptions do not match the SPYM 21C contract")
    if config.execution.position_sizing != "fixed_units" or config.execution.order_size != 1.0:
        raise RuntimeError("SPYM fixture requires fixed whole-share sizing")


def _provenance_record(
    *,
    run_id: str,
    fixture: SPYMFixtureExecution,
) -> DataProvenanceRecord:
    metadata = fixture.manifest.metadata
    validation_summary = {
        "dataset_id": fixture.manifest.dataset_id,
        "dataset": metadata["dataset"],
        "schema": metadata["schema"],
        "observed_regular_session_bar_count": metadata["observed_regular_session_bar_count"],
        "possible_regular_session_minute_count": metadata["possible_regular_session_minute_count"],
        "missing_regular_session_bar_count": metadata["missing_regular_session_bar_count"],
        "missing_session_count": metadata["missing_session_count"],
        "duplicate_timestamp_count": metadata["duplicate_timestamp_count"],
        "out_of_session_bar_count": metadata["out_of_session_bar_count"],
        "null_count": metadata["null_count"],
        "ohlc_violation_count": metadata["ohlc_violation_count"],
        "negative_volume_count": metadata["negative_volume_count"],
        "synthetic_bar_count": metadata["synthetic_bar_count"],
        "validation_notes": metadata.get("validation_notes", ()),
    }
    return DataProvenanceRecord(
        run_id=run_id,
        provider="Databento",
        provider_implementation=f"{metadata['dataset']} {metadata['schema']}",
        symbol=metadata["symbol"],
        interval=metadata["timeframe"],
        timezone=metadata["timezone"],
        requested_coverage=(
            f"{metadata['coverage_start']}..{metadata['latest_completed_session']}"
        ),
        actual_coverage=(
            f"{metadata['earliest_timestamp']}..{metadata['latest_timestamp']}"
        ),
        adjusted=False,
        row_count=fixture.manifest.row_count,
        cache_action="verified",
        validation_summary_json=canonical_json(validation_summary),
        manifest_reference=SPYM_EQUITY_DATA_CONTRACT.manifest_reference,
        checksum=fixture.manifest.sha256,
    )


def _artifact_documents(
    *,
    run_id: str,
    configuration_id: str,
    fixture: SPYMFixtureExecution,
    result,
    portfolio,
) -> list[dict[str, Any]]:
    row = result.ranked_results.iloc[0].to_dict()
    orders = _records(portfolio.orders.records_readable)
    trades = _records(portfolio.trades.records_readable)
    equity = _series_records(portfolio.value, "value")
    benchmark = _benchmark_document(fixture, portfolio)
    base = f"state/artifacts/{run_id}"
    summary = {
        "run_id": run_id,
        "configuration_id": configuration_id,
        "experiment_id": result.experiment_id,
        "strategy_id": result.strategy_id,
        "strategy_version": result.strategy_version,
        "dataset_id": fixture.manifest.dataset_id,
        "dataset_sha256": fixture.manifest.sha256,
        "terminal_status": RunStatus.SUCCEEDED.value,
        "evaluated_combinations": result.evaluated_combinations,
        "broker_orders": "disabled",
        "fixture_only": True,
    }
    validation = {
        "dataset_manifest": {
            "reference": SPYM_EQUITY_DATA_CONTRACT.manifest_reference,
            "sha256": fixture.manifest.sha256,
            "row_count": fixture.manifest.row_count,
            "status": fixture.manifest.status,
        },
        "result_validation_gate_count": int(row["validation_gate_count"]),
        "screening_status": row["screening_status"],
        "data_validation": json.loads(
            _provenance_record(run_id=run_id, fixture=fixture).validation_summary_json
        ),
    }
    return [
        _artifact(
            ArtifactType.RUN_SUMMARY,
            "run_summary",
            f"{base}/run_summary.json",
            summary,
        ),
        _artifact(
            ArtifactType.METRICS,
            "metrics",
            f"{base}/metrics.json",
            {"metrics": _metric_subset(row)},
        ),
        _artifact(
            ArtifactType.PARAMETER_RESULTS,
            "parameter_results",
            f"{base}/parameter_results.json",
            {"ranked_results": [_json_record(row)]},
        ),
        _artifact(
            ArtifactType.TRADES_OR_ORDERS,
            "trades_and_orders",
            f"{base}/trades_and_orders.json",
            {"trades": trades, "orders": orders},
        ),
        _artifact(
            ArtifactType.EQUITY_CURVE,
            "equity_curve",
            f"{base}/equity_curve.json",
            {
                "equity_curve": equity,
                "price_series": _price_series_records(fixture.data),
                "benchmark_curve": benchmark["benchmark_curve"],
                "benchmark": benchmark["benchmark"],
            },
        ),
        _artifact(
            ArtifactType.VALIDATION_EVIDENCE,
            "validation_evidence",
            f"{base}/validation_evidence.json",
            validation,
        ),
        _artifact(
            ArtifactType.DATASET_MANIFEST,
            "dataset_manifest",
            f"{base}/dataset_manifest.json",
            fixture.manifest.metadata,
        ),
    ]


def _benchmark_document(
    fixture: SPYMFixtureExecution,
    portfolio,
) -> dict[str, Any]:
    execution = fixture.config.execution
    close = fixture.data["Close"].astype(float) * execution.price_multiplier
    benchmark_portfolio = vbt.Portfolio.from_holding(
        close,
        init_cash=execution.initial_cash,
        fees=execution.fees,
        slippage=execution.slippage,
        fixed_fees=execution.fixed_fee_per_order,
        direction=execution.direction,
    )
    strategy_final = _last_numeric(portfolio.value)
    benchmark_final = _last_numeric(benchmark_portfolio.value)
    return {
        "benchmark_curve": _series_records(benchmark_portfolio.value, "value"),
        "benchmark": {
            "instrument": fixture.manifest.metadata["symbol"],
            "label": (
                f"{fixture.manifest.metadata['symbol']} same-instrument buy-and-hold"
            ),
            "starting_capital": execution.initial_cash,
            "engine": "vectorbtpro.Portfolio.from_holding",
            "timing": (
                "Invests available starting cash at the first observed one-minute "
                "close and values the open long position through the final observed bar."
            ),
            "strategy_timing": (
                "Strategy signals use completed bars and execute on the next observed "
                "Databento bar open."
            ),
            "strategy_position_sizing": (
                f"fixed {execution.order_size:g} unit long-only orders"
            ),
            "benchmark_position_sizing": "fully invested buy-and-hold",
            "fees": execution.fees,
            "slippage": execution.slippage,
            "fixed_fee_per_order": execution.fixed_fee_per_order,
            "resampling": "none; full observed Databento EQUS.MINI one-minute bars",
            "price_series": "raw SPYM Databento EQUS.MINI ohlcv-1m close values",
            "limitations": (
                "Research fixture comparison only; sparse one-minute bars are not "
                "forward-filled, broker orders are disabled, and zero configured "
                "fees/slippage do not model future actual fills."
            ),
            "strategy_final_value": strategy_final,
            "benchmark_final_value": benchmark_final,
            "strategy_minus_benchmark": (
                None
                if strategy_final is None or benchmark_final is None
                else strategy_final - benchmark_final
            ),
        },
    }


def _artifact(
    artifact_type: ArtifactType,
    logical_name: str,
    location: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "logical_name": logical_name,
        "location": location,
        "document": document,
    }


def _artifact_bytes(document: dict[str, Any]) -> bytes:
    return (canonical_json(document) + "\n").encode("utf-8")


def _metric_subset(row: Mapping[str, Any]) -> dict[str, Any]:
    names = (
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "number_of_trades",
        "win_rate",
    )
    return {name: _json_value(row[name]) for name in names}


def _json_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_value(value) for key, value in row.items()}


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_json_record(record) for record in frame.to_dict(orient="records")]


def _series_records(series: Any, name: str) -> list[dict[str, Any]]:
    if isinstance(series, pd.DataFrame):
        if series.shape[1] != 1:
            raise RuntimeError("expected one-column portfolio series")
        series = series.iloc[:, 0]
    return [
        {"timestamp": _json_value(index), name: _json_value(value)}
        for index, value in series.items()
    ]


def _price_series_records(data: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": _json_value(index),
            "open": _json_value(row.Open),
            "high": _json_value(row.High),
            "low": _json_value(row.Low),
            "close": _json_value(row.Close),
        }
        for index, row in data[["Open", "High", "Low", "Close"]].iterrows()
    ]


def _last_numeric(series: Any) -> float | None:
    if isinstance(series, pd.DataFrame):
        if series.shape[1] != 1:
            return None
        series = series.iloc[:, 0]
    if len(series) == 0:
        return None
    value = series.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and pd.isna(value):
        return None
    return value
