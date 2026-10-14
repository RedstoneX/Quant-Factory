"""Automatic testing of one valid idea's generated rule strategy.

Every number below is copied from the one source-attributed MES setup
(dashboard/mes_candidate_setup.py, ``mes_candidate_definition``); nothing here
is tuned. Only datasets whose contract costs that setup records are supported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import itertools
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Protocol

import pandas as pd

from backtesting.experiments.models import ExecutionConfig, ExperimentConfig
from backtesting.monte_carlo import MonteCarloConfig
from backtesting.out_of_sample import ChronologicalSplitConfig
from backtesting.robustness import (
    FixedRuleCostStressPlan,
    NeighborhoodConfig,
    ParameterNeighborhoodDefinition,
    RegimeConfig,
)
from backtesting.robustness.models import FractionalCostStressPlan
from backtesting.screening import ScreeningConfig
from backtesting.validation import WalkForwardWindowRules
from market_data import DatasetUnavailableError, MarketDataConfig, load_market_data
from market_data.alpaca_sip_universe import UNIVERSE
from orchestration.auto_campaign_stocks import STOCK_INTERVAL, StockCostsUnavailable, stock_profile_fields
from orchestration.candidate_pipeline_runtime import (
    CandidatePipelineDefinition,
    CandidatePipelineReplayIncompleteError,
    CandidatePipelineRuntime,
    CandidateValidationPlan,
)
from persistence import PersistenceService, StrategyLifecycle, canonical_json

POLICY_ID = "auto_test_v1"
_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][^\s'\"\\/]+){2,}[\\/]?")


@dataclass(frozen=True)
class DatasetProfile:
    """One verified local dataset plus the costs its source setup records."""

    dataset_id: str
    symbol: str
    interval: str
    dataset_end: str
    requested_start: str
    end_date_policy: str
    cache_path: Path
    fixed_fee_per_contract_per_side: float
    slippage_ticks: float
    tick_size: float
    price_multiplier: float
    stress_fee_per_contract_per_side: float
    stress_slippage_ticks: float
    annualization_factor: float
    # Defaults are the MES values, so the MES profile and its saved setups are unchanged.
    provider: str = "Databento"
    adjusted: bool = False
    initial_cash: float = 100_000.0
    position_sizing: str = "fixed_units"
    order_size: float = 1.0
    fees: float = 0.0
    slippage: float = 0.0
    stress_slippage: float = 0.0


# Copied verbatim from dashboard/mes_candidate_setup.py (DATASET_ID, DATASET_END,
# BASELINE_*/STRESS_* constants and the MarketDataConfig/ExecutionConfig values).
_PROFILES = {
    ("MES", "5m"): DatasetProfile(
        dataset_id="futures_MES_5m_databento",
        symbol="MES",
        interval="5m",
        dataset_end="2026-02-13T21:55:00Z",
        requested_start="2019-05-06",
        end_date_policy="fixed verified catalog end 2026-02-13",
        cache_path=Path("futures/MES/5m/MES_5m_databento.parquet"),
        fixed_fee_per_contract_per_side=0.62,
        slippage_ticks=1.0,
        tick_size=0.25,
        price_multiplier=5.0,
        stress_fee_per_contract_per_side=1.24,
        stress_slippage_ticks=2.0,
        annualization_factor=252.0 * 78.0,
    ),
}


@dataclass(frozen=True)
class InstalledRuleStrategy:
    strategy_id: str
    version: str
    name: str
    description: str


class RuleStrategyAdapter(Protocol):
    def definition(
        self, *, candidate_id: str, title: str, rule_spec: Mapping[str, Any], variables: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def install(self, definition: Mapping[str, Any]) -> InstalledRuleStrategy: ...


class GeneratedRuleStrategyAdapter:
    """The only caller of strategies.rule_spec_strategy (imported on use)."""

    @staticmethod
    def available() -> bool:
        try:
            return importlib.util.find_spec("strategies.rule_spec_strategy") is not None
        except ImportError:
            return False

    def definition(
        self, *, candidate_id: str, title: str, rule_spec: Mapping[str, Any], variables: Mapping[str, Any]
    ) -> dict[str, Any]:
        from strategies.rule_spec_strategy import rule_strategy_definition

        return rule_strategy_definition(
            candidate_id=candidate_id, title=title, rule_spec=rule_spec, variables=variables
        )

    def install(self, definition: Mapping[str, Any]) -> InstalledRuleStrategy:
        from strategies.rule_spec_strategy import install_rule_strategy

        identity = install_rule_strategy(dict(definition)).spec.identity
        return InstalledRuleStrategy(
            strategy_id=identity.strategy_id,
            version=identity.version,
            name=identity.name,
            description=identity.description,
        )


@dataclass(frozen=True)
class AutoTestRequest:
    candidate_id: str
    definition: Mapping[str, Any]
    profile: DatasetProfile
    database: str
    artifact_root: str
    attempt: int = 0  # earlier runs of this exact packet that a restart cut short


@dataclass(frozen=True)
class AutoTestOutcome:
    state: str
    reason_code: str
    reason_detail: str | None = None
    run_id: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


Launch = Callable[[str, str], tuple[str, Any]]
DataCheck = Callable[[CandidatePipelineDefinition, DatasetProfile], None]


def dataset_profile(symbol: str, timeframe: str) -> DatasetProfile | None:
    """MES 5m from the fixed table; a universe stock at 1m from its manifest and measured spread."""
    key = (symbol.strip().upper(), timeframe.strip())
    if key in _PROFILES:
        return _PROFILES[key]
    if key[1] != STOCK_INTERVAL or key[0] not in UNIVERSE:
        return None
    try:
        return DatasetProfile(**stock_profile_fields(key[0]))
    except (StockCostsUnavailable, DatasetUnavailableError, FileNotFoundError):
        # No measured spread or no manifest: the caller reports no dataset with costs.
        return None


def campaign_idempotency_key(candidate_id: str, strategy_id: str, attempt: int = 0) -> str:
    # The launch-key contract allows only letters, digits, '_' and '-'. A rerun after
    # an interrupted attempt needs its own key: a key is never invoked twice.
    return f"{candidate_id}-{strategy_id}" + (f"-r{attempt}" if attempt else "")


def safe_detail(text: object, *, limit: int = 300) -> str:
    """One plain line with host paths removed, for operator display."""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    line = _PATH.sub("<path>", lines[0] if lines else "")
    return line[:limit] or "No further detail was recorded."


def parameter_combinations(variables: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    names = sorted(variables)
    if not names:
        return ({},)
    values = [list(dict(variables[name])["values"]) for name in names]
    return tuple(dict(zip(names, combination)) for combination in itertools.product(*values))


def auto_test_definition(
    *, candidate_id: str, strategy_id: str, strategy_version: str, variables: Mapping[str, Any], profile: DatasetProfile
) -> CandidatePipelineDefinition:
    """Mirror mes_candidate_definition() for one generated rule strategy."""
    experiment = ExperimentConfig(
        experiment_id=f"{POLICY_ID}_{candidate_id}",
        strategy_id=strategy_id,
        parameter_combinations=parameter_combinations(variables),
        market_data=MarketDataConfig(
            symbol=profile.symbol,
            provider=profile.provider,
            provider_implementation=f"verified_local_catalog:{profile.dataset_id}",
            interval=profile.interval,
            requested_start=profile.requested_start,
            end_date_policy=profile.end_date_policy,
            adjusted=profile.adjusted,
            exchange_calendar="NYSE",
            market_timezone="America/New_York",
            cache_path=profile.cache_path,
        ),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=profile.initial_cash, fees=profile.fees, slippage=profile.slippage,
            direction="both", leverage=1.0, accumulate=False,
            position_sizing=profile.position_sizing,  # type: ignore[arg-type]
            order_size=profile.order_size,
            price_multiplier=profile.price_multiplier,
            fixed_fee_per_contract_per_side=profile.fixed_fee_per_contract_per_side,
            slippage_ticks=profile.slippage_ticks,
            tick_size=profile.tick_size,
        ),
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        output_path=Path("unused-auto-test-output.csv"),
        screening=ScreeningConfig.provisional_defaults(),
    )
    # The pipeline takes exactly one robustness test: parameter-free rules get the
    # fixed-rule cost stress; rules with variables get a neighbourhood over the
    # declared values, as tools/run_mes_orb_grid_candidate.py does.
    stress = neighborhood = None
    if variables:
        neighborhood = NeighborhoodConfig(
            definitions=tuple(
                ParameterNeighborhoodDefinition(name, "explicit_values", explicit_values=tuple(spec["values"]))
                for name, spec in sorted(variables.items())
            ),
            minimum_valid_neighbors=3,
        )
    elif profile.position_sizing == "fixed_units":
        stress = FixedRuleCostStressPlan(
            fixed_fee_per_contract_per_side=profile.stress_fee_per_contract_per_side,
            slippage_ticks=profile.stress_slippage_ticks,
        )
    else:
        # Whole-share stock: 2x slippage, the same regulatory fees.
        stress = FractionalCostStressPlan(fees=profile.fees, slippage=profile.stress_slippage)
    validation = CandidateValidationPlan(
        out_of_sample_split=ChronologicalSplitConfig(
            train_fraction=0.60, selection_fraction=0.20, test_fraction=0.20, minimum_rows_per_partition=10_000,
        ),
        out_of_sample_shortlist_size=1,
        walk_forward_rules=WalkForwardWindowRules(
            training_window_size=80_000, selection_window_size=20_000, test_window_size=20_000,
            step_size=20_000, training_mode="rolling", minimum_rows_per_window=10_000,
            incomplete_final_window="drop",
        ),
        walk_forward_shortlist_size=1,
        robustness_neighborhood=neighborhood,
        robustness_regimes=RegimeConfig(
            trend_window=50, volatility_window=20,
            annualization_factor=profile.annualization_factor, minimum_observations=20,
        ),
        robustness_maximum_drawdown=0.35,
        robustness_minimum_return=0.0,
        robustness_minimum_sharpe=0.5,
        monte_carlo=MonteCarloConfig(
            method="moving_block_bootstrap", simulation_count=1_000, minimum_observations=10, block_length=5,
        ),
        data_as_of=profile.dataset_end,
        fixed_rule_cost_stress=stress,
    )
    return CandidatePipelineDefinition(experiment=experiment, strategy_version=strategy_version, validation=validation)


def earlier_owner_of_strategy(*, database: str | Path, strategy_id: str, candidate_id: str) -> str | None:
    """Return another idea already linked to a setup for this exact strategy."""
    service = PersistenceService(database)
    try:
        configuration_ids = {row.configuration_id for row in service.configurations.list(strategy_id=strategy_id)}
        owners = sorted(
            (draft.created_at, draft.draft_id)
            for draft in service.idea_drafts.list()
            if draft.configuration_id in configuration_ids and draft.draft_id != candidate_id
        )
        return owners[0][1] if owners else None
    finally:
        service.close()


def outcome_from_chain(chain: Any, run_id: str) -> AutoTestOutcome:
    """Map the pipeline's own recorded chain outcome to a campaign state."""
    status = getattr(chain, "status", None)
    reasons = tuple(str(reason) for reason in getattr(chain, "reasons", ()) or ())
    if status == "ready_for_protected_test":
        return AutoTestOutcome("survivor", "awaiting_owner_review", safe_detail(" ".join(reasons) or "Passed every automatic filter."), run_id)
    if status in {"screened_out", "stopped"} and getattr(chain, "stopped_at", None):
        detail = safe_detail(reasons[0] if reasons else f"Stopped at {chain.stopped_at}.")
        return AutoTestOutcome("screened_out", str(chain.stopped_at), detail, run_id)
    return AutoTestOutcome("failed", "run_error", safe_detail(f"The pipeline finished with an unrecognized outcome {status!r}."), run_id)


