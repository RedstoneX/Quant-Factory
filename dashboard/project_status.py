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
    current_milestone_title="Intraday Edge Discovery and Validation",
    current_milestone_status=(
        "Backend edge discovery is active. The reusable screening, out-of-sample, "
        "walk-forward, robustness, Monte Carlo, persistence, and filter-handoff "
        "infrastructure is retained rather than rebuilt."
    ),
    strategy_status=(
        "The next research step is one genuinely new, bounded short-duration "
        "S&P/Nasdaq directional hypothesis using existing validated data where sufficient."
    ),
    workspace_status=(
        "Historical dashboard evidence is retained, but the owner does not consider the "
        "current interface sufficiently intuitive for long-term operation. Non-blocking UI "
        "repair, deployment, paper execution, and live trading are deferred behind the "
        "current research phase and their later gates."
    ),
    home_subtitle="Find and validate a defensible trading edge.",
)
