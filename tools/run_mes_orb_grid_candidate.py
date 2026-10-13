"""Exact owner-authorized MES ORB Candidate and immutable StudyPlan mapping."""

from __future__ import annotations

import hashlib
import json
from itertools import product
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
from orchestration.candidate_pipeline_runtime import CandidatePipelineDefinition, CandidateValidationPlan
from persistence import PersistenceService, StrategyLifecycle, canonical_json
from research_intake import parse_candidate_packet, validate_candidate_packet
from strategies.mes_opening_range_breakout import MES_ORB_GRID_SPEC


CANDIDATE_ID = "qfc_457e442c86ef0d1548f32acfc1b88164"
CANDIDATE_VERSION = "8a8dbe4456843ab91f20697eb3dfb9d8832602c0fa6ede624f37cdf7778dfb9b"
STRATEGY_ID = "mes_opening_range_breakout_grid"
STRATEGY_VERSION = "1.0.0"
DATASET_ID = "futures_MES_5m_databento"
DATASET_END = "2023-12-29T21:55:00Z"
EXPERIMENT_ID = "r13_mes_orb_parameter_grid_v1"
RANGE_MINUTES = (5, 10, 15, 20, 30, 45, 60)
BREAKOUT_OFFSETS = (0, 1, 2)
DIRECTIONS = ("long", "short")
PARAMETER_COMBINATIONS = tuple(
    {
        "range_minutes": minutes,
        "breakout_offset_ticks": offset,
        "direction_variant": direction,
    }
    for direction, minutes, offset in product(DIRECTIONS, RANGE_MINUTES, BREAKOUT_OFFSETS)
)


def candidate_fingerprint(draft: IdeaDraftView) -> str:
    validation = validate_candidate_packet(
        parse_candidate_packet(draft.candidate_json, format_hint="json")
    )
    if not validation.valid:
        raise ValueError("Candidate packet is invalid")
    return hashlib.sha256(validation.canonical_json.encode("utf-8")).hexdigest()


def admit_candidate_identity(candidate_id: str, candidate_version: str) -> CandidatePipelineDefinition:
    if candidate_id != CANDIDATE_ID or candidate_version != CANDIDATE_VERSION:
        raise ValueError("Candidate is outside the exact MES ORB executable policy")
    return study_plan_definition()


def admit_candidate(draft: IdeaDraftView) -> CandidatePipelineDefinition:
    return admit_candidate_identity(draft.draft_id, candidate_fingerprint(draft))


def study_plan_definition() -> CandidatePipelineDefinition:
    experiment = ExperimentConfig(
        experiment_id=EXPERIMENT_ID,
        strategy_id=STRATEGY_ID,
        parameter_combinations=PARAMETER_COMBINATIONS,
        market_data=MarketDataConfig(
            symbol="MES", provider="Databento",
            provider_implementation=f"verified_local_catalog:{DATASET_ID}",
            interval="5m", requested_start="2019-05-06",
            end_date_policy="fixed owner-authorized ORB cutoff 2023-12-29",
            adjusted=False, exchange_calendar="NYSE", market_timezone="America/New_York",
            cache_path=Path("futures/MES/5m/MES_5m_databento.parquet"),
        ),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=100_000.0, fees=0.0, slippage=0.0, direction="both",
            leverage=1.0, accumulate=False, position_sizing="fixed_units", order_size=1.0,
            price_multiplier=5.0, fixed_fee_per_contract_per_side=0.62,
            slippage_ticks=1.0, tick_size=0.25,
        ),
        ranking_columns=("total_return", "sharpe_ratio"),
        ranking_ascending=(False, False),
        output_path=Path("unused-mes-orb-grid-output.csv"),
        screening=ScreeningConfig.provisional_defaults(),
    )
    validation = CandidateValidationPlan(
        out_of_sample_split=ChronologicalSplitConfig(
            train_fraction=0.60, selection_fraction=0.20, test_fraction=0.20,
            minimum_rows_per_partition=10_000,
        ),
        out_of_sample_shortlist_size=1,
        walk_forward_rules=WalkForwardWindowRules(
            training_window_size=80_000, selection_window_size=20_000,
            test_window_size=20_000, step_size=20_000, training_mode="rolling",
            minimum_rows_per_window=10_000, incomplete_final_window="drop",
        ),
        walk_forward_shortlist_size=1,
        robustness_neighborhood=NeighborhoodConfig(
            definitions=(
                ParameterNeighborhoodDefinition("range_minutes", "explicit_values", explicit_values=RANGE_MINUTES),
                ParameterNeighborhoodDefinition("breakout_offset_ticks", "explicit_values", explicit_values=BREAKOUT_OFFSETS),
                ParameterNeighborhoodDefinition("direction_variant", "explicit_values", explicit_values=DIRECTIONS),
            ),
            minimum_valid_neighbors=3,
        ),
        robustness_regimes=RegimeConfig(
            trend_window=50, volatility_window=20,
            annualization_factor=252.0 * 78.0, minimum_observations=20,
        ),
        robustness_maximum_drawdown=0.35,
        robustness_minimum_return=0.0,
        robustness_minimum_sharpe=0.5,
        monte_carlo=MonteCarloConfig(
            method="moving_block_bootstrap", simulation_count=1_000,
            minimum_observations=10, block_length=5,
        ),
        data_as_of=DATASET_END,
    )
    return CandidatePipelineDefinition(
        experiment=experiment, strategy_version=STRATEGY_VERSION, validation=validation,
    )


def persist_admitted_study_plan(*, database: str | Path) -> str:
    drafts = {draft.draft_id: draft for draft in list_idea_drafts(database)}
    draft = drafts.get(CANDIDATE_ID)
    if draft is None:
        raise ValueError("The exact MES ORB Candidate is missing")
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
        service.register_strategy(
            strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
            display_name=MES_ORB_GRID_SPEC.identity.name,
            description=MES_ORB_GRID_SPEC.identity.description,
            lifecycle=StrategyLifecycle.CANDIDATE, active=True,
        )
        current = service.idea_drafts.get(CANDIDATE_ID)
        if current is None or current.candidate_json != draft.candidate_json:
            raise ValueError("The exact MES ORB Candidate changed during admission")
        if current.configuration_id:
            existing = service.configurations.get(current.configuration_id)
            if existing is None or existing.canonical_config_json != canonical_json(document):
                raise ValueError("The MES ORB Candidate is linked to a different StudyPlan")
            return existing.configuration_id
        _, configuration = service.upsert_idea_configuration(
            draft_id=CANDIDATE_ID, document=document,
        )
        return configuration.configuration_id
    finally:
        service.close()
