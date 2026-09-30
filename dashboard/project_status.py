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
    current_milestone_number=25,
    current_milestone_title="Controlled Candidate Research",
    current_milestone_status=(
        "The operator product and deployed Research Atlas are accepted. The next "
        "candidate waits for Terry to name or explicitly approve its hypothesis."
    ),
    strategy_status=(
        "No candidate is active. The MES overnight-gap reversal is rejected and may "
        "not be tuned or rerun; the current research mandate remains same-session intraday."
    ),
    workspace_status=(
        "R12 and the handoff gate are complete. Candidate execution, paid data, "
        "protected testing, paper operation, and live trading require their applicable owner gates."
    ),
    home_subtitle="Your strategy research workspace.",
)
