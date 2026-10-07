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
    current_milestone_title="Operator Product Completion",
    current_milestone_status=(
        "The connected Candidate workflow and intraday metric-basis correction are deployed; "
        "Results performance is the active correction before the owner walkthrough."
    ),
    strategy_status=(
        "No generic candidate research is active. Both fixed MES workflow-proof Candidates "
        "screened out and may not be tuned."
    ),
    workspace_status=(
        "R13 is complete. R12 is correcting the measured Results latency with the existing "
        "Dash and VectorBT stack before the owner walkthrough; the provider-neutral agent "
        "gateway remains operational."
    ),
    home_subtitle="Your strategy research workspace.",
)
