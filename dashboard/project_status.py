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
    current_milestone_title="End-to-End Equity Research Factory Acceptance",
    current_milestone_status=(
        "Factory mechanics, essential dashboard pages, real saved-result connections, "
        "and the complete passive browser workflow are complete through Step 14. "
        "Terry accepted the corrected Step 15 dashboard workflow; bounded beta use is "
        "active at Step 16."
    ),
    strategy_status=(
        "New candidate and edge research remain paused during beta; use saved results "
        "to find and correct demonstrated workflow defects first."
    ),
    workspace_status=(
        "Protected-data inspection, promotion, deployment, paper execution, and live "
        "trading remain blocked; their later authority and evidence gates still apply. "
        "The selected-run workflow is owner-accepted on the private review service, not "
        "production-deployed and not a claim of a trading edge."
    ),
    home_subtitle="Your strategy research workspace.",
)
