"""Page-owned callbacks for safe durable local idea drafts."""

from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.routing import active_route
from dashboard.callbacks.candidate_decision import (
    draft_options as _draft_options,
    register_candidate_decision_callback,
    setup_link_state as _setup_link_state,
)
from dashboard.components.candidate_brief import candidate_brief
from dashboard.candidate_workflow import (
    candidate_packet_status,
    idea_decision_presentation,
)
from dashboard.pages.ideas import _candidate_status
from dashboard.pages.ideas import _candidate_status_prompt
from dashboard.pages.ideas import _candidate_prompt
from dashboard.pages.ideas import _candidate_validation_data
from dashboard.pages.ideas import _readable_time
from dashboard.run_adapter import (
    delete_idea_draft,
    list_idea_drafts,
    save_idea_draft,
)
from research_intake import (
    CandidatePacketError,
    attach_candidate_to_idea,
    export_candidate_packet,
    export_research_context,
    import_candidate_as_idea,
    parse_candidate_packet,
    validate_candidate_packet,
)


IDEAS_PATH = "/research/ideas"
MAX_CANDIDATE_UPLOAD_BYTES = 100_000


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


def _decode_candidate_upload(contents: str | None, filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".yaml", ".yml", ".json"}:
        raise CandidatePacketError("choose a .yaml, .yml, or .json Candidate file")
    if not contents or "," not in contents:
        raise CandidatePacketError("the uploaded Candidate file could not be read")
    _, encoded = contents.split(",", 1)
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CandidatePacketError("the uploaded Candidate file is not valid base64") from exc
    if len(payload) > MAX_CANDIDATE_UPLOAD_BYTES:
        raise CandidatePacketError(
            f"Candidate file exceeds {MAX_CANDIDATE_UPLOAD_BYTES:,} bytes"
        )
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CandidatePacketError("Candidate files must be UTF-8 text") from exc


def _candidate_error(message: str) -> html.Div:
    return html.Div(
        [html.Strong("Candidate needs correction"), html.P(message)],
        className="candidate-validation candidate-validation-error",
    )


def _same_candidate(candidate_text: str, stored: dict[str, Any]) -> bool:
    stored_json = str(stored.get("candidate_json") or "")
    if not stored_json or not candidate_text.strip():
        return False
    try:
        candidate = validate_candidate_packet(parse_candidate_packet(candidate_text))
        persisted = validate_candidate_packet(
            parse_candidate_packet(stored_json, format_hint="json")
        )
    except ValueError:
        return False
    return candidate.canonical_json == persisted.canonical_json


