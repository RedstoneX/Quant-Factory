"""One fixed, source-attributed setup for Terry's accepted MES Candidate."""

from __future__ import annotations

import json
import hashlib
from dataclasses import replace
from pathlib import Path

import pandas as pd
from backtesting.experiments.models import ExecutionConfig, ExperimentConfig
from backtesting.monte_carlo import MonteCarloConfig
from backtesting.out_of_sample import ChronologicalSplitConfig
from backtesting.robustness import FixedRuleCostStressPlan, RegimeConfig
from backtesting.screening import ScreeningConfig
from backtesting.validation import WalkForwardWindowRules
from dashboard.candidate_workflow import candidate_identity
from dashboard.run_adapter import list_idea_drafts
from market_data import MarketDataConfig, load_market_data
from orchestration import CandidatePipelineDefinition, CandidateValidationPlan
from persistence import PersistenceService, StrategyLifecycle, canonical_json
from research_intake import validate_candidate_packet
from strategies.mes_sma_crossover_candidate import MES_SMA_SPEC, STRATEGY_ID as SMA_STRATEGY_ID, STRATEGY_VERSION as SMA_STRATEGY_VERSION
from strategies.mes_vwap_orb_candidate import (
    CANDIDATE_ID,
    CANDIDATE_VERSION,
    MES_VWAP_ORB_SPEC,
    STRATEGY_ID,
    STRATEGY_VERSION,
)

DATASET_ID = "futures_MES_5m_databento"
DATASET_END = "2026-02-13T21:55:00Z"
BASELINE_FEE = 0.62
BASELINE_SLIPPAGE_TICKS = 1.0
STRESS_FEE = 1.24
STRESS_SLIPPAGE_TICKS = 2.0


def sma_candidate_fingerprint() -> str:
    packet = json.loads((Path(__file__).resolve().parents[1] / "research_intake" / "mes_sma_10_30_candidate.json").read_text())
    packet["candidate"]["status"] = "owner_approved"
    return hashlib.sha256(validate_candidate_packet(packet).canonical_json.encode("utf-8")).hexdigest()


def candidate_setup_definition(identity) -> CandidatePipelineDefinition | None:
    if identity is None or identity.status != "owner_approved":
        return None
    if identity.candidate_id == CANDIDATE_ID and identity.version_fingerprint == CANDIDATE_VERSION:
        return mes_candidate_definition()
    if identity.version_fingerprint == sma_candidate_fingerprint():
        baseline = mes_candidate_definition()
        return replace(baseline, experiment=replace(
            baseline.experiment,
            experiment_id="mes_intraday_sma_10_30_candidate_v1",
            strategy_id=SMA_STRATEGY_ID,
        ), strategy_version=SMA_STRATEGY_VERSION)
    return None


def mes_candidate_definition() -> CandidatePipelineDefinition:
    """Return the one inspectable setup contract; constructing it runs nothing."""
    experiment = ExperimentConfig(
        experiment_id="mes_15m_orb_vwap_quality_candidate_v1",
        strategy_id=STRATEGY_ID,
        parameter_combinations=({},),
        market_data=MarketDataConfig(
            symbol="MES",
            provider="Databento",
            provider_implementation=f"verified_local_catalog:{DATASET_ID}",
            interval="5m",
            requested_start="2019-05-06",
            end_date_policy="fixed verified catalog end 2026-02-13",
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
            fixed_fee_per_contract_per_side=BASELINE_FEE,
            slippage_ticks=BASELINE_SLIPPAGE_TICKS,
            tick_size=0.25,
        ),
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        output_path=Path("unused-mes-candidate-output.csv"),
        screening=ScreeningConfig.provisional_defaults(),
    )
    validation = CandidateValidationPlan(
        out_of_sample_split=ChronologicalSplitConfig(
            train_fraction=0.60,
            selection_fraction=0.20,
            test_fraction=0.20,
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
        robustness_neighborhood=None,
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
        fixed_rule_cost_stress=FixedRuleCostStressPlan(
            fixed_fee_per_contract_per_side=STRESS_FEE,
            slippage_ticks=STRESS_SLIPPAGE_TICKS,
        ),
    )
    return CandidatePipelineDefinition(
        experiment=experiment,
        strategy_version=STRATEGY_VERSION,
        validation=validation,
    )


def save_mes_candidate_setup(*, draft_id: str, database: str | Path) -> str:
    """Save and link only the exact approved Candidate version; never launch."""
    draft = next((item for item in list_idea_drafts(database) if item.draft_id == draft_id), None)
    identity = candidate_identity(draft) if draft is not None else None
    definition = candidate_setup_definition(identity)
    if definition is None:
        raise ValueError("The selected saved Candidate has no exact approved implementation")
    if draft.configuration_id:
        raise ValueError("This Candidate already has a saved setup; reopen it instead")
    document = json.loads(canonical_json(definition.configuration_document()))
    # Strict typed round-trip before any durable write.
    CandidatePipelineDefinition.from_configuration_document(document)
    load_market_data(
        definition.experiment.market_data,
        now=pd.Timestamp(DATASET_END),
        allow_download=False,
    )
    service = PersistenceService(database)
    try:
        spec = MES_SMA_SPEC if definition.experiment.strategy_id == SMA_STRATEGY_ID else MES_VWAP_ORB_SPEC
        service.register_strategy(
            strategy_id=spec.identity.strategy_id,
            strategy_version=spec.identity.version,
            display_name=spec.identity.name,
            description=spec.identity.description,
            lifecycle=StrategyLifecycle.CANDIDATE,
            active=True,
        )
        _draft, configuration = service.upsert_idea_configuration(
            draft_id=draft_id,
            document=document,
        )
        return configuration.configuration_id
    finally:
        service.close()
