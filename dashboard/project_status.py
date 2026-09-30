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
    current_milestone_title="Research Product Completion and Handoff",
    current_milestone_status=(
        "The objective research workflow has passed its technical gate and is ready "
        "for Terry's final walkthrough. Handoff acceptance is not yet recorded."
    ),
    strategy_status=(
        "No new strategy selection, screening, optimization, or performance evaluation occurs "
        "before handoff. Product verification uses deterministic fixtures and accepted evidence."
    ),
    workspace_status=(
        "The remaining R12 gate is Terry's walkthrough and explicit handoff acceptance. "
        "Private deployment, new research, paid data, paper execution, and live trading remain unauthorized."
    ),
    home_subtitle="Your strategy research workspace.",
)
