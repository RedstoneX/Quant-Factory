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
        "QF Candidate v1 standardized browser intake has a technical pass and is "
        "ready for the owner walkthrough; acceptance is still pending."
    ),
    strategy_status=(
        "No candidate research is active. The MES overnight-gap reversal is rejected "
        "and may not be tuned or rerun."
    ),
    workspace_status=(
        "R13 provides validated, non-executing Candidate intake. R12 remains active "
        "for the broader dashboard handoff; strategy testing stays paused."
    ),
    home_subtitle="Your strategy research workspace.",
)
