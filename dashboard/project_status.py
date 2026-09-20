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
        "Pending; controlled research and the narrow Results correction are active."
    ),
    strategy_status=(
        "Controlled research is active only for owner-approved, source-attributed "
        "hypotheses with predeclared evidence boundaries."
    ),
    workspace_status=(
        "Protected tests, promotion, paper execution, and live trading remain blocked. "
        "Selected-run R07 inspection is corrected in this source revision."
    ),
    home_subtitle="Your strategy research workspace.",
)
