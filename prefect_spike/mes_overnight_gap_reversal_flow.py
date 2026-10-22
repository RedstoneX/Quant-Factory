"""Prefect boundary for the single R11 MES development screen."""

from __future__ import annotations

from prefect import flow
from prefect.context import FlowRunContext

from persistence.models import ResearchRunSubmissionRecord


@flow(name="quant-factory-mes-overnight-gap-reversal-screen", log_prints=True)
def run_mes_gap_screen_flow(*, runtime, submission: ResearchRunSubmissionRecord):
    """Bind the actual Prefect identity before candidate data or engine work."""
    context = FlowRunContext.get()
    if context is None or context.flow_run is None:
        raise RuntimeError("MES screen requires an active Prefect flow run")
    return runtime.execute_flow(
        submission=submission,
        prefect_flow_run_id=str(context.flow_run.id),
    )
