"""Owner decision and Setup-gate callbacks for saved Candidates."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from dash import Dash, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from dashboard.pages.ideas import _draft_options as _workbench_draft_options
from dashboard.routing import active_route
from dashboard.run_adapter import list_idea_drafts
from research_intake import CandidatePacketError, parse_candidate_packet, record_candidate_decision


IDEAS_PATH = "/research/ideas"


def draft_options(database: str | Path) -> list[dict[str, object]]:
    return _workbench_draft_options(list_idea_drafts(database))


def setup_link_state(
    draft: dict[str, Any] | None,
    *,
    dirty: bool = False,
) -> tuple[str | None, str]:
    value = draft or {}
    status = ""
    if value.get("candidate_json"):
        try:
            document = parse_candidate_packet(str(value["candidate_json"]), format_hint="json")
            candidate = document.get("candidate")
            status = str(candidate.get("status") or "") if isinstance(candidate, dict) else ""
        except CandidatePacketError:
            status = "invalid"
    allowed = bool(value.get("draft_id") and not dirty and status == "owner_approved")
    return (
        "/research/setup" if allowed else None,
        "primary-action" if allowed else "primary-action action-disabled",
    )


def register_candidate_decision_callback(
    app: Dash,
    *,
    database: str | Path,
) -> None:
    @app.callback(
        Output("idea-draft-store", "data", allow_duplicate=True),
        Output("idea-draft-selector", "options", allow_duplicate=True),
        Output("idea-draft-selector", "value", allow_duplicate=True),
        Output("candidate-action-status", "children", allow_duplicate=True),
        Output("candidate-action-status", "className", allow_duplicate=True),
        Output("continue-idea-to-setup", "href", allow_duplicate=True),
        Output("continue-idea-to-setup", "className", allow_duplicate=True),
        Input("accept-candidate-for-setup", "n_clicks"),
        Input("reject-candidate", "n_clicks"),
        State("idea-draft-store", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def decide_candidate(
        _accept_clicks: int | None,
        _reject_clicks: int | None,
        stored_draft: dict[str, Any] | None,
        pathname: str | None,
    ):
        if not active_route(pathname, IDEAS_PATH):
            raise PreventUpdate
        draft_id = str((stored_draft or {}).get("draft_id") or "")
        if not draft_id:
            raise PreventUpdate
        decision = "owner_approved" if str(ctx.triggered_id) == "accept-candidate-for-setup" else "rejected"
        try:
            decided = record_candidate_decision(
                draft_id=draft_id,
                decision=decision,
                database=database,
            )
        except CandidatePacketError as exc:
            return (
                no_update,
                no_update,
                no_update,
                f"Decision not recorded. {exc}.",
                "field-help error-state",
                no_update,
                no_update,
            )
        saved_store = asdict(decided.draft)
        setup_href, setup_class = setup_link_state(saved_store)
        message = (
            "Candidate accepted. Set up will show whether this exact version has an implementation."
            if decision == "owner_approved"
            else "Candidate rejected and retained in history so agents do not repeat it."
        )
        return (
            saved_store,
            draft_options(database),
            decided.draft.draft_id,
            message,
            "field-help save-message-success",
            setup_href,
            setup_class,
        )
