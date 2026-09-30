"""Structured project status for trader-facing dashboard copy."""

from dataclasses import dataclass

@dataclass(frozen=True)
class DashboardProjectStatus:
    current_milestone_number: int
    current_milestone_title: str
    current_milestone_status: str
    strategy_status: str
    workspace_status: str
    home_subtitle: str

PROJECT_STATUS = DashboardProjectStatus(
    current_milestone_number=23,
    current_milestone_title="Operator Product Completion",
    current_milestone_status=(
        "The Research Atlas overview is accepted. The connected operator interface "
        "is still being completed before handoff."
    ),
    strategy_status=(
        "No candidate research is active. The MES overnight-gap reversal is rejected "
        "and may not be tuned or rerun."
    ),
    workspace_status=(
        "R12 remains active until Terry can operate and accept the complete dashboard "
        "workflow. Strategy testing resumes only after that handoff."
    ),
    home_subtitle="Your strategy research workspace.",
)
