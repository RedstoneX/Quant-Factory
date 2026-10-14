"""Rebuild one tested setting's portfolio on demand and prove it matches the saved run.

Composition only; every step is an existing function:
CandidatePipelineDefinition.from_configuration_document -> load_market_data ->
strategy.validate_parameters -> strategy.generate_signals -> build_portfolio ->
extract_metrics.  Nothing is recomputed by hand and nothing is persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
import json
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.experiments import build_portfolio
from backtesting.experiments.metrics import extract_metrics
from market_data import load_market_data
from orchestration.candidate_pipeline_runtime import CandidatePipelineDefinition
from persistence import PersistenceService
from persistence.service import RUNTIME_LINEAGE_ENVIRONMENT_KEY
from strategies import get_strategy


EXACT_METRICS = ("total_return", "number_of_trades")
NOT_PROVABLE = "cannot be proven exact: the run's market data has no checksum"


class SettingRebuildRefused(ValueError):
    """The rebuilt setting would not be the one the saved run tested."""


@dataclass(frozen=True)
class SavedSetting:
    run_id: str
    row_id: str
    definition: CandidatePipelineDefinition
    parameters: dict[str, Any]
    stored_metrics: dict[str, Any]
    provenance_checksum: str | None
    provenance_row_count: int
    run_vectorbtpro_version: str | None


@dataclass(frozen=True)
class SettingRebuild:
    run_id: str
    row_id: str
    exact: bool
    reason: str
    portfolio: Any | None = None
    data: pd.DataFrame | None = None
    warnings: tuple[str, ...] = ()


def load_saved_setting(database: str | Path, run_id: str, row_id: str) -> SavedSetting:
    persistence = PersistenceService(database)
    try:
        run = persistence.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")
        configuration = persistence.configurations.get(run.configuration_id)
        provenance = persistence.results.get_data_provenance(run_id)
        row = next(
            (item for item in persistence.results.list_parameter_results(run_id) if item.row_id == row_id),
            None,
        )
    finally:
        persistence.close()
    if configuration is None or provenance is None or row is None:
        raise KeyError(f"run {run_id} has no saved configuration, data provenance or setting {row_id}")
    lineage = json.loads(run.environment_json).get(RUNTIME_LINEAGE_ENVIRONMENT_KEY, {})
    return SavedSetting(
        run_id=run_id,
        row_id=row_id,
        definition=CandidatePipelineDefinition.from_configuration_document(
            json.loads(configuration.canonical_config_json)
        ),
        parameters=json.loads(row.normalized_parameters_json),
        stored_metrics=json.loads(row.metrics_json),
        provenance_checksum=provenance.checksum,
        provenance_row_count=provenance.row_count,
        run_vectorbtpro_version=lineage.get("vectorbtpro", {}).get("version"),
    )


def prove_same_data(audit: Any, saved: SavedSetting) -> None:
    """Refuse unless the loaded data is byte-for-byte the dataset the run used."""
    if audit.checksum != saved.provenance_checksum or audit.row_count != saved.provenance_row_count:
        raise SettingRebuildRefused(
            f"market data differs from the run: checksum {audit.checksum} rows {audit.row_count}, "
            f"saved checksum {saved.provenance_checksum} rows {saved.provenance_row_count}"
        )


def rebuild_portfolio(saved: SavedSetting, data: pd.DataFrame) -> SettingRebuild:
    """Re-run the saved setting on ``data``; refuse unless the stored metrics come back exactly."""
    experiment = saved.definition.experiment
    strategy = get_strategy(experiment.strategy_id)
    signals = strategy.generate_signals(data, strategy.validate_parameters(saved.parameters))
    portfolio = build_portfolio(data, signals, experiment)
    metrics = (
        extract_metrics(portfolio, data=data, config=experiment)
        if experiment.metric_policy is not None
        else extract_metrics(portfolio)
    )
    mismatched = {
        name: (metrics[name], saved.stored_metrics.get(name))
        for name in EXACT_METRICS
        if metrics[name] != saved.stored_metrics.get(name)
    }
    if mismatched:
        raise SettingRebuildRefused(f"rebuilt setting differs from the saved run (rebuilt, saved): {mismatched}")
    installed = metadata.version("vectorbtpro")
    warnings = (
        ()
        if installed == saved.run_vectorbtpro_version
        else (f"VectorBT PRO {installed} is installed; the run used {saved.run_vectorbtpro_version}",)
    )
    return SettingRebuild(saved.run_id, saved.row_id, True, "Rebuilt exactly", portfolio, data, warnings)


@lru_cache(maxsize=32)
def rebuild_setting(database: str, run_id: str, row_id: str) -> SettingRebuild:
    """Cached rebuild of one saved setting, proven exact or refused."""
    saved = load_saved_setting(database, run_id, row_id)
    if saved.provenance_checksum is None:
        return SettingRebuild(run_id, row_id, False, NOT_PROVABLE)
    data_as_of = saved.definition.validation.data_as_of
    market = load_market_data(
        saved.definition.experiment.market_data,
        now=pd.Timestamp(data_as_of) if data_as_of is not None else None,
        allow_download=False,
    )
    prove_same_data(market.audit, saved)
    return rebuild_portfolio(saved, market.data)
