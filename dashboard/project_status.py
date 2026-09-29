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
    current_milestone_number=26,
    current_milestone_title="Edge Discovery and Candidate Selection",
    current_milestone_status=(
        "Backend completion is recorded. One fixed modern SPY turn-of-month development-screen "
        "proposal is predeclared and awaits explicit owner acceptance before execution."
    ),
    strategy_status=(
        "The turn-of-month hypothesis is proposed but untested. It has no result, no qualified "
        "edge status, and no authority to acquire data, run, or progress automatically."
    ),
    workspace_status=(
        "The current dashboard is not accepted as the long-term operator interface. "
        "Non-blocking UI repair, deployment, paper execution, and live trading remain deferred."
    ),
    home_subtitle="Find, reject, and rigorously validate one defensible edge.",
)
