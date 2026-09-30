"""Explicit durable dispatch seam for one owner-approved candidate screening.

This service intentionally has no strategy implementation, market-data access,
or dashboard registration.  A caller must supply the bounded adapter that owns
the approved screening work and acknowledges the durable claim in that work.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from orchestration.research_launch_claims import (
    CANDIDATE_SCREENING_LAUNCH_CONTRACT,
    DurableResearchLaunchService,
    ResearchDispatchResult,
    ResearchLaunchClaim,
    ResearchLaunchError,
    ResearchLaunchRequest,
    new_dispatcher_instance_id,
)
from persistence import PersistenceService
from persistence.models import (
    ResearchLaunchOperation,
    ResearchRunSubmissionRecord,
    RunStage,
    RunStatus,
)


T = TypeVar("T")
CandidateScreeningAdapter = Callable[
    [ResearchRunSubmissionRecord, DurableResearchLaunchService],
    T,
]


@dataclass(frozen=True)
class CandidateScreeningLaunchResult:
    """One candidate screening claim and its at-most-once dispatch outcome."""

    claim: ResearchLaunchClaim
    dispatch: ResearchDispatchResult


class CandidateRunService:
    """Use the shared durable claim contract for an active candidate only.

    This is deliberately an adapter seam, not an automatic promotion path or
    evidence claim.  Its injected adapter must bind the durable claim before
    reporting any screening work as acknowledged.
    """

    def __init__(
        self,
        *,
        database: str | Path | None = None,
        screening_adapter: CandidateScreeningAdapter,
        dispatcher_instance_id: str | None = None,
        claim_service: DurableResearchLaunchService | None = None,
    ) -> None:
        if (
            claim_service is not None
            and claim_service.launch_contract != CANDIDATE_SCREENING_LAUNCH_CONTRACT
        ):
            raise ValueError("candidate service requires the candidate-screening claim contract")
        self._claims = claim_service or DurableResearchLaunchService(
            database=database,
            launch_contract=CANDIDATE_SCREENING_LAUNCH_CONTRACT,
        )
        self._screening_adapter = screening_adapter
        self._dispatcher_instance_id = dispatcher_instance_id or new_dispatcher_instance_id()

    def launch_screening(
        self,
        *,
        idempotency_key: str,
        configuration_id: str,
        environment: Mapping[str, Any] | None = None,
        operation: ResearchLaunchOperation = ResearchLaunchOperation.RUN_TEST,
        source_run_id: str | None = None,
        source_lineage: Mapping[str, str] | None = None,
    ) -> CandidateScreeningLaunchResult:
        """Claim and dispatch one explicit candidate screening invocation once."""

        try:
            normalized_operation = ResearchLaunchOperation(operation)
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported candidate launch operation") from exc
        if normalized_operation in {
            ResearchLaunchOperation.HISTORICAL_RELAUNCH,
            ResearchLaunchOperation.REPRODUCTION,
        }:
            self._validate_candidate_source_before_claim(source_run_id)

        claim = self._claims.claim(
            idempotency_key=idempotency_key,
            request=ResearchLaunchRequest(
                operation=normalized_operation,
                configuration_id=configuration_id,
                source_run_id=source_run_id,
                source_lineage=source_lineage,
            ),
            environment=environment,
        )
        dispatch = self._claims.dispatch(
            idempotency_key=idempotency_key,
            dispatcher_instance_id=self._dispatcher_instance_id,
            invoke=lambda submission: self._screening_adapter(submission, self._claims),
        )
        return CandidateScreeningLaunchResult(claim=claim, dispatch=dispatch)

    def _validate_candidate_source_before_claim(
        self,
        source_run_id: str | None,
    ) -> None:
        if source_run_id is None:
            return
        persistence = PersistenceService(self._claims.database_path)
        try:
            source = persistence.runs.get(source_run_id)
            if (
                source is None
                or source.stage != RunStage.SCREENING
                or source.status != RunStatus.SUCCEEDED
            ):
                return
            rows = persistence.results.list_parameter_results(source_run_id)
            statuses = {row.screening_status for row in rows}
            if (
                not rows
                or not statuses.issubset({"passed", "screened_out"})
                or "passed" not in statuses
            ):
                raise ResearchLaunchError(
                    "succeeded candidate screening sources require nonempty, valid "
                    "parameter results with at least one passing variant before "
                    "relaunch or reproduction"
                )
        finally:
            persistence.close()
