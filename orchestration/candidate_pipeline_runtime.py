"""Generic runtime composition for one approved candidate research pipeline.

The durable launch service owns submission identity, the filter-chain service
owns ordering and replay, and the existing research engines own computation.
This module only supplies the missing production adapters between them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.experiments import ExperimentConfig, execute_experiment
from backtesting.monte_carlo import MonteCarloConfig, SourceSeries, run_monte_carlo
from backtesting.out_of_sample import (
    ChronologicalSplitConfig,
    OutOfSampleConfig,
    OutOfSampleProgressionError,
    execute_out_of_sample,
)
from backtesting.robustness import (
    NeighborhoodConfig,
    RegimeConfig,
    RobustnessConfig,
    build_neighborhood,
    run_robustness_pipeline,
)
from backtesting.validation import WalkForwardWindowRules
from backtesting.walk_forward import WalkForwardConfig, execute_walk_forward
from market_data import load_market_data
from orchestration.candidate_run_service import (
    CandidateRunService,
    CandidateScreeningLaunchResult,
)
from orchestration.filter_chain import (
    FactoryFilterChainService,
    FilterChainOutcome,
    FilterChainReplayIncompleteError,
    FilterStageContext,
    PersistedStageReference,
)
from orchestration.research_launch_claims import (
    CANDIDATE_SCREENING_LAUNCH_CONTRACT,
    DurableResearchLaunchService,
)
from persistence import (
    ArtifactType,
    EventSeverity,
    PersistenceService,
    RunEventType,
    RunStage,
    RunStatus,
    canonical_json,
)
from persistence.evidence_service import ValidationEvidenceArtifactService
from persistence.models import ResearchRunSubmissionRecord
from persistence.service import (
    RUNTIME_LINEAGE_ENVIRONMENT_KEY,
    capture_runtime_lineage_document,
    configuration_document_from_experiment_config,
)
from strategies import get_strategy


VALIDATION_RUNTIME_KEY = "candidate_validation_runtime"


@dataclass(frozen=True)
class CandidateValidationPlan:
    """Fixed, serializable boundaries for the existing validation engines."""

    out_of_sample_split: ChronologicalSplitConfig
    out_of_sample_shortlist_size: int
    walk_forward_rules: WalkForwardWindowRules
    walk_forward_shortlist_size: int
    robustness_neighborhood: NeighborhoodConfig
    robustness_regimes: RegimeConfig
    robustness_maximum_drawdown: float
    robustness_minimum_return: float
    robustness_minimum_sharpe: float | None
    monte_carlo: MonteCarloConfig
    data_as_of: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("out_of_sample_shortlist_size", self.out_of_sample_shortlist_size),
            ("walk_forward_shortlist_size", self.walk_forward_shortlist_size),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.data_as_of is not None:
            timestamp = pd.Timestamp(self.data_as_of)
            if timestamp.tzinfo is None:
                raise ValueError("data_as_of must include a timezone")

    def document(self) -> dict[str, Any]:
        return {
            "out_of_sample": {
                "split": asdict(self.out_of_sample_split),
                "shortlist_size": self.out_of_sample_shortlist_size,
            },
            "walk_forward": {
                "rules": asdict(self.walk_forward_rules),
                "shortlist_size": self.walk_forward_shortlist_size,
            },
            "robustness": {
                "neighborhood": asdict(self.robustness_neighborhood),
                "regimes": asdict(self.robustness_regimes),
                "maximum_drawdown": self.robustness_maximum_drawdown,
                "minimum_return": self.robustness_minimum_return,
                "minimum_sharpe": self.robustness_minimum_sharpe,
            },
            "monte_carlo": asdict(self.monte_carlo),
            "data_as_of": self.data_as_of,
            "protected_data_state": "gated",
        }


@dataclass(frozen=True)
class CandidatePipelineDefinition:
    """One approved experiment and its fixed generic validation boundaries."""

    experiment: ExperimentConfig
    strategy_version: str
    validation: CandidateValidationPlan

    def configuration_document(self) -> dict[str, Any]:
        document = configuration_document_from_experiment_config(
            self.experiment,
            strategy_version=self.strategy_version,
        )
        document[VALIDATION_RUNTIME_KEY] = self.validation.document()
        return document


@dataclass(frozen=True)
class CandidatePipelineLaunchResult:
    launch: CandidateScreeningLaunchResult
    chain: FilterChainOutcome


class CandidatePipelineReplayIncompleteError(RuntimeError):
    """An acknowledged launch lacks a complete, safely reopenable chain."""


class CandidatePipelineRuntime:
    """Compose the existing durable launch, runners, evidence, and coordinator."""

    def __init__(
        self,
        *,
        database: str | Path,
        artifact_root: str | Path,
        configuration_id: str,
        definition: CandidatePipelineDefinition,
        dispatcher_instance_id: str | None = None,
    ) -> None:
        self.database = Path(database)
        self.artifact_root = Path(artifact_root)
        self.configuration_id = configuration_id
        self.definition = definition
        self.dispatcher_instance_id = dispatcher_instance_id

    def launch(self, *, idempotency_key: str) -> CandidatePipelineLaunchResult:
        service = CandidateRunService(
            database=self.database,
            screening_adapter=self._prefect_adapter,
            dispatcher_instance_id=self.dispatcher_instance_id,
        )
        launch = service.launch_screening(
            idempotency_key=idempotency_key,
            configuration_id=self._configuration_id(),
            environment={
                "candidate_pipeline_runtime": "generic_v1",
                RUNTIME_LINEAGE_ENVIRONMENT_KEY: capture_runtime_lineage_document(),
            },
        )
        if launch.dispatch.invoked:
            chain = launch.dispatch.value
            if not isinstance(chain, FilterChainOutcome):
                raise RuntimeError("candidate pipeline flow returned no filter-chain outcome")
        else:
            chain = self._reopen_completed_chain(launch.claim.run.run_id)
        return CandidatePipelineLaunchResult(launch=launch, chain=chain)

    def _configuration_id(self) -> str:
        expected = canonical_json(self.definition.configuration_document())
        persistence = PersistenceService(self.database)
        try:
            configuration = persistence.configurations.get(self.configuration_id)
            if configuration is None:
                raise KeyError(
                    f"unknown approved candidate configuration {self.configuration_id}"
                )
            if configuration.canonical_config_json != expected:
                raise ValueError(
                    "runtime definition differs from the approved candidate configuration"
                )
            return configuration.configuration_id
        finally:
            persistence.close()
    def _prefect_adapter(
        self,
        submission: ResearchRunSubmissionRecord,
        _claims: DurableResearchLaunchService,
    ) -> FilterChainOutcome:
        from prefect_spike.candidate_pipeline_flow import run_candidate_pipeline_flow

        return run_candidate_pipeline_flow(runtime=self, submission=submission)

    def execute_flow(
        self,
        *,
        submission: ResearchRunSubmissionRecord,
        prefect_flow_run_id: str,
    ) -> FilterChainOutcome:
        claims = DurableResearchLaunchService(
            database=self.database,
            launch_contract=CANDIDATE_SCREENING_LAUNCH_CONTRACT,
            initialize_schema=False,
        )
        claims.bind_prefect_identity(
            idempotency_key=submission.idempotency_key,
            run_id=submission.run_id,
            configuration_id=submission.configuration_id,
            canonical_request_json=submission.canonical_request_json,
            request_fingerprint=submission.request_fingerprint,
            prefect_flow_run_id=prefect_flow_run_id,
        )

        persistence = PersistenceService(self.database)
        try:
            execution_document = self._validate_saved_configuration(
                persistence,
                submission.configuration_id,
            )
            market = load_market_data(
                self.definition.experiment.market_data,
                now=(
                    pd.Timestamp(self.definition.validation.data_as_of)
                    if self.definition.validation.data_as_of is not None
                    else None
                ),
            )
            try:
                screening_result = execute_experiment(
                    self.definition.experiment,
                    market.data,
                    market.audit,
                    write_output=False,
                )
                persistence.persist_experiment_inputs_on_run(
                    run_id=submission.run_id,
                    config=self.definition.experiment,
                    result=screening_result,
                    execution_assumptions=execution_document,
                    include_parameter_results=True,
                )
                persistence.persist_run_manifest(
                    persistence.build_run_manifest(submission.run_id)
                )
                persistence.transition_run_with_operator_event(
                    run_id=submission.run_id,
                    status=RunStatus.SUCCEEDED,
                    event_type=RunEventType.RUN_SUCCEEDED,
                    severity=EventSeverity.INFO,
                    source="candidate_pipeline_runtime",
                    message="Candidate screening completed through the generic runtime.",
                )
            except Exception as exc:
                current = persistence.runs.get(submission.run_id)
                if current is not None and current.status == RunStatus.RUNNING:
                    persistence.transition_run_with_operator_event(
                        run_id=submission.run_id,
                        status=RunStatus.FAILED,
                        event_type=RunEventType.RUN_FAILED,
                        severity=EventSeverity.ERROR,
                        source="candidate_pipeline_runtime",
                        message="Candidate screening failed closed in the generic runtime.",
                        error_summary=str(exc)[:500],
                    )
                raise

            adapters = self._stage_adapters(
                persistence=persistence,
                screening_result=screening_result,
                data=market.data,
                audit=market.audit,
                execution_document=execution_document,
            )
            return FactoryFilterChainService(
                persistence,
                artifact_root=self.artifact_root,
            ).run(
                screening_run_id=submission.run_id,
                stage_adapters=adapters,
            )
        finally:
            persistence.close()

    def _validate_saved_configuration(
        self,
        persistence: PersistenceService,
        configuration_id: str,
    ) -> dict[str, Any]:
        configuration = persistence.configurations.get(configuration_id)
        if configuration is None:
            raise KeyError(f"unknown candidate configuration {configuration_id}")
        expected = canonical_json(self.definition.configuration_document())
        if configuration.canonical_config_json != expected:
            raise ValueError("runtime definition differs from the durable candidate configuration")
        document = json.loads(configuration.canonical_config_json)
        execution = document.get("execution")
        if not isinstance(execution, dict):
            raise ValueError("candidate configuration execution assumptions are malformed")
        return execution

    def _stage_adapters(
        self,
        *,
        persistence: PersistenceService,
        screening_result: Any,
        data: Any,
        audit: Any,
        execution_document: dict[str, Any],
    ) -> dict[RunStage, Any]:
        evidence = ValidationEvidenceArtifactService(persistence)
        plan = self.definition.validation
        experiment = self.definition.experiment

        def prepare(context: FilterStageContext) -> None:
            persistence.transition_run_with_operator_event(
                run_id=context.run_id,
                status=RunStatus.RUNNING,
                event_type=RunEventType.RUN_STARTED,
                severity=EventSeverity.INFO,
                source="candidate_pipeline_runtime",
                message=f"Started generic {context.stage.value} validation.",
            )
            persistence.persist_experiment_inputs_on_run(
                run_id=context.run_id,
                config=experiment,
                result=screening_result,
                execution_assumptions=execution_document,
                include_parameter_results=False,
            )

        def complete(context: FilterStageContext) -> PersistedStageReference:
            persistence.transition_run_with_operator_event(
                run_id=context.run_id,
                status=RunStatus.SUCCEEDED,
                event_type=RunEventType.RUN_SUCCEEDED,
                severity=EventSeverity.INFO,
                source="candidate_pipeline_runtime",
                message=f"Completed generic {context.stage.value} validation.",
            )
            return PersistedStageReference(stage=context.stage, run_id=context.run_id)

        def persist_oos_report(context: FilterStageContext, path: Path) -> None:
            content = path.read_bytes()
            document = json.loads(content)
            artifact_id = str(document.get("artifact_id") or path.stem)
            location = str(path.relative_to(self.artifact_root))
            persistence.register_artifact(
                run_id=context.run_id,
                artifact_type=ArtifactType.VALIDATION_EVIDENCE,
                logical_name=f"source_lock_evidence:{artifact_id}",
                media_type="application/json",
                format="json",
                location=location,
                content=content,
                schema_version=1,
            )
            persistence.persist_run_manifest(
                persistence.build_run_manifest(context.run_id)
            )

        def oos(context: FilterStageContext) -> PersistedStageReference:
            prepare(context)
            path = self.artifact_root / context.run_id / "out_of_sample.json"
            config = OutOfSampleConfig(
                experiment=experiment,
                split=plan.out_of_sample_split,
                output_path=path,
                shortlist_size=plan.out_of_sample_shortlist_size,
            )
            try:
                execute_out_of_sample(config, data, audit, write_output=True)
            except OutOfSampleProgressionError:
                persist_oos_report(context, path)
                return complete(context)
            persist_oos_report(context, path)
            return complete(context)

        def walk_forward(context: FilterStageContext) -> PersistedStageReference:
            prepare(context)
            rules = plan.walk_forward_rules
            result = execute_walk_forward(
                WalkForwardConfig(
                    experiment=experiment,
                    training_window_size=rules.training_window_size,
                    selection_window_size=rules.selection_window_size,
                    test_window_size=rules.test_window_size,
                    step_size=rules.step_size,
                    training_mode=rules.training_mode,
                    minimum_rows_per_window=rules.minimum_rows_per_window,
                    shortlist_size=plan.walk_forward_shortlist_size,
                    incomplete_final_window=rules.incomplete_final_window,
                    output_path=self.artifact_root / context.run_id / "walk_forward.json",
                ),
                data,
                audit,
                write_output=False,
            )
            evidence.persist_walk_forward(
                run_id=context.run_id,
                result=result,
                rules=rules,
                artifact_root=self.artifact_root,
            )
            return complete(context)

        def robustness(context: FilterStageContext) -> PersistedStageReference:
            prepare(context)
            source_lock = evidence.retrieve_out_of_sample_source_lock(
                context.previous[0].run_id,
                artifact_root=self.artifact_root,
            )
            config = RobustnessConfig(
                strategy_id=screening_result.strategy_id,
                strategy_version=screening_result.strategy_version,
                locked_parameters=source_lock.locked_parameters,
                experiment_id=experiment.experiment_id,
                source_artifact_id=source_lock.artifact_id,
                source_start=source_lock.source_start,
                source_end=source_lock.source_end,
                data_provenance=source_lock.data_provenance,
                execution_assumptions=source_lock.execution_assumptions,
                neighborhood=plan.robustness_neighborhood,
                regimes=plan.robustness_regimes,
                maximum_drawdown=plan.robustness_maximum_drawdown,
                minimum_return=plan.robustness_minimum_return,
                minimum_sharpe=plan.robustness_minimum_sharpe,
            )
            strategy = get_strategy(experiment.strategy_id)
            construction = build_neighborhood(
                strategy,
                source_lock.locked_parameters,
                plan.robustness_neighborhood,
            )
            robustness_data = data.loc[
                source_lock.source_start : source_lock.source_end
            ].copy()
            if robustness_data.empty:
                raise ValueError("source-lock boundaries contain no robustness data")
            robustness_audit = replace(
                audit,
                actual_first_row_date=str(robustness_data.index[0].date()),
                actual_last_row_date=str(robustness_data.index[-1].date()),
                row_count=len(robustness_data),
                cache_action="partition:out_of_sample",
                cache_decision_reason="locked out-of-sample robustness source",
            )
            result = run_robustness_pipeline(
                config,
                construction,
                experiment,
                robustness_data,
                robustness_audit,
            )
            evidence.persist_robustness(
                run_id=context.run_id,
                result=result,
                artifact_root=self.artifact_root,
                protected_data_state="gated",
            )
            return complete(context)

        def monte_carlo(context: FilterStageContext) -> PersistedStageReference:
            prepare(context)
            source_lock = evidence.retrieve_out_of_sample_source_lock(
                context.previous[0].run_id,
                artifact_root=self.artifact_root,
            )
            walk_reference = next(
                item for item in context.previous if item.stage == RunStage.WALK_FORWARD
            )
            persisted = evidence.retrieve_walk_forward(
                walk_reference.run_id,
                artifact_root=self.artifact_root,
            )
            folds = persisted.document["evidence"]["folds"]
            values = tuple(
                float(fold["test_metrics"]["total_return"])
                for fold in folds
                if fold.get("status") == "successful"
            )
            result = run_monte_carlo(
                SourceSeries(
                    source_id=persisted.evidence_identity,
                    source_kind="fold_endpoint_returns",
                    experiment_id=experiment.experiment_id,
                    strategy_id=screening_result.strategy_id,
                    strategy_version=screening_result.strategy_version,
                    values=values,
                    provenance={
                        "walk_forward_evidence_identity": persisted.evidence_identity
                    },
                    execution_assumptions=source_lock.execution_assumptions,
                    period_frequency="walk-forward-fold",
                ),
                plan.monte_carlo,
            )
            evidence.persist_monte_carlo(
                run_id=context.run_id,
                result=result,
                artifact_root=self.artifact_root,
                protected_data_state="gated",
            )
            return complete(context)

        return {
            RunStage.OOS: oos,
            RunStage.WALK_FORWARD: walk_forward,
            RunStage.ROBUSTNESS: robustness,
            RunStage.MONTE_CARLO: monte_carlo,
        }

    def _reopen_completed_chain(self, screening_run_id: str) -> FilterChainOutcome:
        persistence = PersistenceService(self.database)
        try:
            screening = persistence.runs.get(screening_run_id)
            if screening is None or screening.status != RunStatus.SUCCEEDED:
                raise CandidatePipelineReplayIncompleteError(
                    "candidate screening replay is not a completed successful run"
                )
            try:
                return FactoryFilterChainService(
                    persistence,
                    artifact_root=self.artifact_root,
                ).reopen(screening_run_id=screening_run_id)
            except FilterChainReplayIncompleteError as exc:
                raise CandidatePipelineReplayIncompleteError(str(exc)) from exc
        finally:
            persistence.close()