def _check_verified_data(definition: CandidatePipelineDefinition, profile: DatasetProfile) -> None:
    load_market_data(definition.experiment.market_data, now=pd.Timestamp(profile.dataset_end), allow_download=False)


def runtime_launch(*, database: str | Path, artifact_root: str | Path, pipeline_launcher: Any) -> Launch:
    """The gateway's existing launch chain, returning the run and its chain outcome."""

    def launch(configuration_id: str, idempotency_key: str) -> tuple[str, Any]:
        runtime = CandidatePipelineRuntime.from_saved_configuration(
            database=database, artifact_root=artifact_root, configuration_id=configuration_id,
            pipeline_launcher=pipeline_launcher, cache_only=True,
        )
        result = runtime.launch(idempotency_key=idempotency_key)
        return result.launch.claim.run.run_id, result.chain

    return launch


def run_auto_test(
    request: AutoTestRequest, *, adapter: RuleStrategyAdapter, launch: Launch, data_check: DataCheck = _check_verified_data
) -> AutoTestOutcome:
    """Install, save, link and launch one idea; never approves or promotes."""
    try:
        installed = adapter.install(request.definition)
    except ValueError as exc:
        return AutoTestOutcome("implementation_blocked", "rules_invalid", safe_detail(exc))
    definition = auto_test_definition(
        candidate_id=request.candidate_id, strategy_id=installed.strategy_id, strategy_version=installed.version,
        variables=request.definition.get("variables") or {}, profile=request.profile,
    )
    document = json.loads(canonical_json(definition.configuration_document()))
    CandidatePipelineDefinition.from_configuration_document(document)
    try:
        data_check(definition, request.profile)
    except (DatasetUnavailableError, OSError, ValueError) as exc:
        return AutoTestOutcome("implementation_blocked", "data_unavailable", safe_detail(f"Verified local data could not be read: {exc}"))
    service = PersistenceService(request.database)
    try:
        service.register_strategy(
            strategy_id=installed.strategy_id, strategy_version=installed.version, display_name=installed.name,
            description=installed.description, lifecycle=StrategyLifecycle.CANDIDATE, active=True,
        )
        _draft, configuration = service.upsert_idea_configuration(draft_id=request.candidate_id, document=document)
    finally:
        service.close()
    key = campaign_idempotency_key(request.candidate_id, installed.strategy_id, request.attempt)
    try:
        run_id, chain = launch(configuration.configuration_id, key)
    except CandidatePipelineReplayIncompleteError:
        # A repeated key never invokes the pipeline twice; an interrupted first
        # attempt cannot be reopened, so it is reported rather than rerun.
        return AutoTestOutcome(
            "failed", "run_error",
            "An earlier attempt was interrupted before finishing and was not run a second time.",
        )
    return outcome_from_chain(chain, run_id)
