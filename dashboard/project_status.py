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
        "Terry's Step 15 final dashboard and workflow acceptance is next; beta remains "
        "Step 16."
    ),
    strategy_status=(
        "New candidate and edge research are paused until beta; deterministic factory "
        "mechanics and essential dashboard pages are complete for this bounded path."
    ),
    workspace_status=(
        "Protected-data inspection, promotion, deployment, paper execution, and live "
        "trading remain blocked; their later authority and evidence gates still apply. "
        "The selected-run R07 correction is merged but not deployed or operator-accepted."
    ),
    home_subtitle="Your strategy research workspace.",
)
