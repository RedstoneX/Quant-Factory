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
        "QF Candidate v1 standardized browser intake is owner-accepted and complete; "
        "the exact connected Candidate workflow is being corrected for a new owner walkthrough."
    ),
    strategy_status=(
        "No candidate research is active. The MES overnight-gap reversal is rejected "
        "and may not be tuned or rerun."
    ),
    workspace_status=(
        "R13 is complete and R12 exact-object correction is active. The provider-neutral "
        "agent gateway remains operational locally; bounded campaign preparation does "
        "not start strategy testing or bypass the first Candidate approval gate."
    ),
    home_subtitle="Your strategy research workspace.",
)