def register_ideas_callbacks(app: Dash, *, database: str | Path) -> None:
    """Persist only operator-authored text in local Quant Factory storage."""

    register_candidate_decision_callback(app, database=database)

    @app.callback(
        Output("manual-idea-path", "className"),
        Output("assisted-idea-path", "className"),
        Output("idea-context-bar", "className"),
        Output("new-idea-draft", "className"),
        Output("idea-action-bar", "className"),
        Input("idea-start-path", "value"),
    )
    def show_idea_start_path(path: str | None):
        manual = path == "manual"
        assisted = path == "assisted"
        active = manual or assisted
        return (
            "idea-workbench-grid idea-path-panel"
            if manual
            else "idea-workbench-grid idea-path-panel idea-path-hidden",
            "idea-path-panel"
            if assisted
            else "idea-path-panel idea-path-hidden",
            "idea-context-bar" if active else "idea-context-bar idea-path-hidden",
            "secondary-action idea-new-draft-action",
            "idea-action-bar" if active else "idea-action-bar idea-path-hidden",
        )

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
            setup_href, setup_class = _setup_link_state(selected.to_store())
            return (
                selected.to_store(),
                f"Draft saved locally at {selected.updated_at}. Nothing was retrieved or run.",
                "save-message save-message-success",
                False,
                no_update,
                selected.draft_id,
                setup_href,
                setup_class,
            )

        values = _draft_values(title, description, source_url, attribution, notes)
        if triggered_id == "new-idea-draft":
            stored = stored_draft or {}
            stored_values = {key: stored.get(key, "") for key in values}
            # The editor may be intentionally blank while a saved Candidate is
            # selected in the review workspace. That is a safe new-draft action,
            # not an unsaved edit to the selected Candidate.
            if values != stored_values and any(values.values()):
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
            saved_store = saved.to_store()
            setup_href, setup_class = _setup_link_state(saved_store)
            return (
                saved_store,
                f"Draft saved locally at {saved.updated_at}. Nothing was retrieved or run.",
                class_name,
                confirm,
                _draft_options(database),
                saved.draft_id,
                setup_href,
                setup_class,
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
            selected_store = selected.to_store() if selected else {}
            setup_href, setup_class = _setup_link_state(selected_store)
            return (
                selected_store,
                message,
                class_name,
                confirm,
                _draft_options(database),
                selected.draft_id if selected else None,
                setup_href,
                setup_class,
            )
        stored_values = {
            key: (stored_draft or {}).get(key, "")
            for key in values
        }
        dirty = values != stored_values
        setup_href, setup_class = _setup_link_state(stored_draft, dirty=dirty)
        return (
            store,
            message,
            class_name,
            confirm,
            no_update,
            no_update,
            setup_href,
            setup_class,
        )

    @app.callback(
        Output("selected-idea-title", "children"),
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
        stored = stored_draft or {}
        if stored.get("draft_id") and all(
            value is None
            for value in (title, description, source_url, attribution, notes)
        ):
            values = {
                key: str(stored.get(key) or "")
                for key in ("title", "description", "source_url", "attribution", "notes")
            }
        else:
            values = _draft_values(title, description, source_url, attribution, notes)
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
        brief_state, brief_class, next_action = idea_decision_presentation(
            candidate_status=candidate_packet_status(stored.get("candidate_json")),
            formed=formed,
            dirty=dirty,
            has_draft=bool(stored.get("draft_id")),
            has_configuration=bool(stored.get("configuration_id")),
        )

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

    @app.callback(
        Output("candidate-packet-input", "value"),
        Output("candidate-upload-status", "children"),
        Output("candidate-upload-status", "className"),
        Output("candidate-editor-draft-id", "data"),
        Input("candidate-file-upload", "contents"),
        Input("idea-draft-store", "data"),
        State("candidate-file-upload", "filename"),
        State("candidate-packet-input", "value"),
        State("candidate-editor-draft-id", "data"),
        prevent_initial_call=True,
    )
    def load_candidate_editor(
        upload_contents: str | None,
        draft: dict[str, Any] | None,
        upload_filename: str | None,
        current_text: str | None,
        editor_draft_id: str | None,
    ):
        triggered_id = str(ctx.triggered_id)
        if triggered_id == "candidate-file-upload":
            try:
                uploaded = _decode_candidate_upload(upload_contents, upload_filename)
            except CandidatePacketError as exc:
                return (
                    no_update,
                    f"File not loaded. {exc}. Existing text is unchanged.",
                    "field-help error-state",
                    no_update,
                )
            return (
                uploaded,
                f"Loaded {upload_filename}. Validate before saving.",
                "field-help save-message-success",
                no_update,
            )

        stored = draft or {}
        next_draft_id = stored.get("draft_id")
        candidate_json = str(stored.get("candidate_json") or "")
        if next_draft_id == editor_draft_id:
            if candidate_json and not _same_candidate(current_text or "", stored):
                document = parse_candidate_packet(candidate_json, format_hint="json")
                return (
                    json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True),
                    "Loaded the Candidate saved on this idea.",
                    "field-help save-message-success",
                    next_draft_id,
                )
            return no_update, no_update, no_update, no_update
        if candidate_json:
            document = parse_candidate_packet(candidate_json, format_hint="json")
            return (
                json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True),
                "Loaded the Candidate saved on this idea.",
                "field-help save-message-success",
                next_draft_id,
            )
        return (
            "",
            "No Candidate is attached to this idea.",
            "field-help",
            next_draft_id,
        )

    @app.callback(
        Output("candidate-validation-store", "data"),
        Output("candidate-validation-status", "children"),
        Output("candidate-brief-content", "children"),
        Output("save-candidate-packet", "disabled"),
        Output("export-candidate-yaml", "disabled"),
        Output("export-candidate-json", "disabled"),
        Output("candidate-valid-actions", "className"),
        Output("candidate-brief-panel-v1", "className"),
        Input("validate-candidate-packet", "n_clicks"),
        Input("candidate-packet-input", "n_blur"),
        Input("idea-draft-store", "data"),
        State("candidate-packet-input", "value"),
        prevent_initial_call=True,
    )
    def validate_candidate_editor(
        _validate_clicks: int | None,
        _packet_blurs: int | None,
        draft: dict[str, Any] | None,
        candidate_text: str | None,
    ):
        triggered_id = str(ctx.triggered_id)
        text = (candidate_text or "").strip()
        stored = draft or {}
        if triggered_id == "idea-draft-store" and stored.get("candidate_json"):
            text = str(stored["candidate_json"])
        if not text:
            return (
                {},
                _candidate_status_prompt(),
                _candidate_prompt(),
                True,
                True,
                True,
                "candidate-valid-actions idea-path-hidden",
                "idea-workbench-panel candidate-brief-panel-v1 idea-path-hidden",
            )
        try:
            validation = validate_candidate_packet(parse_candidate_packet(text))
        except CandidatePacketError as exc:
            return (
                {},
                _candidate_error(str(exc)),
                _candidate_prompt(),
                True,
                True,
                True,
                "candidate-valid-actions idea-path-hidden",
                "idea-workbench-panel candidate-brief-panel-v1 idea-path-hidden",
            )
        enabled = validation.valid
        return (
            _candidate_validation_data(validation),
            _candidate_status(
                validation,
                saved=_same_candidate(text, stored),
            ),
            candidate_brief(validation.document, validation),
            not enabled,
            not enabled,
            not enabled,
            (
                "candidate-valid-actions"
                if enabled
                else "candidate-valid-actions idea-path-hidden"
            ),
            (
                "idea-workbench-panel candidate-brief-panel-v1"
                if enabled
                else "idea-workbench-panel candidate-brief-panel-v1 idea-path-hidden"
            ),
        )

    @app.callback(
        Output("idea-draft-store", "data", allow_duplicate=True),
        Output("idea-draft-selector", "options", allow_duplicate=True),
        Output("idea-draft-selector", "value", allow_duplicate=True),
        Output("candidate-action-status", "children"),
        Output("candidate-action-status", "className"),
        Output("continue-idea-to-setup", "href", allow_duplicate=True),
        Output("continue-idea-to-setup", "className", allow_duplicate=True),
        Input("save-candidate-packet", "n_clicks"),
        State("candidate-packet-input", "value"),
        State("idea-draft-store", "data"),
        State("idea-title", "value"),
        State("idea-description", "value"),
        State("idea-source-url", "value"),
        State("idea-attribution", "value"),
        State("idea-notes", "value"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def save_candidate_packet(
        _save_clicks: int | None,
        candidate_text: str | None,
        stored_draft: dict[str, Any] | None,
        title: str | None,
        description: str | None,
        source_url: str | None,
        attribution: str | None,
        notes: str | None,
        pathname: str | None,
    ):
        if not active_route(pathname, IDEAS_PATH):
            raise PreventUpdate
        text = (candidate_text or "").strip()
        if not text:
            return (
                no_update,
                no_update,
                no_update,
                "Candidate not saved. Paste or upload a packet first.",
                "field-help error-state",
                no_update,
                no_update,
            )
        stored = stored_draft or {}
        if stored.get("draft_id"):
            current_values = _draft_values(
                title, description, source_url, attribution, notes
            )
            stored_values = {key: stored.get(key, "") for key in current_values}
            if current_values != stored_values and any(current_values.values()):
                return (
                    no_update,
                    no_update,
                    no_update,
                    "Candidate not saved. Save or discard the ordinary draft changes first; nothing was lost.",
                    "field-help error-state",
                    no_update,
                    no_update,
                )
        try:
            if stored.get("draft_id"):
                imported = attach_candidate_to_idea(
                    text,
                    draft_id=str(stored["draft_id"]),
                    database=database,
                )
            else:
                imported = import_candidate_as_idea(text, database=database)
        except (CandidatePacketError, KeyError, ValueError) as exc:
            return (
                no_update,
                no_update,
                no_update,
                f"Candidate not saved. {exc}. Submitted content is unchanged.",
                "field-help error-state",
                no_update,
                no_update,
            )
        saved_store = asdict(imported.draft)
        setup_href, setup_class = _setup_link_state(saved_store)
        high_questions = sum(
            1
            for question in imported.validation.document.get("open_questions", []) or []
            if isinstance(question, dict)
            and str(question.get("importance", "")).lower() == "high"
        )
        unresolved = (
            f" {high_questions} high-importance question{'s remain' if high_questions != 1 else ' remains'} unresolved."
            if high_questions
            else ""
        )
        return (
            saved_store,
            _draft_options(database),
            imported.draft.draft_id,
            "Candidate saved durably on this idea. It is not approved, implemented, or runnable."
            + unresolved,
            "field-help save-message-success",
            setup_href,
            setup_class,
        )

    @app.callback(
        Output("candidate-download", "data"),
        Input("export-candidate-yaml", "n_clicks"),
        Input("export-candidate-json", "n_clicks"),
        State("candidate-validation-store", "data"),
        prevent_initial_call=True,
    )
    def download_candidate_packet(
        _yaml_clicks: int | None,
        _json_clicks: int | None,
        validation_data: dict[str, Any] | None,
    ):
        data = validation_data or {}
        document = data.get("document")
        if not data.get("valid") or not isinstance(document, dict):
            raise PreventUpdate
        format_name = "json" if str(ctx.triggered_id) == "export-candidate-json" else "yaml"
        rendered = export_candidate_packet(document, format=format_name)
        candidate = document.get("candidate") if isinstance(document.get("candidate"), dict) else {}
        title = str(candidate.get("title") or "qf-candidate")
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
        filename = f"{slug or 'qf-candidate'}.{format_name}"
        return dcc.send_string(rendered, filename)


    @app.callback(
        Output("research-context-download", "data"),
        Input("export-research-context-yaml", "n_clicks"),
        Input("export-research-context-json", "n_clicks"),
        prevent_initial_call=True,
    )
    def download_research_context(
        _yaml_clicks: int | None,
        _json_clicks: int | None,
    ):
        format_name = (
            "json"
            if str(ctx.triggered_id) == "export-research-context-json"
            else "yaml"
        )
        rendered = export_research_context(format=format_name)
        return dcc.send_string(
            rendered,
            f"qf-research-context-v1.{format_name}",
        )
