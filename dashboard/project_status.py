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
    current_milestone_status="Pending - hard discovery gate",
    strategy_status="Research only until Milestone 23 is accepted.",
    workspace_status="Research workspace only; no paper or live trading is active.",
    home_subtitle="Your strategy research workspace.",
)
