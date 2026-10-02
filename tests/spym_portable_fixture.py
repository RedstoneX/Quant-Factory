"""Portable persisted SPYM evidence for dashboard and persistence tests.

This fixture intentionally replaces only the licensed calculation boundary.  It
persists the same public evidence contract consumed by the dashboard so browser
tests continue to exercise real durable claims, manifests, artifact validation,
and UI rendering without claiming to prove VectorBT Pro calculations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from dashboard.health import DatasetHealth
from market_data.catalog import DataLocations, load_dataset_manifest
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    ReviewState,
    RunStatus,
    canonical_json,
)
from persistence.database import transaction
from prefect_spike.fixture_flow import (
    PrefectFixtureResult,
    PrefectRunReference,
    _validated_claim_boundary,
    deterministic_fixture_body,
    is_spym_21c_fixture_request,
    reconcile_quant_factory_run_status,
)


_DATASET_ID = "equities_SPYM_1m_databento_equs_mini"
_DATASET_CHECKSUM = (
    "0fac9de8cb97568c7ee5ae00532277d960c316989ccd65296c394f0dfa44a5ab"
)
_MANIFEST_REFERENCE = "data/manifests/equities_SPYM_1m_databento_equs_mini.json"
_ROW_COUNT = 53_528
_TRADE_COUNT = 366
_METRICS = {
    "annualized_return": 0.008051216589356924,
    "max_drawdown": -0.00032545736508460266,
    "number_of_trades": _TRADE_COUNT,
    "sharpe_ratio": 5.269897369953472,
    "total_return": 0.0008170000000000059,
    "win_rate": 0.6693989071038251,
}


def portable_spym_catalog_snapshot() -> tuple[
    DataLocations,
    tuple[DatasetHealth, ...],
    None,
]:
    """Provide a typed test double for readiness without reading market data."""

    fixture_root = Path("/portable-test-market-data")
    locations = DataLocations(
        root=fixture_root,
        manifests=fixture_root / "manifests",
        quarantine=fixture_root / "quarantine",
        backup_archive=None,
        extracted_root=None,
        verify_sha256_before_use=True,
    )
    health = DatasetHealth(
        load_dataset_manifest(_DATASET_ID),
        "Available locally",
        "Verified",
        "Injected portable browser-test readiness; no market-data file was read.",
    )
    return locations, (health,), None


def portable_spym_fixture_launcher(**kwargs: Any) -> PrefectFixtureResult:
    """Launch generic fixtures normally and seed SPYM's persisted UI contract."""

    kwargs.pop("attempt_marker_path", None)
    if not is_spym_21c_fixture_request(
        saved_parameters=kwargs.get("saved_parameters"),
        saved_execution_assumptions=kwargs.get("saved_execution_assumptions"),
    ):
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
            prefect_api_url="http://127.0.0.1:4200/api",
        )
    return _persist_portable_spym_fixture(**kwargs)


