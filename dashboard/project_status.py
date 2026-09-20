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
        "Pending; the narrow Results correction is merged, while target and operator "
        "proof remain."
    ),
    strategy_status=(
        "Controlled research is active only for owner-approved, source-attributed "
        "hypotheses with predeclared evidence boundaries."
    ),
    workspace_status=(
        "Protected tests, promotion, paper execution, and live trading remain blocked. "
        "The selected-run R07 correction is merged but not deployed or operator-accepted."
    ),
    home_subtitle="Your strategy research workspace.",
)
