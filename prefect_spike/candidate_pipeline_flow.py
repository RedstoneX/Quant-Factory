"""Prefect execution boundary for the generic candidate research pipeline."""

from __future__ import annotations

from prefect import flow
from prefect.context import FlowRunContext

from orchestration.candidate_pipeline_runtime import CandidatePipelineRuntime
from orchestration.filter_chain import FilterChainOutcome
from persistence.models import ResearchRunSubmissionRecord


@flow(name="quant-factory-candidate-pipeline", log_prints=True)
def run_candidate_pipeline_flow(
    *,
    runtime: CandidatePipelineRuntime,
    submission: ResearchRunSubmissionRecord,
) -> FilterChainOutcome:
    """Bind the actual Prefect identity before executing candidate work."""
    context = FlowRunContext.get()
    if context is None or context.flow_run is None:
        raise RuntimeError("candidate pipeline requires an active Prefect flow run")
    return runtime.execute_flow(
        submission=submission,
        prefect_flow_run_id=str(context.flow_run.id),
    )