def _persist_portable_spym_fixture(
    *,
    database_path: str | Path,
    idempotency_key: str,
    configuration_id: str,
    quant_factory_run_id: str,
    canonical_request_json: str,
    request_fingerprint: str,
    operation_kind: str,
    source_run_id: str | None,
    source_lineage: Mapping[str, str],
    saved_parameters: object | None,
    saved_execution_assumptions: object | None,
    fail_after_run_start: bool = False,
    frozen_runtime_lineage: dict[str, Any] | None = None,
    reproduction_metadata: dict[str, Any] | None = None,
) -> PrefectFixtureResult:
    del frozen_runtime_lineage, reproduction_metadata
    flow_run_id = f"prefect-{quant_factory_run_id}"
    api_url = "http://127.0.0.1:4200/api"
    _validated_claim_boundary(
        database_path=database_path,
        idempotency_key=idempotency_key,
        configuration_id=configuration_id,
        quant_factory_run_id=quant_factory_run_id,
        canonical_request_json=canonical_request_json,
        request_fingerprint=request_fingerprint,
        operation_kind=operation_kind,
        source_run_id=source_run_id,
        source_lineage=source_lineage,
        prefect_reference=PrefectRunReference(
            flow_run_id=flow_run_id,
            api_url=api_url,
        ),
    )
    service = PersistenceService(database_path)
    try:
        run = service.increment_run_attempt(quant_factory_run_id)
        if fail_after_run_start:
            raise RuntimeError("controlled Prefect fixture failure")
        if not isinstance(saved_parameters, Mapping):
            raise RuntimeError("portable SPYM fixture parameters are missing")
        parameters = saved_parameters.get("strategy_parameters")
        if not isinstance(parameters, Mapping) or not parameters:
            raise RuntimeError("portable SPYM fixture parameters are invalid")
        if not isinstance(saved_execution_assumptions, Mapping):
            raise RuntimeError("portable SPYM execution assumptions are missing")

        manifest = _dataset_manifest()
        bars = _price_rows(manifest)
        trades, orders = _trade_and_order_rows(bars)
        artifacts = _artifact_documents(
            run_id=quant_factory_run_id,
            configuration_id=configuration_id,
            parameters=dict(parameters),
            execution=dict(saved_execution_assumptions),
            manifest=manifest,
            bars=bars,
            trades=trades,
            orders=orders,
        )
        with transaction(service.connection):
            service.require_active_run_for_completion(quant_factory_run_id)
            service.results.add_parameter_result(
                run_id=quant_factory_run_id,
                row_id=f"portable-spym:{quant_factory_run_id}",
                normalized_parameters=dict(parameters),
                metrics=_METRICS,
                ranking_position=1,
                screening_status="passed",
                rejection_reasons="",
            )
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id=quant_factory_run_id,
                    provider="Databento",
                    provider_implementation="EQUS.MINI ohlcv-1m",
                    symbol="SPYM",
                    interval="1m",
                    timezone="UTC",
                    requested_coverage="2025-10-31..2026-07-13",
                    actual_coverage=(
                        f"{bars[0]['timestamp']}..{bars[-1]['timestamp']}"
                    ),
                    adjusted=False,
                    row_count=_ROW_COUNT,
                    cache_action="portable-contract-fixture",
                    validation_summary_json=canonical_json(
                        _validation_summary(manifest)
                    ),
                    manifest_reference=_MANIFEST_REFERENCE,
                    checksum=_DATASET_CHECKSUM,
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

        root = _artifact_root(database_path)
        for artifact_type, logical_name, document in artifacts:
            location = f"state/artifacts/{quant_factory_run_id}/{logical_name}.json"
            content = (canonical_json(document) + "\n").encode("utf-8")
            path = root / location
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            service.register_artifact(
                run_id=quant_factory_run_id,
                artifact_type=artifact_type,
                logical_name=logical_name,
                media_type="application/json",
                format="json",
                location=location,
                content=content,
                schema_version=1,
            )
        service.persist_run_manifest(service.build_run_manifest(quant_factory_run_id))
        reconcile_quant_factory_run_status(
            service,
            quant_factory_run_id=quant_factory_run_id,
            prefect_state="Completed",
        )
        return PrefectFixtureResult(
            quant_factory_run_id=quant_factory_run_id,
            prefect_flow_run_id=flow_run_id,
            configuration_id=configuration_id,
            deterministic_value=_TRADE_COUNT,
            attempt_count=run.attempt_count,
            prefect_api_url=api_url,
        )
    except Exception:
        if service.runs.get(quant_factory_run_id) is not None:
            reconcile_quant_factory_run_status(
                service,
                quant_factory_run_id=quant_factory_run_id,
                prefect_state="Failed",
                error_summary=(
                    "Prefect fixture execution failed; inspect approved technical "
                    "diagnostics."
                ),
            )
        raise
    finally:
        service.close()


def _artifact_root(database_path: str | Path) -> Path:
    database = Path(database_path).resolve()
    return database.parent.parent if database.parent.name == "state" else database.parent


def _dataset_manifest() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "manifests"
        / f"{_DATASET_ID}.json"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        document.get("dataset_id") != _DATASET_ID
        or document.get("sha256") != _DATASET_CHECKSUM
        or document.get("row_count") != _ROW_COUNT
    ):
        raise RuntimeError("public SPYM manifest no longer matches the portable contract")
    return document


