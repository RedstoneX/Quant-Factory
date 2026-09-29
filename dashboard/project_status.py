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
        "Backend completion is recorded. Current work is to select and bound one genuinely "
        "new short-duration S&P/Nasdaq hypothesis, then run only the cheapest sufficient "
        "first-stage discovery test."
    ),
    strategy_status=(
        "No candidate is currently qualified. Historical MES ORB, MSFT ORB, SPYM momentum, "
        "and SPY Donchian/RSI work do not substitute for a new predeclared hypothesis."
    ),
    workspace_status=(
        "The current dashboard is not accepted as the long-term operator interface. "
        "Non-blocking UI repair, deployment, paper execution, and live trading remain deferred."
    ),
    home_subtitle="Find, reject, and rigorously validate one defensible edge.",
)
