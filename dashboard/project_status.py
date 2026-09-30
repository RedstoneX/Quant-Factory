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
    current_milestone_title="Intraday Edge Discovery and Candidate Selection",
    current_milestone_status=(
        "Backend completion is recorded. The fixed 09:35–10:00 MES overnight-gap reversal "
        "development screen completed and the candidate was rejected."
    ),
    strategy_status=(
        "The MES candidate screened out on negative return and Sharpe below 0.5. R11 is "
        "at the owner gate for the next fixed intraday candidate; SPY turn-of-month remains "
        "out of scope for the current day-trading mandate."
    ),
    workspace_status=(
        "The current dashboard is not accepted as the long-term operator interface. "
        "Non-blocking UI repair, deployment, paper execution, and live trading remain deferred."
    ),
    home_subtitle="Find and validate a same-session intraday trading edge.",
)
