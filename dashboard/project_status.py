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
    current_milestone_title="Research Backend Completion",
    current_milestone_status=(
        "Backend completion is active. Existing screening, out-of-sample, walk-forward, "
        "robustness, Monte Carlo, persistence, durable launch, and filter-chain services "
        "are being connected into one generic runtime path before new strategy research."
    ),
    strategy_status=(
        "New candidate selection is deferred until the backend can carry an approved "
        "candidate through the existing validation pipeline without test-only adapters "
        "or manual stage assembly."
    ),
    workspace_status=(
        "The current dashboard is not accepted as the long-term operator interface. "
        "Non-blocking UI repair, deployment, paper execution, and live trading remain deferred."
    ),
    home_subtitle="Complete the research backend, then find and validate an edge.",
)
