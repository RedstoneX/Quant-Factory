"""Page-owned callbacks for safe durable local idea drafts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dash import Dash, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from dashboard.routing import active_route
from dashboard.pages.ideas import _draft_options as _workbench_draft_options
from dashboard.pages.ideas import _readable_time
from dashboard.run_adapter import (
    delete_idea_draft,
    list_idea_drafts,
    save_idea_draft,
)


IDEAS_PATH = "/research/ideas"


def _valid_source_url(value: str) -> bool:
    if not value:
        return True
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


def _draft_values(
    title: str | None,
    description: str | None,
    source_url: str | None,
    attribution: str | None,
    notes: str | None,
) -> dict[str, str]:
    return {
        "title": (title or "").strip(),
        "description": (description or "").strip(),
        "source_url": (source_url or "").strip(),
        "attribution": (attribution or "").strip(),
        "notes": (notes or "").strip(),
    }


def _idea_draft_transition(
    triggered_id: str,
    values: dict[str, str],
    stored_draft: dict[str, str] | None,
    *,
    saved_at: str | None = None,
):
    """Return store/status/confirmation changes without retrieving source text."""

    stored = stored_draft or {}
    stored_values = {key: stored.get(key, "") for key in values}
    has_text = any(values.values())

    if triggered_id == "confirm-discard-idea-draft":
        return (
            {},
            "Draft discarded from local Quant Factory storage.",
            "save-message",
            False,
        )
    if triggered_id == "discard-idea-draft":
        if has_text or stored:
            return (
                no_update,
                "Discard not applied. Confirm before removing local changes.",
                "save-message unsaved-state",
                True,
            )
        return (
            no_update,
            "Empty draft — there is nothing to discard.",
            "save-message",
            False,
        )
    if triggered_id == "save-idea-draft":
        if not _valid_source_url(values["source_url"]):
            return (
                no_update,
                (
                    "Draft not saved. Enter a complete http:// or https:// source URL "
                    "without embedded credentials, or leave it blank. Your text is "
                    "unchanged."
                ),
                "save-message error-state",
                False,
            )
        if not values["title"]:
            return (
                no_update,
                "Draft not saved. Add a short operator-authored title. Your text is unchanged.",
                "save-message error-state",
                False,
            )
        timestamp = saved_at or datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        return (
            {**values, "saved_at": timestamp},
            f"Draft saved locally at {timestamp}. Nothing was retrieved or run.",
            "save-message save-message-success",
            False,
        )
    if values != stored_values:
        return (
            no_update,
            "Unsaved local changes — save the draft or confirm before discarding it.",
            "save-message unsaved-state",
            False,
        )
    stored_timestamp = stored.get("updated_at") or stored.get("saved_at")
    if stored_timestamp:
        return (
            no_update,
            f"Draft saved locally at {stored_timestamp}. Nothing was retrieved or run.",
            "save-message save-message-success",
            False,
        )
    return (
        no_update,
        "Empty draft — nothing is saved locally.",
        "save-message",
        False,
    )


def _draft_options(database: str | Path) -> list[dict[str, object]]:
    return _workbench_draft_options(list_idea_drafts(database))


def register_ideas_callbacks(
    app: Dash,
    *,
    database: str | Path,
) -> None:
    """Persist only operator-authored text in local Quant Factory storage."""

    @app.callback(
        Output("idea-draft-store", "data"),
        Output("idea-draft-status", "children"),
        Output("idea-draft-status", "className"),
        Output("confirm-discard-idea-draft", "displayed"),
        Output("idea-draft-selector", "options"),
        Output("idea-draft-selector", "value"),
        Output("continue-idea-to-setup", "href"),
        Output("continue-idea-to-setup", "className"),
        Input("save-idea-draft", "n_clicks"),
        Input("discard-idea-draft", "n_clicks"),
        Input("new-idea-draft", "n_clicks"),
        Input("confirm-discard-idea-draft", "submit_n_clicks"),
        Input("idea-draft-selector", "value"),
        Input("idea-title", "value"),
        Input("idea-description", "value"),
        Input("idea-source-url", "value"),
        Input("idea-attribution", "value"),
        Input("idea-notes", "value"),
        State("idea-draft-store", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_idea_draft(
        _save_clicks: int | None,
        _discard_clicks: int | None,
        _new_clicks: int | None,
        _confirm_clicks: int | None,
        selected_draft_id: str | None,
        title: str | None,
        description: str | None,
        source_url: str | None,
        attribution: str | None,
        notes: str | None,
        stored_draft: dict[str, str] | None,
        pathname: str | None,
    ):
        if not active_route(pathname, IDEAS_PATH):
            raise PreventUpdate
        triggered_id = str(ctx.triggered_id)
        if triggered_id == "idea-draft-selector":
            selected = next(
                (
                    draft
                    for draft in list_idea_drafts(database)
                    if draft.draft_id == selected_draft_id
                ),
                None,
            )
            if selected is None:
                return (
                    {},
                    "New draft — add a title before saving locally.",
                    "save-message",
                    False,
                    no_update,
                    None,
                    None,
                    "primary-action action-disabled",
                )
            return (
                selected.to_store(),
                f"Draft saved locally at {selected.updated_at}. Nothing was retrieved or run.",
                "save-message save-message-success",
                False,
                no_update,
                selected.draft_id,
                "/research/setup",
                "primary-action",
            )

        values = _draft_values(title, description, source_url, attribution, notes)
        if triggered_id == "new-idea-draft":
            stored = stored_draft or {}
            stored_values = {key: stored.get(key, "") for key in values}
            if values != stored_values:
                return (
                    no_update,
                    "Save or discard the current changes before starting a new idea.",
                    "save-message unsaved-state",
                    False,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                )
            return (
                {},
                "New draft — add a title and hypothesis before saving locally.",
                "save-message",
                False,
                no_update,
                None,
                None,
                "primary-action action-disabled",
            )
        transition = _idea_draft_transition(
            triggered_id,
            values,
            stored_draft,
        )
        store, message, class_name, confirm = transition
        if triggered_id == "save-idea-draft" and store is not no_update:
            try:
                saved = save_idea_draft(
                    values,
                    draft_id=(stored_draft or {}).get("draft_id"),
                    database=database,
                )
            except ValueError as exc:
                return (
                    no_update,
                    f"Draft not saved. {exc}",
                    "save-message error-state",
                    False,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                )
            return (
                saved.to_store(),
                f"Draft saved locally at {saved.updated_at}. Nothing was retrieved or run.",
                class_name,
                confirm,
                _draft_options(database),
                saved.draft_id,
                "/research/setup",
                "primary-action",
            )
        if triggered_id == "confirm-discard-idea-draft":
            draft_id = (stored_draft or {}).get("draft_id")
            if draft_id:
                try:
                    delete_idea_draft(draft_id, database=database)
                except ValueError as exc:
                    return (
                        no_update,
                        str(exc),
                        "save-message error-state",
                        False,
                        no_update,
                        no_update,
                        "/research/setup",
                        "primary-action",
                    )
            remaining = list_idea_drafts(database)
            selected = remaining[0] if remaining else None
            return (
                selected.to_store() if selected else {},
                message,
                class_name,
                confirm,
                _draft_options(database),
                selected.draft_id if selected else None,
                "/research/setup" if selected else None,
                "primary-action" if selected else "primary-action action-disabled",
            )
        stored_values = {
            key: (stored_draft or {}).get(key, "")
            for key in values
        }
        dirty = values != stored_values
        return (
            store,
            message,
            class_name,
            confirm,
            no_update,
            no_update,
            None if dirty else no_update,
            "primary-action action-disabled" if dirty else no_update,
        )

    @app.callback(
        Output("idea-workbench-title", "children"),
        Output("idea-workbench-state", "children"),
        Output("idea-workbench-state", "className"),
        Output("idea-workbench-meta", "children"),
        Output("idea-source-state", "children"),
        Output("idea-brief-hypothesis", "children"),
        Output("idea-brief-source", "children"),
        Output("idea-brief-questions", "children"),
        Output("idea-brief-setup", "children"),
        Output("idea-brief-state", "children"),
        Output("idea-brief-state", "className"),
        Output("idea-next-action-copy", "children"),
        Input("idea-title", "value"),
        Input("idea-description", "value"),
        Input("idea-source-url", "value"),
        Input("idea-attribution", "value"),
        Input("idea-notes", "value"),
        Input("idea-draft-store", "data"),
    )
    def update_workbench_brief(
        title: str | None,
        description: str | None,
        source_url: str | None,
        attribution: str | None,
        notes: str | None,
        stored_draft: dict[str, str] | None,
    ):
        values = _draft_values(title, description, source_url, attribution, notes)
        stored = stored_draft or {}
        stored_values = {key: stored.get(key, "") for key in values}
        dirty = values != stored_values
        saved = bool(stored.get("draft_id")) and not dirty

        if dirty:
            state = "Unsaved changes"
            state_class = "idea-state-badge idea-state-unsaved"
            meta = "Save to retain this version"
        elif saved:
            state = "Draft saved"
            state_class = "idea-state-badge idea-state-saved"
            updated = stored.get("updated_at") or stored.get("saved_at") or ""
            meta = f"Updated {_readable_time(updated)}" if updated else "Saved locally"
        else:
            state = "New draft"
            state_class = "idea-state-badge"
            meta = "Nothing runs until you deliberately continue"

        source_parts = [part for part in (values["attribution"], values["source_url"]) if part]
        formed = bool(values["title"] and values["description"])
        if formed:
            brief_state = "Draft formed"
            brief_class = "idea-brief-badge idea-brief-badge-ready"
        else:
            brief_state = "Needs your input"
            brief_class = "idea-brief-badge"

        if not formed:
            next_action = "Add a title and hypothesis, then save the draft."
        elif dirty or not stored.get("draft_id"):
            next_action = "Save this version before continuing."
        elif stored.get("configuration_id"):
            next_action = "Open Set up to review the saved bounded configuration."
        else:
            next_action = "Continue to Set up and choose an approved specification."

        return (
            values["title"] or "New research idea",
            state,
            state_class,
            meta,
            "Source linked" if values["source_url"] else "Owner-authored",
            values["description"] or "Describe the behavior you want to investigate.",
            " · ".join(source_parts) or "No source or owner observation recorded yet.",
            values["notes"] or "Record the uncertainties that must be resolved before testing.",
            "Bounded setup saved" if stored.get("configuration_id") else "Not prepared",
            brief_state,
            brief_class,
            next_action,
        )

    @app.callback(
        Output("idea-history-count", "children"),
        Output("idea-history-empty", "style"),
        Input("idea-draft-selector", "options"),
    )
    def update_history_state(options: list[dict[str, object]] | None):
        count = len(options or ())
        return str(count), ({"display": "none"} if count else {})

    @app.callback(
        Output("idea-title", "value"),
        Output("idea-description", "value"),
        Output("idea-source-url", "value"),
        Output("idea-attribution", "value"),
        Output("idea-notes", "value"),
        Input("idea-draft-store", "data"),
    )
    def show_idea_draft(draft: dict[str, str] | None):
        if draft is None:
            return (no_update,) * 5
        values = draft or {}
        return (
            values.get("title", ""),
            values.get("description", ""),
            values.get("source_url", ""),
            values.get("attribution", ""),
            values.get("notes", ""),
        )
