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
        "The Dashboard and Candidates reconstruction is owner-approved for implementation. "
        "Research remains paused while the first production slice is built and reviewed."
    ),
    strategy_status=(
        "No generic candidate research is active. Both fixed MES workflow-proof Candidates "
        "screened out and may not be tuned."
    ),
    workspace_status=(
        "R12 usability acceptance is open. No executable Candidate is active; the provider-neutral "
        "agent gateway remains operational but no research campaign is authorized."
    ),
    home_subtitle="Live Factory operations, survivors, and exceptions.",
)
