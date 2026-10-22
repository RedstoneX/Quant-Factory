"""One-Candidate admission policy and immutable StudyPlan execution mapping."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from backtesting.experiments import ExecutionConfig, ExperimentConfig
from backtesting.monte_carlo import MonteCarloConfig
from backtesting.out_of_sample import ChronologicalSplitConfig
from backtesting.robustness import NeighborhoodConfig, ParameterNeighborhoodDefinition, RegimeConfig
from backtesting.screening import ScreeningConfig
from backtesting.validation import WalkForwardWindowRules
from dashboard.run_adapter import IdeaDraftView, list_idea_drafts
from market_data import MarketDataConfig, load_market_data
from orchestration.candidate_pipeline_definition import CandidateValidationPlan
from orchestration.candidate_pipeline_runtime import CandidatePipelineDefinition
from persistence import PersistenceService, StrategyLifecycle, canonical_json
from research_intake import parse_candidate_packet, validate_candidate_packet
from strategies.mes_five_bar_run_exhaustion import (
    CANDIDATE_ID,
    CANDIDATE_VERSION,
    MES_FIVE_BAR_RUN_EXHAUSTION_SPEC,
    STRATEGY_ID,
    STRATEGY_VERSION,
)

DATASET_ID = "futures_MES_5m_databento"
DATASET_END = "2023-12-29T21:55:00Z"
EXPERIMENT_ID = "r13_five_bar_run_exhaustion_v1"
PARAMETER_COMBINATIONS = tuple(
    {"run_length": run_length, "minimum_ticks_per_bar": ticks}
    for run_length in (4, 5, 6)
    for ticks in (1, 2)
)


def candidate_fingerprint(draft: IdeaDraftView) -> str:
    validation = validate_candidate_packet(
        parse_candidate_packet(draft.candidate_json, format_hint="json")
    )
    if not validation.valid:
        raise ValueError("Candidate packet is invalid")
    return hashlib.sha256(validation.canonical_json.encode("utf-8")).hexdigest()


def admit_candidate(draft: IdeaDraftView) -> CandidatePipelineDefinition:
    """Admit only the exact retained Candidate version named by the policy."""
    return admit_candidate_identity(draft.draft_id, candidate_fingerprint(draft))


def admit_candidate_identity(
    candidate_id: str, candidate_version: str
) -> CandidatePipelineDefinition:
    """Resolve one already-validated Candidate identity through the allowlist."""
    if candidate_id != CANDIDATE_ID or candidate_version != CANDIDATE_VERSION:
        raise ValueError("Candidate is outside the one-Candidate executable policy")
    return study_plan_definition()


def study_plan_definition() -> CandidatePipelineDefinition:
    experiment = ExperimentConfig(
        experiment_id=EXPERIMENT_ID,
        strategy_id=STRATEGY_ID,
        parameter_combinations=PARAMETER_COMBINATIONS,
        market_data=MarketDataConfig(
            symbol="MES",
            provider="Databento",
            provider_implementation=f"verified_local_catalog:{DATASET_ID}",
            interval="5m",
            requested_start="2019-05-06",
            end_date_policy="fixed retained Candidate end 2023-12-29",
            adjusted=False,
            exchange_calendar="NYSE",
            market_timezone="America/New_York",
            cache_path=Path("futures/MES/5m/MES_5m_databento.parquet"),
        ),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=100_000.0,
            fees=0.0,
            slippage=0.0,
            direction="both",
            leverage=1.0,
            accumulate=False,
            position_sizing="fixed_units",
            order_size=1.0,
            price_multiplier=5.0,
            fixed_fee_per_contract_per_side=0.62,
            slippage_ticks=1.0,
            tick_size=0.25,
        ),
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        output_path=Path("unused-five-bar-run-output.csv"),
        screening=ScreeningConfig.provisional_defaults(),
    )
    validation = CandidateValidationPlan(
        out_of_sample_split=ChronologicalSplitConfig(
            train_fraction=0.60, selection_fraction=0.20, test_fraction=0.20,
            minimum_rows_per_partition=10_000,
        ),
        out_of_sample_shortlist_size=1,
        walk_forward_rules=WalkForwardWindowRules(
            training_window_size=80_000,
            selection_window_size=20_000,
            test_window_size=20_000,
            step_size=20_000,
            training_mode="rolling",
            minimum_rows_per_window=10_000,
            incomplete_final_window="drop",
        ),
        walk_forward_shortlist_size=1,
        robustness_neighborhood=NeighborhoodConfig(
            definitions=(
                ParameterNeighborhoodDefinition(
                    "run_length", "explicit_values", explicit_values=(4, 5, 6)
                ),
                ParameterNeighborhoodDefinition(
                    "minimum_ticks_per_bar", "explicit_values", explicit_values=(1, 2)
                ),
            ),
            minimum_valid_neighbors=3,
        ),
        robustness_regimes=RegimeConfig(
            trend_window=50,
            volatility_window=20,
            annualization_factor=252.0 * 78.0,
            minimum_observations=20,
        ),
        robustness_maximum_drawdown=0.35,
        robustness_minimum_return=0.0,
        robustness_minimum_sharpe=0.5,
        monte_carlo=MonteCarloConfig(
            method="moving_block_bootstrap",
            simulation_count=1_000,
            minimum_observations=10,
            block_length=5,
        ),
        data_as_of=DATASET_END,
    )
    return CandidatePipelineDefinition(
        experiment=experiment,
        strategy_version=STRATEGY_VERSION,
        validation=validation,
    )


def persist_admitted_study_plan(*, database: str | Path) -> str:
    """Persist and link the one admitted StudyPlan without rewriting its packet."""
    drafts = {draft.draft_id: draft for draft in list_idea_drafts(database)}
    draft = drafts.get(CANDIDATE_ID)
    if draft is None:
        raise ValueError("The retained Candidate is missing")
    definition = admit_candidate(draft)
    document = json.loads(canonical_json(definition.configuration_document()))
    CandidatePipelineDefinition.from_configuration_document(document)
    load_market_data(
        definition.experiment.market_data,
        now=pd.Timestamp(DATASET_END),
        allow_download=False,
    )
    service = PersistenceService(database)
    try:
        spec = MES_FIVE_BAR_RUN_EXHAUSTION_SPEC
        service.register_strategy(
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            display_name=spec.identity.name,
            description=spec.identity.description,
            lifecycle=StrategyLifecycle.CANDIDATE,
            active=True,
        )
        current = service.idea_drafts.get(CANDIDATE_ID)
        if current is None:
            raise ValueError("The retained Candidate disappeared during admission")
        if current.candidate_json != draft.candidate_json:
            raise ValueError("The retained Candidate changed during admission")
        if current.configuration_id:
            existing = service.configurations.get(current.configuration_id)
            if existing is None or existing.canonical_config_json != canonical_json(document):
                raise ValueError("The retained Candidate is linked to a different StudyPlan")
            return existing.configuration_id
        _, configuration = service.upsert_idea_configuration(
            draft_id=CANDIDATE_ID,
            document=document,
        )
        return configuration.configuration_id
    finally:
        service.close()