def _price_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    sessions = manifest.get("requested_sessions")
    if not isinstance(sessions, list) or len(sessions) != 173:
        raise RuntimeError("public SPYM manifest session inventory is invalid")
    counts = [310] * 74 + [309] * 98 + [306]
    rows: list[dict[str, Any]] = []
    for session_index, (session, count) in enumerate(zip(sessions, counts, strict=True)):
        start = datetime.fromisoformat(f"{session}T13:30:00+00:00")
        if session_index < 24:
            occupied_five_minute_buckets = list(range(75))
        elif session_index < 106:
            occupied_five_minute_buckets = [
                bucket for bucket in range(78) if bucket != 76
            ]
        else:
            occupied_five_minute_buckets = list(range(78))
        minutes = [bucket * 5 for bucket in occupied_five_minute_buckets]
        for offset in range(1, 5):
            minutes.extend(
                bucket * 5 + offset for bucket in occupied_five_minute_buckets
            )
        minutes = sorted(minutes[:count])
        for minute in minutes:
            timestamp = start + timedelta(minutes=minute)
            price = 80.0 + session_index * 0.01 + minute * 0.0005
            close = price + (0.005 if minute % 2 == 0 else -0.005)
            rows.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "open": round(price, 4),
                    "high": round(max(price, close) + 0.01, 4),
                    "low": round(min(price, close) - 0.01, 4),
                    "close": round(close, 4),
                }
            )
    if len(rows) != _ROW_COUNT:
        raise RuntimeError("portable SPYM row generator produced the wrong count")
    return rows


def _trade_and_order_rows(
    bars: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    session_starts: list[int] = []
    previous_date = None
    for index, row in enumerate(bars):
        current_date = row["timestamp"][:10]
        if current_date != previous_date:
            session_starts.append(index)
            previous_date = current_date

    placements: list[tuple[int, int]] = []
    for trade_index in range(_TRADE_COUNT - 3):
        session_index = trade_index % (len(session_starts) - 1)
        cycle = trade_index // (len(session_starts) - 1)
        placements.append((session_index, 10 + cycle * 20))
    placements.extend(
        (len(session_starts) - 1, offset) for offset in (30, 100, 200)
    )

    trades: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    for trade_id, (session_index, offset) in enumerate(placements):
        entry = bars[session_starts[session_index] + offset]
        exit_row = bars[session_starts[session_index] + offset + 5]
        entry_price = float(entry["open"])
        pnl = 0.05 if trade_id % 3 else -0.03
        exit_price = entry_price + pnl
        trades.append(
            {
                "Avg Entry Price": entry_price,
                "Avg Exit Price": exit_price,
                "Column": 0,
                "Direction": "Long",
                "Entry Fees": 0.0,
                "Entry Index": entry["timestamp"],
                "Entry Order Id": trade_id * 2,
                "Exit Fees": 0.0,
                "Exit Index": exit_row["timestamp"],
                "Exit Order Id": trade_id * 2 + 1,
                "Exit Trade Id": trade_id,
                "PnL": pnl,
                "Position Id": trade_id,
                "Return": pnl / entry_price,
                "Size": 1.0,
                "Status": "Closed",
            }
        )
        for order_id, side, row, price in (
            (trade_id * 2, "Buy", entry, entry_price),
            (trade_id * 2 + 1, "Sell", exit_row, exit_price),
        ):
            orders.append(
                {
                    "Column": 0,
                    "Creation Index": row["timestamp"],
                    "Fees": 0.0,
                    "Fill Index": row["timestamp"],
                    "Order Id": order_id,
                    "Price": price,
                    "Side": side,
                    "Signal Index": row["timestamp"],
                    "Size": 1.0,
                    "Stop Type": None,
                    "Type": "Market",
                }
            )
    return trades, orders


def _validation_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dataset": "EQUS.MINI",
        "dataset_id": _DATASET_ID,
        "duplicate_timestamp_count": 0,
        "missing_regular_session_bar_count": manifest.get(
            "missing_regular_session_bar_count", 0
        ),
        "missing_session_count": 0,
        "negative_volume_count": 0,
        "null_count": 0,
        "observed_regular_session_bar_count": _ROW_COUNT,
        "ohlc_violation_count": 0,
        "out_of_session_bar_count": 0,
        "possible_regular_session_minute_count": manifest.get(
            "possible_regular_session_minute_count", _ROW_COUNT
        ),
        "schema": "ohlcv-1m",
        "synthetic_bar_count": 0,
        "validation_notes": [
            "Deterministic public test evidence; not licensed-engine proof."
        ],
    }


