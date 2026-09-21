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
    ResearchLaunchRequest,
    new_dispatcher_instance_id,
)
from persistence.models import ResearchLaunchOperation, ResearchRunSubmissionRecord


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
    ) -> CandidateScreeningLaunchResult:
        """Claim and dispatch one explicit candidate screening invocation once."""

        claim = self._claims.claim(
            idempotency_key=idempotency_key,
            request=ResearchLaunchRequest(
                operation=ResearchLaunchOperation.RUN_TEST,
                configuration_id=configuration_id,
            ),
            environment=environment,
        )
        dispatch = self._claims.dispatch(
            idempotency_key=idempotency_key,
            dispatcher_instance_id=self._dispatcher_instance_id,
            invoke=lambda submission: self._screening_adapter(submission, self._claims),
        )
        return CandidateScreeningLaunchResult(claim=claim, dispatch=dispatch)
