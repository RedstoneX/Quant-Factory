"""Stable execution contracts between candidate orchestration and adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestration.filter_chain import FilterChainOutcome
from persistence.models import ResearchRunSubmissionRecord


@runtime_checkable
class CandidatePipelineExecution(Protocol):
    """Candidate work an execution adapter may invoke after acquiring identity."""

    def execute_flow(
        self,
        *,
        submission: ResearchRunSubmissionRecord,
        prefect_flow_run_id: str,
    ) -> FilterChainOutcome: ...


class CandidatePipelineLauncher(Protocol):
    """Technical execution boundary supplied by an outer composition root."""

    def __call__(
        self,
        *,
        runtime: CandidatePipelineExecution,
        submission: ResearchRunSubmissionRecord,
    ) -> FilterChainOutcome: ...
