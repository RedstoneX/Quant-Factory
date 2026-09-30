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
    current_milestone_title="Research Product Completion and Handoff",
    current_milestone_status=(
        "The backend and audited MES run are complete. Dashboard and operator-workflow "
        "completion are now active for Terry's final handoff."
    ),
    strategy_status=(
        "No new strategy selection, screening, optimization, or performance evaluation occurs "
        "before handoff. Product verification uses deterministic fixtures and accepted evidence."
    ),
    workspace_status=(
        "Complete the existing single-user workflow and prepare the final operator walkthrough. "
        "Paid data, external deployment, paper execution, and live trading remain deferred."
    ),
    home_subtitle="Your strategy research workspace.",
)
