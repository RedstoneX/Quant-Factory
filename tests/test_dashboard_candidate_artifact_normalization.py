"""Regression proof for preserved candidate artifacts in Results and Compare."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.compare_adapter import CompareDashboardAdapter
from dashboard.components.trade_explorer import normalize_trade_rows
from dashboard.run_detail_adapter import (
    RunDetailDashboardAdapter,
    _candidate_trade_rows,
    _validated_equity_curve,
)
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document


def _persist_candidate_run(
    database: Path,
    artifact_root: Path,
    *,
    run_id: str,
    equity_values: tuple[float, ...],
) -> None:
    service = PersistenceService(database)
    try:
        if service.strategies.get("mes_overnight_gap_reversal", "1.0.0") is None:
            service.register_strategy(
                strategy_id="mes_overnight_gap_reversal",
                strategy_version="1.0.0",
                display_name="MES Overnight Gap Reversal",
                description="Preserved accepted candidate evidence",
                lifecycle=StrategyLifecycle.REJECTED,
                active=False,
            )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id=f"candidate_{run_id}",
                strategy_id="mes_overnight_gap_reversal",
                strategy_version="1.0.0",
                market_data={
                    "provider": "Databento",
                    "symbol": "MES.c.0",
                    "interval": "5m",
                },
                parameters={},
                execution={
                    "entry_time": "09:35 America/New_York",
                    "exit_time": "10:00 America/New_York",
                    "fee_per_side": 0.62,
                    "slippage_ticks_per_side": 1,
                },
                ranking={"metric": "total_return"},
                screening={"minimum_trades": 500},
            )
        )
        service.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id="mes_overnight_gap_reversal",
            strategy_version="1.0.0",
            stage=RunStage.SCREENING,
            run_id=run_id,
            status=RunStatus.SUCCEEDED,
        )
        with transaction(service.connection):
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id=run_id,
                    provider="Databento",
                    provider_implementation="owned-mes-parquet",
                    symbol="MES.c.0",
                    interval="5m",
                    timezone="UTC",
                    requested_coverage="2019-05-06/2023-12-29",
                    actual_coverage="2019-05-06/2023-12-29",
                    adjusted=False,
                    row_count=1173,
                    cache_action="owned_data",
                    validation_summary_json=canonical_json({"status": "valid"}),
                    manifest_reference="data/manifests/futures_MES_5m_databento.json",
                    checksum="candidate-dataset-checksum",
                )
            )
            service.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id=run_id,
                    assumptions_json=canonical_json(
                        {
                            "entry_time": "09:35 America/New_York",
                            "exit_time": "10:00 America/New_York",
                            "fee_per_side": 0.62,
                            "slippage_ticks_per_side": 1,
                        }
                    ),
                )
            )
            service.results.add_parameter_result(
                run_id=run_id,
                row_id=f"{run_id}-fixed",
                normalized_parameters={},
                metrics={
                    "total_return": -0.0416386,
                    "annualized_return": -0.0090953,
                    "sharpe_ratio": -1.03455,
                    "max_drawdown": -0.0473226,
                    "number_of_trades": 1114,
                    "win_rate": 0.472172,
                },
                ranking_position=1,
                screening_status="screened_out",
                rejection_reasons="total_return | annualized_return | sharpe_ratio",
            )

        documents = {
            "metrics": (
                ArtifactType.METRICS,
                {
                    "metrics": {
                        "total_return": -0.0416386,
                        "annualized_return": -0.0090953,
                        "sharpe_ratio": -1.03455,
                        "max_drawdown": -0.0473226,
                        "number_of_trades": 1114,
                        "win_rate": 0.472172,
                    }
                },
            ),
            "trades_and_orders": (
                ArtifactType.TRADES_OR_ORDERS,
                {
                    "instrument": "MES",
                    "contract_count": 1,
                    "price_unit": "index_points",
                    "pnl_unit": "USD",
                    "manual_trades": [
                        {
                            "session_date": "2023-12-21",
                            "prior_session_date": "2023-12-20",
                            "mapping_instrument_id": "MESZ3",
                            "gap": 2.0,
                            "direction": "short",
                            "direction_value": -1,
                            "entry_timestamp": "2023-12-21T14:35:00+00:00",
                            "exit_timestamp": "2023-12-21T15:00:00+00:00",
                            "entry_raw": 503.5,
                            "exit_raw": 501.5,
                            "entry_fill": 503.25,
                            "exit_fill": 501.75,
                            "fee_per_side": 0.62,
                            "net_pnl": 6.26,
                        }
                    ],
                    "vectorbt_trades": [
                        {
                            "Size": 1.0,
                            "Entry Index": "2023-12-21T14:35:00+00:00",
                            "Exit Index": "2023-12-21T15:00:00+00:00",
                            "Avg Entry Price": 503.25,
                            "Avg Exit Price": 501.75,
                            "Entry Fees": 0.62,
                            "Exit Fees": 0.62,
                            "PnL": 6.26,
                            "Direction": "Short",
                            "Status": "Closed",
                        }
                    ],
                    "vectorbt_orders": [
                        {
                            "Fill Index": "2023-12-21T14:35:00+00:00",
                            "Size": 1.0,
                            "Price": 503.25,
                            "Fees": 0.62,
                            "Side": "Sell",
                        },
                        {
                            "Fill Index": "2023-12-21T15:00:00+00:00",
                            "Size": 1.0,
                            "Price": 501.75,
                            "Fees": 0.62,
                            "Side": "Buy",
                        },
                    ],
                },
            ),
            "equity_curve": (
                ArtifactType.EQUITY_CURVE,
                {
                    "equity_curve": [
                        {
                            "timestamp": f"2023-12-{20 + index}T00:00:00+00:00",
                            "equity": value,
                        }
                        for index, value in enumerate(equity_values)
                    ],
                    "daily_returns": [],
                    "basis": "every scheduled NYSE development session",
                },
            ),
        }
        for logical_name, (artifact_type, document) in documents.items():
            content = (canonical_json(document) + "\n").encode("utf-8")
            location = f"artifacts/{run_id}/{logical_name}.json"
            target = artifact_root / location
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            service.register_artifact(
                run_id=run_id,
                artifact_type=artifact_type,
                logical_name=logical_name,
                media_type="application/json",
                format="json",
                location=location,
                content=content,
            )
        service.persist_run_manifest(service.build_run_manifest(run_id))
    finally:
        service.close()


def test_results_normalizes_preserved_candidate_artifact_shapes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "candidate.sqlite3"
    artifact_root = tmp_path / "evidence"
    _persist_candidate_run(
        database,
        artifact_root,
        run_id="candidate-a",
        equity_values=(100_000.0, 100_100.0, 99_900.0),
    )

    detail = RunDetailDashboardAdapter(
        database,
        artifact_root=artifact_root,
    ).selected_run_detail("candidate-a")

    assert detail.warnings == ()
    assert len(detail.evidence.trades) == 1
    assert detail.evidence.trades[0]["entry_timestamp"] == (
        "2023-12-21T14:35:00+00:00"
    )
    assert detail.evidence.trades[0]["Entry Index"] == (
        "2023-12-21T14:35:00+00:00"
    )
    assert detail.evidence.trades[0]["PnL"] == pytest.approx(6.26)
    normalized_trade = normalize_trade_rows(
        detail.evidence.trades,
        run_id="candidate-a",
        price_unit=detail.evidence.price_unit or "currency",
        pnl_unit=detail.evidence.pnl_unit or "not_recorded",
    )[0]
    assert normalized_trade["Status"] == "Closed"
    assert normalized_trade["Direction"] == "Short"
    assert normalized_trade["Outcome"] == "Win"
    assert normalized_trade["Entry price"] == pytest.approx(503.25)
    assert normalized_trade["P&L"] == pytest.approx(6.26)
    assert len(detail.evidence.orders) == 2
    assert [row["Side"] for row in detail.evidence.orders] == ["Sell", "Buy"]
    assert [row["value"] for row in detail.evidence.equity_curve] == [
        100_000.0,
        100_100.0,
        99_900.0,
    ]
    assert [row["drawdown"] for row in detail.evidence.drawdown_curve] == pytest.approx(
        [0.0, 0.0, 99_900.0 / 100_100.0 - 1.0]
    )
    assert detail.evidence.price_series == ()


def test_compare_uses_normalized_candidate_equity_and_drawdown(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "candidate-compare.sqlite3"
    artifact_root = tmp_path / "evidence"
    _persist_candidate_run(
        database,
        artifact_root,
        run_id="candidate-a",
        equity_values=(100_000.0, 101_000.0, 100_500.0),
    )
    _persist_candidate_run(
        database,
        artifact_root,
        run_id="candidate-b",
        equity_values=(200_000.0, 198_000.0, 202_000.0),
    )

    model = CompareDashboardAdapter(
        database,
        artifact_root=artifact_root,
    ).compare(("candidate-a", "candidate-b"))

    assert [point.value for point in model.equity_series[0].points] == pytest.approx(
        [100.0, 101.0, 100.5]
    )
    assert [point.value for point in model.equity_series[1].points] == pytest.approx(
        [100.0, 99.0, 101.0]
    )
    assert [point.value for point in model.drawdown_series[0].points] == pytest.approx(
        [0.0, 0.0, 100_500.0 / 101_000.0 - 1.0]
    )
    assert [point.value for point in model.drawdown_series[1].points] == pytest.approx(
        [0.0, -0.01, 0.0]
    )
    assert not any(finding.code == "equity_unavailable" for finding in model.findings)


def test_vectorbt_trade_rows_remain_the_fallback_when_manual_rows_are_absent() -> None:
    vectorbt_rows = ({"PnL": 2.5, "Status": "Closed"},)

    assert _candidate_trade_rows({"vectorbt_trades": list(vectorbt_rows)}) == vectorbt_rows


def test_conflicting_equity_aliases_fail_closed() -> None:
    warnings: list[str] = []

    rows = _validated_equity_curve(
        {
            "equity_curve": [
                {
                    "timestamp": "2023-12-20T00:00:00+00:00",
                    "value": 100_000.0,
                    "equity": 99_000.0,
                }
            ]
        },
        warnings=warnings,
    )

    assert rows == ()
    assert warnings == [
        "Artifact equity_curve field equity_curve row 0 has conflicting value and equity."
    ]