def _artifact_documents(
    *,
    run_id: str,
    configuration_id: str,
    parameters: Mapping[str, Any],
    execution: Mapping[str, Any],
    manifest: Mapping[str, Any],
    bars: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> tuple[tuple[ArtifactType, str, dict[str, Any]], ...]:
    equity_curve = [
        {"timestamp": row["timestamp"], "value": 10_000.0 + index * 0.0001526}
        for index, row in enumerate(bars)
    ]
    first_close = float(bars[0]["close"])
    benchmark_curve = [
        {
            "timestamp": row["timestamp"],
            "value": 10_000.0 * float(row["close"]) / first_close,
        }
        for row in bars
    ]
    benchmark = {
        "benchmark_final_value": benchmark_curve[-1]["value"],
        "benchmark_position_sizing": "fully invested buy-and-hold",
        "engine": "persisted deterministic contract fixture",
        "fees": 0.0,
        "fixed_fee_per_order": 0.0,
        "instrument": "SPYM",
        "label": "SPYM same-instrument buy-and-hold",
        "limitations": (
            "Research fixture comparison only; broker orders are disabled, and "
            "zero configured fees/slippage do not model future actual fills."
        ),
        "price_series": "deterministic public SPYM-shaped one-minute test evidence",
        "resampling": "none; 53,528 persisted one-minute contract rows",
        "slippage": 0.0,
        "starting_capital": 10_000.0,
        "strategy_final_value": equity_curve[-1]["value"],
        "strategy_minus_benchmark": (
            equity_curve[-1]["value"] - benchmark_curve[-1]["value"]
        ),
        "strategy_position_sizing": "fixed 1 unit long-only orders",
        "strategy_timing": "Completed-bar signal with next persisted bar execution.",
        "timing": "Buy-and-hold comparison begins at the first persisted close.",
    }
    validation = _validation_summary(manifest)
    ranked_row = {
        **parameters,
        **_METRICS,
        "parameter_row_id": f"portable-spym:{run_id}",
        "screening_status": "passed",
        "screening_rejection_reasons": "",
        "validation_gate_count": 20,
    }
    return (
        (
            ArtifactType.RUN_SUMMARY,
            "run_summary",
            {
                "run_id": run_id,
                "configuration_id": configuration_id,
                "experiment_id": "milestone_21c_spym_databento_vectorbt_fixture",
                "strategy_id": "spym_rsi_mean_reversion_fixture",
                "strategy_version": "1.0.0",
                "dataset_id": _DATASET_ID,
                "dataset_sha256": _DATASET_CHECKSUM,
                "terminal_status": RunStatus.SUCCEEDED.value,
                "evaluated_combinations": 1,
                "broker_orders": "disabled",
                "fixture_only": True,
            },
        ),
        (ArtifactType.METRICS, "metrics", {"metrics": _METRICS}),
        (
            ArtifactType.PARAMETER_RESULTS,
            "parameter_results",
            {"ranked_results": [ranked_row]},
        ),
        (
            ArtifactType.TRADES_OR_ORDERS,
            "trades_and_orders",
            {"trades": trades, "orders": orders},
        ),
        (
            ArtifactType.EQUITY_CURVE,
            "equity_curve",
            {
                "equity_curve": equity_curve,
                "price_series": bars,
                "benchmark_curve": benchmark_curve,
                "benchmark": benchmark,
            },
        ),
        (
            ArtifactType.VALIDATION_EVIDENCE,
            "validation_evidence",
            {
                "dataset_manifest": {
                    "reference": _MANIFEST_REFERENCE,
                    "sha256": _DATASET_CHECKSUM,
                    "row_count": _ROW_COUNT,
                    "status": "validated",
                },
                "result_validation_gate_count": 20,
                "screening_status": "passed",
                "data_validation": validation,
                "evidence_classification": (
                    "deterministic public UI/persistence fixture; not engine evidence"
                ),
                "promotion_eligible": False,
                "execution_contract": dict(execution),
            },
        ),
        (ArtifactType.DATASET_MANIFEST, "dataset_manifest", dict(manifest)),
    )
