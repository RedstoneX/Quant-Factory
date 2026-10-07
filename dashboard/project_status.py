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
        "The connected Candidate workflow is deployed and owner-accepted for private-beta use. "
        "The next gate is acceptance of one bounded Candidate packet and evidence contract."
    ),
    strategy_status=(
        "No generic candidate research is active. Both fixed MES workflow-proof Candidates "
        "screened out and may not be tuned."
    ),
    workspace_status=(
        "R13 and R12 are complete. No executable Candidate is active; the provider-neutral "
        "agent gateway remains operational while the next bounded Candidate awaits owner acceptance."
    ),
    home_subtitle="Your strategy research workspace.",
)
