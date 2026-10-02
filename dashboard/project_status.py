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
        "the corrected Setup page is deployed for the connected owner walkthrough."
    ),
    strategy_status=(
        "No candidate research is active. The MES overnight-gap reversal is rejected "
        "and may not be tuned or rerun."
    ),
    workspace_status=(
        "R13 is complete and R12 awaits owner review. The separately authorized "
        "agent gateway is operational locally; its real Grok connection awaits "
        "the owner-controlled hosted public key and does not start strategy testing."
    ),
    home_subtitle="Your strategy research workspace.",
)
