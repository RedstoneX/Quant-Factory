"""Page-owned callbacks for safe browser-session idea drafts."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from dash import Dash, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from dashboard.routing import active_route


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
            None,
            "Draft discarded from this browser session.",
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
                "Draft not saved. Enter a complete http:// or https:// source URL without embedded credentials, or leave it blank. Your text is unchanged.",
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
            f"Draft saved in this browser session at {timestamp}. Nothing was retrieved or run.",
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
    if stored.get("saved_at"):
        return (
            no_update,
            f"Draft saved in this browser session at {stored['saved_at']}. Nothing was retrieved or run.",
            "save-message save-message-success",
            False,
        )
    return (
        no_update,
        "Empty draft — nothing is saved in this browser session.",
        "save-message",
        False,
    )


def register_ideas_callbacks(app: Dash) -> None:
    """Persist only operator-authored text in the browser session."""

    @app.callback(
        Output("idea-draft-store", "data"),
        Output("idea-draft-status", "children"),
        Output("idea-draft-status", "className"),
        Output("confirm-discard-idea-draft", "displayed"),
        Input("save-idea-draft", "n_clicks"),
        Input("discard-idea-draft", "n_clicks"),
        Input("confirm-discard-idea-draft", "submit_n_clicks"),
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
        _confirm_clicks: int | None,
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
        return _idea_draft_transition(
            str(ctx.triggered_id),
            _draft_values(title, description, source_url, attribution, notes),
            stored_draft,
        )

    @app.callback(
        Output("idea-title", "value"),
        Output("idea-description", "value"),
        Output("idea-source-url", "value"),
        Output("idea-attribution", "value"),
        Output("idea-notes", "value"),
        Input("idea-draft-store", "data"),
    )
    def show_idea_draft(draft: dict[str, str] | None):
        values = draft or {}
        return (
            values.get("title", ""),
            values.get("description", ""),
            values.get("source_url", ""),
            values.get("attribution", ""),
            values.get("notes", ""),
        )
