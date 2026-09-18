"""Coordination boundary for persisted validation evidence artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from persistence.manifest import run_manifest_document
from persistence.models import ReviewState, RunStage
from persistence.serialization import canonical_json


@dataclass(frozen=True)
class ValidationStageOutcome:
    """Normalized stage evidence outcome from strict persisted artifact retrieval."""

    stage: str
    status: str
    reasons: tuple[str, ...]
    protected_data_state: str | None
    evidence_identity: str | None
    artifact_id: int | None
    eligible_to_progress: bool


def _missing_evidence_status(message: str) -> str:
    lower = message.lower()
    if (
        "no persisted manifest" in lower
        or "artifact_missing" in lower
        or lower.endswith("evidence artifact is missing")
    ):
        return "insufficient_evidence"
    return "invalid"


class ValidationEvidenceArtifactService:
    """Coordinate validation evidence artifacts using the persistence facade."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def source_document(self, run_id: str) -> dict[str, Any]:
        """Source identity for validation evidence from run manifest lineage."""
        manifest_document = run_manifest_document(
            self._service.build_run_manifest(run_id),
            include_mutable=False,
        )
        lineage = manifest_document.get("lineage")
        if not isinstance(lineage, dict):
            raise ValueError("run manifest lineage is missing")
        configuration = lineage.get("configuration")
        strategy = lineage.get("strategy")
        data = lineage.get("data")
        execution = lineage.get("execution_assumptions")
        runtime = lineage.get("runtime")
        if not all(
            isinstance(item, dict)
            for item in (configuration, strategy, data, execution, runtime)
        ):
            raise ValueError("run manifest lineage is incomplete")
        run = self._service.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")
        return {
            "run_id": manifest_document["run_id"],
            "configuration_id": manifest_document["configuration_id"],
            "strategy_id": manifest_document["strategy_id"],
            "strategy_version": manifest_document["strategy_version"],
            "stage": run.stage.value,
            "configuration_hash": configuration["config_hash"],
            "data_identity": data["dataset_identity"],
            "execution_assumptions_identity": execution[
                "execution_assumptions_identity"
            ],
            "runtime_identity": runtime["runtime_identity"],
        }

    def persist_walk_forward(
        self,
        *,
        run_id: str,
        result: Any,
        rules: Any,
        artifact_root: str | Path,
    ) -> Any:
        """Persist canonical walk-forward evidence for one walk-forward run."""
        from backtesting.validation.walk_forward_artifacts import (
            persist_walk_forward_evidence_artifact,
        )

        self._require_stage(
            run_id,
            expected=RunStage.WALK_FORWARD,
            evidence_name="walk-forward evidence",
        )
        return persist_walk_forward_evidence_artifact(
            service=self._service,
            run_id=run_id,
            source=self.source_document(run_id),
            result=result,
            rules=rules,
            artifact_root=artifact_root,
        )

    def retrieve_walk_forward(
        self,
        run_id: str,
        *,
        artifact_root: str | Path,
    ) -> Any:
        """Retrieve validated walk-forward evidence for one run."""
        from backtesting.validation.walk_forward_artifacts import (
            retrieve_walk_forward_evidence_artifact,
        )

        return retrieve_walk_forward_evidence_artifact(
            service=self._service,
            run_id=run_id,
            artifact_root=artifact_root,
            expected_source=self.source_document(run_id),
        )

    def persist_monte_carlo(
        self,
        *,
        run_id: str,
        result: Any,
        artifact_root: str | Path,
        protected_data_state: object = "gated",
    ) -> Any:
        """Persist canonical Monte Carlo evidence for one Monte Carlo run."""
        from backtesting.validation.monte_carlo_artifacts import (
            persist_monte_carlo_evidence_artifact,
        )

        self._require_stage(
            run_id,
            expected=RunStage.MONTE_CARLO,
            evidence_name="Monte Carlo evidence",
        )
        return persist_monte_carlo_evidence_artifact(
            service=self._service,
            run_id=run_id,
            source=self.source_document(run_id),
            result=result,
            artifact_root=artifact_root,
            protected_data_state=protected_data_state,
        )

    def retrieve_monte_carlo(
        self,
        run_id: str,
        *,
        artifact_root: str | Path,
    ) -> Any:
        """Retrieve validated Monte Carlo evidence for one run."""
        from backtesting.validation.monte_carlo_artifacts import (
            retrieve_monte_carlo_evidence_artifact,
        )

        return retrieve_monte_carlo_evidence_artifact(
            service=self._service,
            run_id=run_id,
            artifact_root=artifact_root,
            expected_source=self.source_document(run_id),
        )

    def persist_robustness(
        self,
        *,
        run_id: str,
        result: Any,
        artifact_root: str | Path,
        protected_data_state: object = "gated",
    ) -> Any:
        """Persist canonical robustness evidence for one robustness run."""
        from backtesting.validation.robustness_artifacts import (
            persist_robustness_evidence_artifact,
        )

        self._require_stage(
            run_id,
            expected=RunStage.ROBUSTNESS,
            evidence_name="robustness evidence",
        )
        return persist_robustness_evidence_artifact(
            service=self._service,
            run_id=run_id,
            source=self.source_document(run_id),
            result=result,
            artifact_root=artifact_root,
            protected_data_state=protected_data_state,
        )

    def retrieve_robustness(
        self,
        run_id: str,
        *,
        artifact_root: str | Path,
    ) -> Any:
        """Retrieve validated robustness evidence for one run."""
        from backtesting.validation.robustness_artifacts import (
            retrieve_robustness_evidence_artifact,
        )

        return retrieve_robustness_evidence_artifact(
            service=self._service,
            run_id=run_id,
            artifact_root=artifact_root,
            expected_source=self.source_document(run_id),
        )

    def stage_outcome(
        self,
        run_id: str,
        *,
        artifact_root: str | Path,
    ) -> ValidationStageOutcome:
        """Return the normalized outcome for one persisted validation stage."""
        methods = {
            RunStage.WALK_FORWARD: ("walk_forward", self.retrieve_walk_forward),
            RunStage.MONTE_CARLO: ("monte_carlo", self.retrieve_monte_carlo),
            RunStage.ROBUSTNESS: ("robustness", self.retrieve_robustness),
        }
        run = self._service.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")
        stage_method = methods.get(run.stage)
        if stage_method is None:
            return ValidationStageOutcome(
                stage=run.stage.value,
                status="not_run",
                reasons=(),
                protected_data_state=None,
                evidence_identity=None,
                artifact_id=None,
                eligible_to_progress=False,
            )
        stage, retrieve = stage_method
        try:
            record = retrieve(run_id, artifact_root=artifact_root)
        except (RuntimeError, ValueError) as exc:
            return ValidationStageOutcome(
                stage=stage,
                status=_missing_evidence_status(str(exc)),
                reasons=(str(exc),),
                protected_data_state=None,
                evidence_identity=None,
                artifact_id=None,
                eligible_to_progress=False,
            )
        normalized = record.document["evidence"]["normalized_evidence"]
        return ValidationStageOutcome(
            stage=stage,
            status=normalized["status"],
            reasons=tuple(normalized.get("reasons", ())),
            protected_data_state=normalized.get("protected_data_state"),
            evidence_identity=record.evidence_identity,
            artifact_id=record.artifact.artifact_id,
            eligible_to_progress=bool(normalized.get("eligible_to_progress")),
        )

    def evaluate_lockbox_prerequisites(
        self,
        *,
        walk_forward_run_id: str,
        monte_carlo_run_id: str,
        robustness_run_id: str,
        source_lock: Any,
        artifact_root: str | Path,
        protected_data_state: object = "gated",
    ) -> Any:
        """Evaluate prerequisite evidence for protected lockbox execution."""
        from backtesting.validation.lockbox_gate import (
            LockboxGateResult,
            evaluate_lockbox_prerequisites,
            lockbox_gate_identity,
        )

        retrieval_failures: list[tuple[str, str, str]] = []

        def retrieve(stage: str, run_id: str, method: str) -> Any | None:
            try:
                return getattr(self, method)(run_id, artifact_root=artifact_root)
            except (RuntimeError, ValueError) as exc:
                message = str(exc)
                status = _missing_evidence_status(message)
                retrieval_failures.append((stage, status, message))
                return None

        result = evaluate_lockbox_prerequisites(
            walk_forward=retrieve(
                "walk_forward",
                walk_forward_run_id,
                "retrieve_walk_forward",
            ),
            monte_carlo=retrieve(
                "monte_carlo",
                monte_carlo_run_id,
                "retrieve_monte_carlo",
            ),
            robustness=retrieve(
                "robustness",
                robustness_run_id,
                "retrieve_robustness",
            ),
            source_lock=source_lock,
            protected_data_state=protected_data_state,
        )
        if not retrieval_failures:
            return result
        statuses = [result.status, *(status for _, status, _ in retrieval_failures)]
        status = "invalid" if "invalid" in statuses else (
            "failed" if "failed" in statuses else "insufficient_evidence"
        )
        reasons = tuple(
            [*result.reasons]
            + [f"{stage}: {message}" for stage, _, message in retrieval_failures]
        )
        draft = LockboxGateResult(
            status=status,
            reasons=reasons,
            referenced_artifacts=result.referenced_artifacts,
            parameter_lock_identity=result.parameter_lock_identity,
            protected_data_state=result.protected_data_state,
            lineage_identity=result.lineage_identity,
            gate_identity="",
            eligible_to_execute_lockbox=False,
            eligible_to_progress=False,
        )
        return LockboxGateResult(
            status=draft.status,
            reasons=draft.reasons,
            referenced_artifacts=draft.referenced_artifacts,
            parameter_lock_identity=draft.parameter_lock_identity,
            protected_data_state=draft.protected_data_state,
            lineage_identity=draft.lineage_identity,
            gate_identity=lockbox_gate_identity(draft),
            eligible_to_execute_lockbox=False,
            eligible_to_progress=False,
        )

    def _review_context_target_state(self, target_run_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        target = self._service.runs.get(target_run_id)
        if target is None:
            raise KeyError(f"unknown run {target_run_id}")
        configuration = self._service.configurations.get(target.configuration_id)
        if configuration is None:
            raise RuntimeError(
                f"run {target_run_id} references missing configuration"
            )
        try:
            document = json.loads(configuration.canonical_config_json)
        except json.JSONDecodeError as exc:
            raise ValueError("target configuration JSON is corrupt") from exc
        if not isinstance(document, dict):
            raise ValueError("target configuration is not a JSON object")
        if (
            document.get("strategy_id") != target.strategy_id
            or document.get("strategy_version") != target.strategy_version
        ):
            raise ValueError("target strategy identity mismatches saved configuration")
        return target, document, self.source_document(target_run_id)

    def _source_compatibility_identity(self, source: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_id": source.get("strategy_id"),
            "strategy_version": source.get("strategy_version"),
            "configuration_hash": source.get("configuration_hash"),
            "data_identity": source.get("data_identity"),
            "execution_assumptions_identity": source.get(
                "execution_assumptions_identity"
            ),
        }

    @staticmethod
    def _effective_strategy_parameters(parameters: object) -> dict[str, Any]:
        """Return flat strategy parameters or the single supported fixture envelope."""
        if not isinstance(parameters, Mapping):
            raise ValueError("target configuration parameters are missing or malformed")
        keys = set(parameters)
        envelope_keys = {"fixture", "strategy_parameters"}
        if not keys.intersection(envelope_keys):
            return dict(parameters)
        if keys != envelope_keys:
            raise ValueError("target fixture parameter envelope is malformed or ambiguous")
        fixture = parameters.get("fixture")
        strategy_parameters = parameters.get("strategy_parameters")
        if not isinstance(fixture, str) or not fixture.strip():
            raise ValueError("target fixture parameter envelope is malformed or ambiguous")
        if not isinstance(strategy_parameters, Mapping) or not strategy_parameters:
            raise ValueError("target fixture strategy parameters are missing or malformed")
        return dict(strategy_parameters)

    def _retrieve_validated_source_lock(
        self,
        *,
        source_lock_run_id: str,
        source_lock_artifact_id: int,
        target_configuration: dict[str, Any],
        artifact_root: str | Path,
    ) -> Any:
        from backtesting.robustness import load_lock_artifact

        source_run = self._service.runs.get(source_lock_run_id)
        if source_run is None:
            raise KeyError(f"unknown run {source_lock_run_id}")
        artifact = self._service.get_artifact_metadata(source_lock_artifact_id)
        if artifact.run_id != source_lock_run_id:
            raise ValueError("source-lock artifact run mismatch")
        validation = self._service.validate_artifact(
            source_lock_artifact_id,
            artifact_root=artifact_root,
        )
        if not validation.valid or validation.resolved_path is None:
            raise ValueError(
                f"source-lock artifact is unavailable: {validation.reason}"
            )
        execution = target_configuration.get("execution")
        if not isinstance(execution, dict):
            raise ValueError("target configuration lacks execution assumptions")
        source_lock = load_lock_artifact(
            Path(validation.resolved_path),
            expected_experiment_id=str(target_configuration.get("experiment_id")),
            expected_strategy_id=str(target_configuration.get("strategy_id")),
            expected_strategy_version=str(target_configuration.get("strategy_version")),
            expected_execution=execution,
        )
        if source_lock.status != "passed":
            raise ValueError(
                "source-lock evidence is invalid: "
                + "; ".join(source_lock.reasons)
            )
        return source_lock

    def _validate_review_context_compatibility(
        self,
        *,
        target_run_id: str,
        source_lock: Any,
        walk_forward: Any,
        monte_carlo: Any,
        robustness: Any,
        target_configuration: dict[str, Any],
        target_source: dict[str, Any],
    ) -> None:
        parameters = self._effective_strategy_parameters(
            target_configuration.get("parameters")
        )
        if canonical_json(parameters) != canonical_json(source_lock.locked_parameters):
            raise ValueError("target parameter lock mismatch")
        if source_lock.strategy_id != target_source.get("strategy_id"):
            raise ValueError("target strategy identity mismatch")
        if source_lock.strategy_version != target_source.get("strategy_version"):
            raise ValueError("target strategy version mismatch")
        if source_lock.experiment_id != target_configuration.get("experiment_id"):
            raise ValueError("target experiment identity mismatch")
        target_identity = self._source_compatibility_identity(target_source)
        for stage, record in (
            ("walk_forward", walk_forward),
            ("monte_carlo", monte_carlo),
            ("robustness", robustness),
        ):
            source = record.document.get("source")
            if not isinstance(source, dict):
                raise ValueError(f"{stage} source lineage is missing")
            if self._source_compatibility_identity(source) != target_identity:
                raise ValueError(f"{stage} source lineage mismatch")
        _ = target_run_id

    def persist_review_context(
        self,
        *,
        target_run_id: str,
        source_lock_run_id: str,
        source_lock_artifact_id: int,
        walk_forward_run_id: str,
        monte_carlo_run_id: str,
        robustness_run_id: str,
        protected_data_state: object,
        artifact_root: str | Path,
        created_at: str | None = None,
    ) -> Any:
        """Persist explicit review context after service-owned gate validation."""
        from backtesting.validation.review_context_artifacts.persistence import (
            persist_review_context_artifact,
        )

        _, target_configuration, target_source = self._review_context_target_state(
            target_run_id
        )
        source_lock = self._retrieve_validated_source_lock(
            source_lock_run_id=source_lock_run_id,
            source_lock_artifact_id=source_lock_artifact_id,
            target_configuration=target_configuration,
            artifact_root=artifact_root,
        )
        walk_forward = self.retrieve_walk_forward(
            walk_forward_run_id,
            artifact_root=artifact_root,
        )
        monte_carlo = self.retrieve_monte_carlo(
            monte_carlo_run_id,
            artifact_root=artifact_root,
        )
        robustness = self.retrieve_robustness(
            robustness_run_id,
            artifact_root=artifact_root,
        )
        self._validate_review_context_compatibility(
            target_run_id=target_run_id,
            source_lock=source_lock,
            walk_forward=walk_forward,
            monte_carlo=monte_carlo,
            robustness=robustness,
            target_configuration=target_configuration,
            target_source=target_source,
        )
        gate = self.evaluate_lockbox_prerequisites(
            walk_forward_run_id=walk_forward_run_id,
            monte_carlo_run_id=monte_carlo_run_id,
            robustness_run_id=robustness_run_id,
            source_lock=source_lock,
            artifact_root=artifact_root,
            protected_data_state=protected_data_state,
        )
        if gate.status != "passed":
            raise ValueError(
                "; ".join(gate.reasons)
                or f"review context gate returned {gate.status}"
            )
        return persist_review_context_artifact(
            service=self._service,
            target_run_id=target_run_id,
            source_lock=source_lock,
            source_lock_run_id=source_lock_run_id,
            source_lock_artifact_id=source_lock_artifact_id,
            walk_forward_run_id=walk_forward_run_id,
            monte_carlo_run_id=monte_carlo_run_id,
            robustness_run_id=robustness_run_id,
            protected_data_state=str(protected_data_state),
            artifact_root=artifact_root,
            created_at=created_at,
        )

    def retrieve_review_context(
        self,
        target_run_id: str,
        *,
        artifact_root: str | Path,
    ) -> Any:
        """Retrieve the validated explicit review context for one target run."""
        from backtesting.validation.review_context_artifacts.persistence import (
            retrieve_review_context_artifact,
        )

        return retrieve_review_context_artifact(
            service=self._service,
            target_run_id=target_run_id,
            artifact_root=artifact_root,
        )

    def evaluate_persisted_review_context(
        self,
        target_run_id: str,
        *,
        artifact_root: str | Path,
    ) -> Any:
        """Evaluate the persisted review context through the lockbox gate service."""
        from backtesting.validation.review_context_artifacts.validator import (
            source_lock_from_document,
        )

        context = self.retrieve_review_context(
            target_run_id,
            artifact_root=artifact_root,
        )
        document = context.document
        _, target_configuration, target_source = self._review_context_target_state(
            target_run_id
        )
        source_lock = self._retrieve_validated_source_lock(
            source_lock_run_id=str(document["source_lock_run_id"]),
            source_lock_artifact_id=int(document["source_lock_artifact_id"]),
            target_configuration=target_configuration,
            artifact_root=artifact_root,
        )
        stored_source_lock = source_lock_from_document(document["source_lock"])
        from backtesting.validation.review_context_artifacts.builder import (
            source_lock_document,
        )

        if source_lock_document(source_lock) != source_lock_document(stored_source_lock):
            raise ValueError("review context source-lock artifact mismatch")
        walk_forward = self.retrieve_walk_forward(
            str(document["walk_forward_run_id"]),
            artifact_root=artifact_root,
        )
        monte_carlo = self.retrieve_monte_carlo(
            str(document["monte_carlo_run_id"]),
            artifact_root=artifact_root,
        )
        robustness = self.retrieve_robustness(
            str(document["robustness_run_id"]),
            artifact_root=artifact_root,
        )
        self._validate_review_context_compatibility(
            target_run_id=target_run_id,
            source_lock=source_lock,
            walk_forward=walk_forward,
            monte_carlo=monte_carlo,
            robustness=robustness,
            target_configuration=target_configuration,
            target_source=target_source,
        )
        gate = self.evaluate_lockbox_prerequisites(
            walk_forward_run_id=str(document["walk_forward_run_id"]),
            monte_carlo_run_id=str(document["monte_carlo_run_id"]),
            robustness_run_id=str(document["robustness_run_id"]),
            source_lock=source_lock,
            artifact_root=artifact_root,
            protected_data_state=document["protected_data_state"],
        )
        if gate.status != "passed":
            raise ValueError(
                "; ".join(gate.reasons)
                or f"review context gate returned {gate.status}"
            )
        return gate

    def persist_evidence_decision(
        self,
        *,
        run_id: str,
        gate_result: Any,
        review_state: ReviewState,
        review_reason: str,
        reviewer: str = "local-user",
        artifact_root: str | Path,
        created_at: str | None = None,
    ) -> Any:
        """Persist a compact human evidence-decision record for one run."""
        from backtesting.validation.evidence_decision_artifacts import (
            EVIDENCE_DECISION_LOGICAL_NAME,
            persist_evidence_decision_artifact,
        )
        from persistence import ArtifactType

        source = self.source_document(run_id)
        existing = tuple(
            artifact
            for artifact in self._service.list_run_artifacts(run_id)
            if artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
            and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
        )
        if len(existing) > 1:
            raise ValueError("multiple evidence decision artifacts are registered")
        if existing:
            retrieved = self.retrieve_evidence_decision(
                run_id,
                artifact_root=artifact_root,
                expected_gate=gate_result,
            )
            review = retrieved.document["decision"]["review"]
            if (
                review.get("state") == ReviewState(review_state).value
                and review.get("reviewer") == reviewer
                and review.get("reason") == review_reason
            ):
                return retrieved
            raise ValueError("conflicting evidence decision artifact already exists")

        review = self._service.update_review(
            target_type="run",
            target_id=run_id,
            state=review_state,
            note=review_reason,
            operator=reviewer,
        )
        history = self._service.reviews.history("run", run_id)
        audit_reference = history[-1] if history else None
        return persist_evidence_decision_artifact(
            service=self._service,
            run_id=run_id,
            source=source,
            gate_result=gate_result,
            review=review,
            audit_reference=audit_reference,
            artifact_root=artifact_root,
            created_at=created_at,
        )

    def retrieve_evidence_decision(
        self,
        run_id: str,
        *,
        artifact_root: str | Path,
        expected_gate: Any | None = None,
    ) -> Any:
        """Retrieve a validated evidence-decision record for one run."""
        from backtesting.validation.evidence_decision_artifacts import (
            retrieve_evidence_decision_artifact,
        )

        return retrieve_evidence_decision_artifact(
            service=self._service,
            run_id=run_id,
            artifact_root=artifact_root,
            expected_source=self.source_document(run_id),
            expected_gate=expected_gate,
        )

    def _require_stage(
        self,
        run_id: str,
        *,
        expected: RunStage,
        evidence_name: str,
    ) -> None:
        run = self._service.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")
        if run.stage != expected:
            raise ValueError(
                f"{evidence_name} cannot be persisted for {run.stage.value} runs"
            )
