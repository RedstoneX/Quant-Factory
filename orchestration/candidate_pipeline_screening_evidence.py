"""Bounded capture and durable persistence of screening evidence for one candidate run.

The screening engine hands each parameter configuration's portfolio to an observer
while it is alive. This module keeps one detached snapshot per configuration and
later writes the shared price history and every configuration's evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.experiments import ExperimentConfig
from orchestration.candidate_screening_artifacts import (
    persist_screening_artifacts,
    persist_screening_price_series,
    snapshot_screening_portfolio,
)
from backtesting.out_of_sample import OutOfSampleConfig, execute_out_of_sample
from persistence import ArtifactType, PersistenceService


def capture_screening_portfolios(captured: dict[str, Any]) -> Callable[[str, Any], Any]:
    """Return a portfolio observer that keeps one detached snapshot per parameter row."""

    def observe(row_id: str, portfolio: Any) -> Any:
        return captured.setdefault(row_id, snapshot_screening_portfolio(portfolio))

    return observe


def persist_captured_screening_evidence(
    *,
    persistence: PersistenceService,
    artifact_root: Path,
    run_id: str,
    result: Any,
    config: ExperimentConfig,
    data: pd.DataFrame,
    captured_portfolios: Mapping[str, Any],
) -> None:
    """Write the shared price history and each configuration's captured evidence."""
    if not captured_portfolios:
        return
    combination_count = len(config.parameter_combinations)
    if len(captured_portfolios) != combination_count:
        raise RuntimeError("bounded screening evidence capture is incomplete")
    persist_screening_price_series(
        persistence=persistence,
        artifact_root=artifact_root,
        run_id=run_id,
        data=data,
    )
    for row_id, portfolio in captured_portfolios.items():
        persist_screening_artifacts(
            persistence=persistence, artifact_root=artifact_root,
            run_id=run_id, result=result,
            portfolio=portfolio, data=data,
            config=config, parameter_row_id=row_id,
            namespace=(f"screening_configuration/{row_id}" if combination_count > 1 else None),
            include_price_series=False,
            price_window_only=False,
        )


def execute_oos_saving_trades(config: OutOfSampleConfig, data: pd.DataFrame, audit: Any,
                              persistence: PersistenceService, artifact_root: Path, run_id: str) -> Any:
    """Run the out-of-sample stage and save the locked test portfolio's trades with the run."""
    captured: dict[str, Any] = {}
    result = execute_out_of_sample(config, data, audit, write_output=True,
                                   test_portfolio_observer=capture_screening_portfolios(captured))
    for row_id, portfolio in captured.items():
        persist_screening_artifacts(
            persistence=persistence, artifact_root=artifact_root, run_id=run_id, result=result.test_result,
            portfolio=portfolio, data=data, config=config.experiment, parameter_row_id=row_id,
            include_price_series=False, only=(ArtifactType.TRADES_OR_ORDERS,),
        )
    return result
