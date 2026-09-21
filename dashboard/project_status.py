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
        "Factory mechanics and essential dashboard pages are complete for this bounded "
        "Step 11 path; Terry's Step 12 direction review is next. Real saved "
        "filter-result connection, full workflow proof, final acceptance, and beta "
        "remain in Steps 13–16."
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
