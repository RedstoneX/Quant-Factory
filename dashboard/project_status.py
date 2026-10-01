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
        "The connected operator workflow has a technical pass and is ready for "
        "the owner walkthrough; handoff acceptance is still pending."
    ),
    strategy_status=(
        "No candidate research is active. The MES overnight-gap reversal is rejected "
        "and may not be tuned or rerun."
    ),
    workspace_status=(
        "R12 remains active until Terry operates and accepts the complete dashboard "
        "workflow. Concrete walkthrough defects are repaired before strategy testing resumes."
    ),
    home_subtitle="Your strategy research workspace.",
)
