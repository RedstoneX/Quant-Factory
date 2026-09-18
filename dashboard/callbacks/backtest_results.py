"""Mounted run-test and results callback ownership."""

from __future__ import annotations

import json
import hashlib
import re
from inspect import Parameter, signature
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from dash import Dash, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.components.operator_context import (
    OperatorContextViewModel,
    operator_context,
)
from dashboard.components.configuration_summary import configuration_summary
from dashboard.application import (
    _active_route,
    _backtest_selector_label,
    _callback_triggered_id,
    _configuration_is_launchable,
    _operator_message,
    _preferred_backtest_id,
    _recent_events_panel,
    _recent_runs_panel,
    _run_action_availability,
    _run_detail_panel,
    _results_operator_context,
    _selector_options,
)
from dashboard.run_adapter import ConfigurationReadinessView, SavedConfigurationView
from dashboard.callbacks.review_state import load_durable_review
from dashboard.run_detail_adapter import (
    ResultSummaryView,
    RunDetailDashboardAdapter,
    RunEvidenceView,
    SelectedRunDetailView,
)
from orchestration import (
    DurableResearchLaunchService,
    FixtureRunService,
    ResearchLaunchConflictError,
    ResearchLaunchContentionError,
    ResearchLaunchError,
    RunServiceError,
    RunSummary,
    new_research_launch_key,
)
from persistence import ResearchLaunchOperation, ResearchSubmissionState, canonical_json


OWNED_STATE = {
    "selected_backtest": ("selected-run-selector.value", "selected-run-state.data"),
    "run_test_launch": ("run-test-launch-state.data",),
    "historical_relaunch": ("historical-launch-state.data",),
    "reproduction_launch": ("reproduction-launch-state.data",),
}


_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_MAX_RESULTS_QUERY_LENGTH = 2_048
_MAX_RUN_ID_LENGTH = 256
_LAUNCH_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}")
# A NUL cannot occur in a syntactically valid Results run ID. Keeping the
# malformed-request state distinct from ``None`` prevents the mounted page
# from falling back to a previously selected, unrelated run while retaining a
# compact string contract for the shared session store.
_INVALID_REQUESTED_RUN_STATE = "\x00invalid-results-run-id"
_UNKNOWN_REQUESTED_RUN_PREFIX = "\x00unknown-results-run-id:"


def _unknown_requested_run_state(run_id: str) -> str:
    return f"{_UNKNOWN_REQUESTED_RUN_PREFIX}{run_id}"


def _unknown_requested_run_id(state: str | None) -> str | None:
    if not isinstance(state, str) or not state.startswith(
        _UNKNOWN_REQUESTED_RUN_PREFIX
    ):
        return None
    return state.removeprefix(_UNKNOWN_REQUESTED_RUN_PREFIX)


def _persisted_selected_run_id(state: str | None) -> str | None:
    """Return only identities that are safe to pass to persistence services."""

    if (
        not isinstance(state, str)
        or state == _INVALID_REQUESTED_RUN_STATE
        or _unknown_requested_run_id(state)
    ):
        return None
    return state


def _accepts_keywords(callable_object: Any, required: frozenset[str]) -> bool:
    """Return whether a service method implements the frozen durable seam."""

    try:
        parameters = signature(callable_object).parameters.values()
    except (TypeError, ValueError):
        return False
    parameters = tuple(parameters)
    if any(parameter.kind == Parameter.VAR_KEYWORD for parameter in parameters):
        return True
    return required.issubset({parameter.name for parameter in parameters})


def _durable_launch_supported(runs: FixtureRunService, operation: str) -> bool:
    method = (
        getattr(runs, "reproduce_fixture_run", None)
        if operation == ResearchLaunchOperation.REPRODUCTION.value
        else getattr(runs, "launch_fixture", None)
    )
    required = (
        frozenset({"idempotency_key"})
        if operation == ResearchLaunchOperation.REPRODUCTION.value
        else frozenset(
            {"idempotency_key", "operation", "source_run_id", "source_lineage"}
        )
    )
    return callable(method) and _accepts_keywords(method, required)


def _launch_intent(
    operation: str,
    configuration_id: str | None,
    source_run_id: str | None,
) -> dict[str, Any]:
    return {
        "idempotency_key": new_research_launch_key(),
        "operation": operation,
        "configuration_id": configuration_id,
        "source_run_id": source_run_id,
    }


def _valid_launch_key(value: object) -> bool:
    return isinstance(value, str) and _LAUNCH_KEY_PATTERN.fullmatch(value) is not None


def _intent_matches(
    intent: dict[str, Any],
    binding: tuple[str, str | None, str | None],
) -> bool:
    return (
        intent.get("operation"),
        intent.get("configuration_id"),
        intent.get("source_run_id"),
    ) == binding


def _launch_store(
    data: object,
    *,
    operation: str,
    configuration_id: str | None,
    source_run_id: str | None,
) -> tuple[dict[str, Any], str | None]:
    """Normalize one untrusted session store and rotate only unused intent."""

    raw = data if isinstance(data, dict) else {}
    prepared_raw = raw.get("prepared")
    submitted_raw = raw.get("submitted")
    binding = (operation, configuration_id, source_run_id)

    submitted = submitted_raw if isinstance(submitted_raw, dict) else None
    if submitted_raw is not None and submitted is None:
        return (
            {"prepared": None, "submitted": submitted_raw},
            "The saved submitted launch identity is malformed and cannot be trusted.",
        )
    if submitted is not None:
        if not _valid_launch_key(submitted.get("idempotency_key")):
            return (
                {"prepared": None, "submitted": submitted},
                "The saved submitted launch key is malformed and cannot be trusted.",
            )
        # A submitted identity is immutable evidence for its original request.
        # A later selection changes only the unused prepared identity; the
        # persisted submitted request is verified below but is not rebound to
        # (or allowed to block) the new selection.

    prepared = prepared_raw if isinstance(prepared_raw, dict) else None
    if prepared is None or not _valid_launch_key(prepared.get("idempotency_key")):
        prepared = _launch_intent(operation, configuration_id, source_run_id)
    elif not _intent_matches(prepared, binding):
        # Prepared identities are unused and may be rotated when the selection changes.
        prepared = _launch_intent(operation, configuration_id, source_run_id)
    return {"prepared": prepared, "submitted": submitted}, None


def _submission_for_intent(
    research_launches: DurableResearchLaunchService,
    intent: dict[str, Any] | None,
):
    if intent is None:
        return None
    key = intent.get("idempotency_key") if isinstance(intent, dict) else None
    if not _valid_launch_key(key):
        raise ResearchLaunchConflictError("saved research launch identity is malformed")
    try:
        submission = research_launches.get(key)
    except (ResearchLaunchError, ValueError) as exc:
        raise ResearchLaunchConflictError(
            "saved research launch identity could not be verified"
        ) from exc
    if submission is None:
        return None
    try:
        document = json.loads(submission.canonical_request_json)
    except (AttributeError, json.JSONDecodeError, TypeError) as exc:
        raise ResearchLaunchConflictError(
            "persisted research launch request could not be verified"
        ) from exc
    if (
        not isinstance(document, dict)
        or canonical_json(document) != submission.canonical_request_json
        or hashlib.sha256(submission.canonical_request_json.encode("utf-8")).hexdigest()
        != submission.request_fingerprint
        or document.get("configuration_id") != submission.configuration_id
    ):
        raise ResearchLaunchConflictError(
            "persisted research launch identity failed integrity validation"
        )
    expected = (
        intent.get("operation"),
        intent.get("configuration_id"),
        intent.get("source_run_id"),
    )
    actual = (
        document.get("operation_kind") if isinstance(document, dict) else None,
        document.get("configuration_id") if isinstance(document, dict) else None,
        document.get("source_run_id") if isinstance(document, dict) else None,
    )
    if actual != expected:
        raise ResearchLaunchConflictError(
            "research launch key is bound to a different operation or selection"
        )
    return submission


def _resolve_launch_store(
    research_launches: DurableResearchLaunchService,
    store: dict[str, Any],
    *,
    binding: tuple[str, str | None, str | None],
) -> tuple[dict[str, Any], Any, bool]:
    """Adopt a committed prepared key after lost response or another tab's claim."""

    submitted_intent = store.get("submitted")
    submitted = _submission_for_intent(research_launches, submitted_intent)
    if submitted is not None and _intent_matches(submitted_intent, binding):
        return store, submitted, False
    prepared_intent = store.get("prepared")
    prepared_submission = _submission_for_intent(research_launches, prepared_intent)
    if prepared_submission is None:
        return store, None, False
    store = {
        "submitted": prepared_intent,
        "prepared": _launch_intent(
            prepared_intent["operation"],
            prepared_intent.get("configuration_id"),
            prepared_intent.get("source_run_id"),
        ),
    }
    return store, prepared_submission, True


def _record_claimed_intent(
    store: dict[str, Any],
    intent: dict[str, Any],
) -> dict[str, Any]:
    """Move a durably claimed key to submitted and passively prepare its successor."""

    return {
        "submitted": intent,
        "prepared": _launch_intent(
            intent["operation"],
            intent.get("configuration_id"),
            intent.get("source_run_id"),
        ),
    }


def _run_for_submission(runs: FixtureRunService, submission: Any) -> RunSummary | None:
    if submission is None:
        return None
    try:
        return runs.get_run(submission.run_id)
    except (KeyError, ValueError, RunServiceError):
        return None


def _submission_is_terminal(submission: Any, run: RunSummary | None) -> bool:
    if submission is None:
        return False
    if submission.state in {
        ResearchSubmissionState.FAILED_BEFORE_SUBMISSION,
        ResearchSubmissionState.ABANDONED,
    }:
        return True
    return submission.state == ResearchSubmissionState.ACKNOWLEDGED and (
        run is not None and run.status in {"succeeded", "failed", "cancelled"}
    )


def _submission_heading(state: ResearchSubmissionState) -> str:
    return {
        ResearchSubmissionState.CLAIMED: "Starting test",
        ResearchSubmissionState.INVOKING: "Invoking fixture",
        ResearchSubmissionState.ACKNOWLEDGED: "Fixture acknowledged",
        ResearchSubmissionState.SUBMISSION_UNKNOWN: "Submission outcome unknown",
        ResearchSubmissionState.FAILED_BEFORE_SUBMISSION: "Submission did not start",
        ResearchSubmissionState.ABANDONED: "Unknown submission abandoned",
    }[state]


def _durable_launch_summary(submission: Any, run: RunSummary | None) -> html.Section:
    state = submission.state
    run_status = run.status if run is not None else "Created"
    details = [
        html.Li(f"Quant Factory run: {submission.run_id}"),
        html.Li(f"Submission: {state.value.replace('_', ' ').title()}"),
        html.Li(f"Run status: {run_status.replace('_', ' ').title()}"),
    ]
    if submission.prefect_flow_run_id:
        details.append(html.Li(f"Prefect flow run: {submission.prefect_flow_run_id}"))
    if submission.error_summary:
        details.append(html.Li(f"Details: {submission.error_summary}"))
    if state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
        details.append(
            html.Li(
                "Do not retry, cancel, or launch from this unresolved ticket. Reconciliation is required."
            )
        )
    return html.Section(
        [html.H3(_submission_heading(state)), html.Ul(details)],
        className=(
            "run-launch-status run-launch-status-error"
            if state
            in {
                ResearchSubmissionState.SUBMISSION_UNKNOWN,
                ResearchSubmissionState.FAILED_BEFORE_SUBMISSION,
                ResearchSubmissionState.ABANDONED,
            }
            else "run-launch-status"
        ),
        **{"data-run-id": submission.run_id},
    )


def _launch_button_state(
    *,
    supported: bool,
    allowed: bool,
    submission: Any,
    run: RunSummary | None,
    base_label: str,
) -> tuple[bool, str, str]:
    if submission is not None and submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
        return (
            True,
            "Submission outcome is unknown. Reconcile it before any retry, cancellation, or launch.",
            "Submission unknown",
        )
    if submission is not None and not _submission_is_terminal(submission, run):
        return True, "This durable submission is still active.", "Starting test..."
    if not supported:
        return (
            True,
            "Durable submission support is unavailable; the legacy launcher is disabled.",
            base_label,
        )
    if not allowed:
        return True, "This persisted selection is not launchable.", base_label
    if submission is None:
        return False, "Start one durable fixture submission.", base_label
    return False, "Start a new durable run ticket.", f"{base_label} again"


def _empty_run_context():
    context = operator_context(component_id="run-test-operator-context")
    return context.children, context.className


def _run_context(run: RunSummary | None, submission: Any):
    if run is None or submission is None:
        return _empty_run_context()
    status = run.status.replace("_", " ").title()
    if submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
        next_action = "Reconciliation required"
    elif run.status == "succeeded":
        next_action = "Inspect evidence"
    elif run.status in {"created", "queued", "running", "retrying"}:
        next_action = "Wait for completion"
    else:
        next_action = "Review failure"
    context = operator_context(
        OperatorContextViewModel(
            selected_run=True,
            run_status=status,
            evidence_outcome="Unavailable",
            human_decision="Unavailable",
            next_safe_action=next_action,
        ),
        component_id="run-test-operator-context",
    )
    return context.children, context.className


def _requested_results_run_id(search: str | None) -> tuple[bool, str | None]:
    """Return whether Results was asked to adopt one syntactically safe run ID."""

    if not search:
        return False, None
    query = search[1:] if search.startswith("?") else search
    if len(query) > _MAX_RESULTS_QUERY_LENGTH or _INVALID_PERCENT_ESCAPE.search(query):
        return True, None
    try:
        pairs = parse_qsl(
            query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=20,
        )
    except (UnicodeDecodeError, ValueError):
        return True, None
    values = [value for key, value in pairs if key == "run_id"]
    if not values:
        return False, None
    if len(values) != 1:
        return True, None
    run_id = values[0]
    if (
        not run_id.strip()
        or len(run_id) > _MAX_RUN_ID_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in run_id)
    ):
        return True, None
    return True, run_id


def _callback_triggered_ids() -> frozenset[str]:
    """Return every component that triggered the current Dash callback."""

    try:
        component_ids = {
            component_id
            for component_id in ctx.triggered_prop_ids.values()
            if isinstance(component_id, str)
        }
    except Exception:
        component_ids = set()
    primary = _callback_triggered_id()
    if primary:
        component_ids.add(primary)
    return frozenset(component_ids)


def register_backtest_results_callbacks(
    app: Dash,
    *,
    runs: FixtureRunService,
    detail_adapter: RunDetailDashboardAdapter,
    configurations: tuple[SavedConfigurationView, ...],
    readiness_by_id: dict[str, ConfigurationReadinessView],
    dashboard_database: str | Path,
    artifact_root: Path,
    research_launches: DurableResearchLaunchService,
) -> None:
    """Register Run test and Results callbacks within their page boundaries."""

    @app.callback(
        Output("run-configuration-preview", "children"),
        Input("selected-configuration-state", "data"),
    )
    def preview_configuration(configuration_id: str | None):
        readiness = readiness_by_id.get(configuration_id or "")
        summary = configuration_summary(
            readiness,
            component_id="run-configuration-preview-content",
        )
        if readiness is None:
            return summary.children
        return summary.children

    @app.callback(
        Output("run-test-launch-state", "data"),
        Output("launch-message", "children"),
        Output("launch-message", "className"),
        Output("run-test-operator-context", "children"),
        Output("run-test-operator-context", "className"),
        Output("launch-run", "disabled"),
        Output("launch-run", "title"),
        Output("launch-run", "children"),
        Input("launch-run", "n_clicks"),
        Input("selected-configuration-state", "data"),
        State("run-test-launch-state", "data"),
        State("url", "pathname"),
        running=[
            (Output("launch-run", "disabled"), True, True),
            (Output("launch-run", "children"), "Starting test...", "Run test"),
        ],
    )
    def launch_saved_configuration(
        n_clicks: int | None,
        configuration_id: str | None,
        launch_state: object = None,
        pathname: str | None = "/research/run-test",
    ):
        triggered_id = _callback_triggered_id()
        explicit_action = triggered_id == "launch-run" and bool(n_clicks)
        if triggered_id is None and n_clicks:
            # Unit-level direct invocation has no Dash callback context.
            explicit_action = True
        if explicit_action and not _active_route(pathname, "/research/run-test"):
            raise PreventUpdate
        selected = next(
            (
                configuration
                for configuration in configurations
                if configuration.configuration_id == configuration_id
            ),
            None,
        )
        readiness = readiness_by_id.get(selected.configuration_id) if selected else None
        allowed = selected is not None and readiness is not None and readiness.ready
        supported = _durable_launch_supported(runs, ResearchLaunchOperation.RUN_TEST.value)
        store, store_error = _launch_store(
            launch_state,
            operation=ResearchLaunchOperation.RUN_TEST.value,
            configuration_id=configuration_id,
            source_run_id=None,
        )
        submission = None
        adopted_prepared = False
        if store_error is None:
            try:
                store, submission, adopted_prepared = _resolve_launch_store(
                    research_launches,
                    store,
                    binding=(
                        ResearchLaunchOperation.RUN_TEST.value,
                        configuration_id,
                        None,
                    ),
                )
            except ResearchLaunchConflictError as exc:
                store_error = str(exc)
        run = _run_for_submission(runs, submission)
        launch_error: BaseException | None = None

        if (
            explicit_action
            and allowed
            and supported
            and store_error is None
            and not adopted_prepared
            and (submission is None or _submission_is_terminal(submission, run))
        ):
            intent = store.get("prepared")
            if not isinstance(intent, dict):
                store_error = "No valid prepared run ticket is available."
            else:
                try:
                    runs.launch_fixture(
                        configuration_id=selected.configuration_id,
                        idempotency_key=intent["idempotency_key"],
                        operation=ResearchLaunchOperation.RUN_TEST,
                        source_run_id=None,
                        source_lineage=None,
                    )
                except (
                    ResearchLaunchError,
                    KeyError,
                    ValueError,
                    RunServiceError,
                ) as exc:
                    launch_error = exc
                try:
                    claimed_submission = _submission_for_intent(research_launches, intent)
                except ResearchLaunchConflictError as exc:
                    store_error = str(exc)
                    claimed_submission = None
                if claimed_submission is not None:
                    store = _record_claimed_intent(store, intent)
                    submission = claimed_submission
                elif launch_error is None:
                    launch_error = ResearchLaunchError(
                        "The launcher returned without creating a durable claim."
                    )
                run = _run_for_submission(runs, submission)

        disabled, title, label = _launch_button_state(
            supported=supported,
            allowed=allowed and store_error is None,
            submission=submission,
            run=run,
            base_label="Run test",
        )
        if store_error is not None:
            message = _operator_message(
                "Run ticket conflict.", store_error, tone="error"
            )
            message_class = "save-message error-state"
            disabled = True
            title = store_error
            label = "Run ticket conflict"
        elif submission is not None:
            message = _durable_launch_summary(submission, run)
            message_class = (
                "save-message error-state"
                if submission.state
                in {
                    ResearchSubmissionState.SUBMISSION_UNKNOWN,
                    ResearchSubmissionState.FAILED_BEFORE_SUBMISSION,
                    ResearchSubmissionState.ABANDONED,
                }
                else "save-message"
            )
        elif launch_error is not None:
            message = _operator_message(
                "Run launch did not start.",
                f"{launch_error} You may retry this same request.",
                tone="warning" if isinstance(launch_error, ResearchLaunchContentionError) else "error",
            )
            message_class = (
                "save-message warning-state"
                if isinstance(launch_error, ResearchLaunchContentionError)
                else "save-message error-state"
            )
        elif selected is None:
            message = _operator_message(
                "Run launch unavailable.",
                "The selected saved configuration could not be found.",
                tone="error",
            )
            message_class = "save-message error-state"
        elif not allowed:
            message = _operator_message(
                "Run launch unavailable.",
                "The selected saved configuration did not pass preflight.",
                tone="error",
            )
            message_class = "save-message error-state"
        elif not supported:
            message = _operator_message(
                "Run launch unavailable.",
                "Durable submission support is not connected. The legacy launcher is disabled.",
                tone="warning",
            )
            message_class = "save-message warning-state"
        else:
            message = "Ready to create one durable run ticket."
            message_class = "save-message"
        context_children, context_class = _run_context(run, submission)
        return (
            store,
            message,
            message_class,
            context_children,
            context_class,
            disabled,
            title,
            label,
        )

    @app.callback(
        Output("historical-launch-state", "data"),
        Output("historical-launch-message", "children"),
        Output("historical-launch-message", "className"),
        Output("launch-selected-run-configuration", "disabled"),
        Output("launch-selected-run-configuration", "title"),
        Output("launch-selected-run-configuration", "children"),
        Input("launch-selected-run-configuration", "n_clicks"),
        Input("selected-run-state", "data"),
        State("historical-launch-state", "data"),
        State("url", "pathname"),
        running=[
            (Output("launch-selected-run-configuration", "disabled"), True, True),
            (
                Output("launch-selected-run-configuration", "children"),
                "Starting test...",
                "Launch new run from this configuration",
            ),
        ],
    )
    def launch_selected_run_configuration(
        n_clicks: int | None,
        run_id: str | None,
        launch_state: object = None,
        pathname: str | None = "/research/backtest-results",
    ):
        run_id = _persisted_selected_run_id(run_id)
        triggered_id = _callback_triggered_id()
        explicit_action = triggered_id == "launch-selected-run-configuration" and bool(n_clicks)
        if triggered_id is None and n_clicks:
            explicit_action = True
        if explicit_action and not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        try:
            selected_run = runs.get_run(run_id) if run_id else None
        except (KeyError, ValueError, RunServiceError):
            selected_run = None
        configuration_id = selected_run.configuration_id if selected_run else None
        allowed = selected_run is not None and _configuration_is_launchable(
            configuration_id or "", configurations
        )
        source_submission = (
            research_launches.get_for_run(run_id) if run_id else None
        )
        if source_submission is not None and source_submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
            allowed = False
        supported = _durable_launch_supported(
            runs, ResearchLaunchOperation.HISTORICAL_RELAUNCH.value
        )
        store, store_error = _launch_store(
            launch_state,
            operation=ResearchLaunchOperation.HISTORICAL_RELAUNCH.value,
            configuration_id=configuration_id,
            source_run_id=run_id,
        )
        submission = None
        adopted_prepared = False
        if store_error is None:
            try:
                store, submission, adopted_prepared = _resolve_launch_store(
                    research_launches,
                    store,
                    binding=(
                        ResearchLaunchOperation.HISTORICAL_RELAUNCH.value,
                        configuration_id,
                        run_id,
                    ),
                )
            except ResearchLaunchConflictError as exc:
                store_error = str(exc)
        launched_run = _run_for_submission(runs, submission)
        launch_error: BaseException | None = None
        if (
            explicit_action
            and allowed
            and supported
            and store_error is None
            and not adopted_prepared
            and (submission is None or _submission_is_terminal(submission, launched_run))
        ):
            intent = store.get("prepared")
            if not isinstance(intent, dict):
                store_error = "No valid prepared historical run ticket is available."
            else:
                try:
                    runs.launch_fixture(
                        configuration_id=configuration_id,
                        idempotency_key=intent["idempotency_key"],
                        operation=ResearchLaunchOperation.HISTORICAL_RELAUNCH,
                        source_run_id=run_id,
                        source_lineage=None,
                    )
                except (ResearchLaunchError, KeyError, ValueError, RunServiceError) as exc:
                    launch_error = exc
                try:
                    claimed_submission = _submission_for_intent(research_launches, intent)
                except ResearchLaunchConflictError as exc:
                    store_error = str(exc)
                    claimed_submission = None
                if claimed_submission is not None:
                    store = _record_claimed_intent(store, intent)
                    submission = claimed_submission
                elif launch_error is None:
                    launch_error = ResearchLaunchError(
                        "The launcher returned without creating a durable claim."
                    )
                launched_run = _run_for_submission(runs, submission)
        disabled, title, label = _launch_button_state(
            supported=supported,
            allowed=allowed and store_error is None,
            submission=submission,
            run=launched_run,
            base_label="Launch new run from this configuration",
        )
        if store_error is not None:
            message = _operator_message(
                "Historical run ticket conflict.", store_error, tone="error"
            )
            message_class = "historical-launch-message error-state"
            disabled = True
            title = store_error
            label = "Run ticket conflict"
        elif submission is not None:
            message = _durable_launch_summary(submission, launched_run)
            message_class = "historical-launch-message"
        elif launch_error is not None:
            message = _operator_message(
                "New run launch did not start.", str(launch_error), tone="error"
            )
            message_class = "historical-launch-message error-state"
        elif source_submission is not None and source_submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
            message = "This source run has an unknown submission outcome. Reconcile it before launching again."
            message_class = "historical-launch-message error-state"
        elif not supported:
            message = "Durable historical relaunch is unavailable; the legacy launcher is disabled."
            message_class = "historical-launch-message error-state"
        elif not allowed:
            message = "Select a launchable persisted run before creating a new run ticket."
            message_class = "historical-launch-message"
        else:
            message = "This creates a durable run ticket from the selected run's configuration."
            message_class = "historical-launch-message"
        return store, message, message_class, disabled, title, label

    @app.callback(
        Output("reproduction-launch-state", "data"),
        Output("reproduction-message", "children"),
        Output("reproduction-message", "className"),
        Output("reproduce-selected-run", "disabled"),
        Output("reproduce-selected-run", "title"),
        Output("reproduce-selected-run", "children"),
        Input("reproduce-selected-run", "n_clicks"),
        Input("selected-run-state", "data"),
        State("reproduction-launch-state", "data"),
        State("url", "pathname"),
        running=[
            (Output("reproduce-selected-run", "disabled"), True, True),
            (
                Output("reproduce-selected-run", "children"),
                "Starting test...",
                "Reproduce selected run",
            ),
        ],
    )
    def reproduce_selected_run(
        n_clicks: int | None,
        run_id: str | None,
        launch_state: object = None,
        pathname: str | None = "/research/backtest-results",
    ):
        run_id = _persisted_selected_run_id(run_id)
        triggered_id = _callback_triggered_id()
        explicit_action = triggered_id == "reproduce-selected-run" and bool(n_clicks)
        if triggered_id is None and n_clicks:
            explicit_action = True
        if explicit_action and not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        try:
            source_run = runs.get_run(run_id) if run_id else None
        except (KeyError, ValueError, RunServiceError):
            source_run = None
        configuration_id = source_run.configuration_id if source_run else None
        source_submission = research_launches.get_for_run(run_id) if run_id else None
        allowed = source_run is not None and source_run.status == "succeeded"
        if source_submission is not None and source_submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
            allowed = False
        supported = _durable_launch_supported(runs, ResearchLaunchOperation.REPRODUCTION.value)
        store, store_error = _launch_store(
            launch_state,
            operation=ResearchLaunchOperation.REPRODUCTION.value,
            configuration_id=configuration_id,
            source_run_id=run_id,
        )
        submission = None
        adopted_prepared = False
        if store_error is None:
            try:
                store, submission, adopted_prepared = _resolve_launch_store(
                    research_launches,
                    store,
                    binding=(
                        ResearchLaunchOperation.REPRODUCTION.value,
                        configuration_id,
                        run_id,
                    ),
                )
            except ResearchLaunchConflictError as exc:
                store_error = str(exc)
        reproduced_run = _run_for_submission(runs, submission)
        launch_error: BaseException | None = None
        if (
            explicit_action
            and allowed
            and supported
            and store_error is None
            and not adopted_prepared
            and (submission is None or _submission_is_terminal(submission, reproduced_run))
        ):
            intent = store.get("prepared")
            if not isinstance(intent, dict):
                store_error = "No valid prepared reproduction ticket is available."
            else:
                try:
                    runs.reproduce_fixture_run(
                        run_id,
                        artifact_root=artifact_root,
                        idempotency_key=intent["idempotency_key"],
                    )
                except (
                    ResearchLaunchError,
                    KeyError,
                    ValueError,
                    RuntimeError,
                    RunServiceError,
                ) as exc:
                    launch_error = exc
                try:
                    claimed_submission = _submission_for_intent(research_launches, intent)
                except ResearchLaunchConflictError as exc:
                    store_error = str(exc)
                    claimed_submission = None
                if claimed_submission is not None:
                    store = _record_claimed_intent(store, intent)
                    submission = claimed_submission
                elif launch_error is None:
                    launch_error = ResearchLaunchError(
                        "The launcher returned without creating a durable claim."
                    )
                reproduced_run = _run_for_submission(runs, submission)
        disabled, title, label = _launch_button_state(
            supported=supported,
            allowed=allowed and store_error is None,
            submission=submission,
            run=reproduced_run,
            base_label="Reproduce selected run",
        )
        if store_error is not None:
            message = f"Reproduction ticket conflict: {store_error}"
            message_class = "reproduction-message error-state"
            disabled = True
            title = store_error
            label = "Run ticket conflict"
        elif submission is not None:
            message = _durable_launch_summary(submission, reproduced_run)
            message_class = "reproduction-message"
        elif launch_error is not None:
            message = f"Run reproduction did not start: {launch_error}"
            message_class = "reproduction-message error-state"
        elif source_submission is not None and source_submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
            message = "This source run has an unknown submission outcome. Reconcile it before reproduction."
            message_class = "reproduction-message error-state"
        elif not supported:
            message = "Durable reproduction is unavailable; the legacy launcher is disabled."
            message_class = "reproduction-message error-state"
        elif not allowed:
            message = "Select a succeeded persisted run before requesting reproduction."
            message_class = "reproduction-message"
        else:
            message = "Reproduction creates one durable run ticket linked to the original."
            message_class = "reproduction-message"
        return store, message, message_class, disabled, title, label

    @app.callback(
        Output("selected-run-state", "data"),
        Input("selected-run-selector", "value"),
        Input("run-history-grid", "selectedRows", allow_optional=True),
        Input("url", "search"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
    )
    def preserve_selected_run(
        selected_run_id: str | None,
        history_rows: list[dict[str, Any]] | None = None,
        search: str | None = None,
        stored_run_id: str | None = None,
        pathname: str | None = "/research/backtest-results",
    ):
        triggered_ids = _callback_triggered_ids()
        triggered_id = _callback_triggered_id()

        def stored_run_is_valid() -> bool:
            persisted_run_id = _persisted_selected_run_id(stored_run_id)
            if not persisted_run_id:
                return False
            try:
                return runs.get_run(persisted_run_id) is not None
            except (KeyError, ValueError, RunServiceError):
                return False

        query_requested, requested_run_id = _requested_results_run_id(search)
        should_consider_query = triggered_id is None or "url" in triggered_ids
        results_route_is_active = _active_route(
            pathname,
            "/research/backtest-results",
        )
        if should_consider_query and not results_route_is_active:
            return no_update
        if should_consider_query and query_requested:
            if requested_run_id:
                try:
                    requested_run = runs.get_run(requested_run_id)
                except (KeyError, ValueError, RunServiceError):
                    requested_run = None
                if (
                    requested_run is not None
                    and requested_run.run_id == requested_run_id
                ):
                    return requested_run_id
                # Preserve the requested identity so every Results-owned
                # display can fail truthfully instead of retaining stale data.
                return _unknown_requested_run_state(requested_run_id)
            return _INVALID_REQUESTED_RUN_STATE
        if triggered_id == "run-history-grid" and history_rows:
            return history_rows[0].get("run_id") or stored_run_id
        if triggered_id == "selected-run-selector" and selected_run_id:
            return selected_run_id
        # On a full browser refresh Dash reports the mounted Location search
        # as the trigger while the selector still carries its layout default.
        # Keep the valid session selection until the store re-controls it.
        if triggered_id in {None, "url"} and stored_run_is_valid():
            return no_update
        if selected_run_id:
            return selected_run_id
        return no_update if stored_run_id else None

    @app.callback(
        Output("cancel-selected-run", "disabled"),
        Output("cancel-selected-run", "title"),
        Input("selected-run-state", "data"),
        Input("refresh-runs", "n_clicks"),
        Input("cancellation-message", "children"),
        Input("stale-recovery-message", "children"),
    )
    def update_selected_run_actions(
        run_id: str | None,
        _: int,
        __: int,
        ___: int,
    ):
        run_id = _persisted_selected_run_id(run_id)
        run = runs.get_run(run_id) if run_id else None
        availability = _run_action_availability(
            run,
            (
                run is not None
                and _configuration_is_launchable(
                    run.configuration_id,
                    configurations,
                )
            ),
        )
        if run is not None:
            submission = research_launches.get_for_run(run.run_id)
            if (
                submission is not None
                and submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
            ):
                return (
                    True,
                    "Submission outcome is unknown. Reconcile it before cancellation.",
                )
        return availability[4], availability[5]

    @app.callback(
        Output("recent-runs-monitor", "children"),
        Output("recent-events-monitor", "children"),
        Input("refresh-runs", "n_clicks"),
        Input("launch-message", "children"),
        Input("historical-launch-message", "children", allow_optional=True),
        Input("reproduction-message", "children", allow_optional=True),
        Input("cancellation-message", "children", allow_optional=True),
        Input("stale-recovery-message", "children"),
    )
    def refresh_run_monitor(
        _: int,
        __: int,
        ___: int,
        ____: int,
        _____: int,
        ______: int,
    ):
        recent_run_records = runs.recent_runs(limit=20)
        recent_event_records = runs.recent_events(limit=20)
        return (
            _recent_runs_panel(recent_run_records),
            _recent_events_panel(recent_event_records),
        )

    @app.callback(
        Output("run-history-grid", "rowData"),
        Input("refresh-runs", "n_clicks"),
        Input("launch-message", "children"),
        Input("historical-launch-message", "children", allow_optional=True),
        Input("reproduction-message", "children", allow_optional=True),
        Input("review-message", "children", allow_optional=True),
        Input("cancellation-message", "children", allow_optional=True),
        Input("stale-recovery-message", "children"),
    )
    def refresh_run_history(
        *_: object,
    ):
        if hasattr(runs, "all_history"):
            return list(runs.all_history(artifact_root=detail_adapter.artifact_root))
        return [
            {
                "run_id": run.run_id,
                "created_at": run.created_at,
                "instrument": "Not recorded",
                "strategy": f"{run.strategy_id} {run.strategy_version}",
                "stage": run.stage,
                "status": run.status,
                "review": "Not checked",
                "evidence": "Unverified",
                "metric_basis": "No persisted ranked result",
                "total_return": None,
                "annualized_return": None,
                "sharpe_ratio": None,
                "number_of_trades": None,
                "artifact_status": "Unverified",
                "reproducibility": "Unverified",
            }
            for run in runs.recent_runs(limit=20)
        ]

    @app.callback(
        Output("selected-run-selector", "options"),
        Output("selected-run-selector", "value"),
        Input("refresh-runs", "n_clicks"),
        Input("run-test-launch-state", "data"),
        Input("historical-launch-state", "data", allow_optional=True),
        Input("reproduction-launch-state", "data", allow_optional=True),
        Input("selected-run-state", "data"),
        State("selected-run-selector", "value"),
        State("selected-run-selector", "options"),
    )
    def refresh_run_selectors_after_launch(
        _refresh_clicks: int,
        run_test_launch_state: object,
        historical_launch_state: object,
        reproduction_launch_state: object,
        stored_run_id: str | None,
        selected_run_id: str | None,
        selected_options: list[dict[str, str]] | None,
    ):
        recent_run_records = runs.recent_runs(limit=20)
        recent_runs_by_id = {run.run_id: run for run in recent_run_records}
        triggered_id = _callback_triggered_id()
        triggered_ids = _callback_triggered_ids()

        looked_up_runs: dict[str, RunSummary | None] = {}

        def valid_run(run_id: str | None) -> RunSummary | None:
            if not run_id:
                return None
            if run_id in recent_runs_by_id:
                return recent_runs_by_id[run_id]
            if run_id not in looked_up_runs:
                try:
                    looked_up_runs[run_id] = runs.get_run(run_id)
                except (KeyError, ValueError, RunServiceError):
                    looked_up_runs[run_id] = None
            return looked_up_runs[run_id]

        selected_request_is_unknown = _unknown_requested_run_id(selected_run_id)
        stored_unknown_run_id = _unknown_requested_run_id(stored_run_id)
        selected_run = (
            None
            if selected_request_is_unknown
            or selected_run_id == _INVALID_REQUESTED_RUN_STATE
            else valid_run(selected_run_id)
        )
        stored_run = (
            None
            if stored_unknown_run_id
            or stored_run_id == _INVALID_REQUESTED_RUN_STATE
            else valid_run(stored_run_id)
        )
        stored_request_is_invalid = stored_run_id == _INVALID_REQUESTED_RUN_STATE
        stored_request_is_unknown = stored_unknown_run_id is not None
        completion_stores = {
            "run-test-launch-state": run_test_launch_state,
            "historical-launch-state": historical_launch_state,
            "reproduction-launch-state": reproduction_launch_state,
        }

        def store_run_id(data: object) -> str | None:
            if not isinstance(data, dict):
                return None
            for name in ("submitted", "prepared"):
                intent = data.get(name)
                if not isinstance(intent, dict):
                    continue
                try:
                    submission = _submission_for_intent(research_launches, intent)
                except ResearchLaunchConflictError:
                    continue
                if submission is not None:
                    return submission.run_id
            return None

        completed_run_id = (
            store_run_id(completion_stores[triggered_id])
            if triggered_id in completion_stores
            else None
        )
        completed_run = valid_run(completed_run_id)
        completed_run_id = completed_run.run_id if completed_run is not None else None
        stored_state_has_priority = (
            (triggered_id is None or "selected-run-state" in triggered_ids)
            and stored_run is not None
        )
        stable_selected_run_id = (
            stored_run_id
            if stored_state_has_priority
            else selected_run_id
            if selected_run is not None
            else stored_run_id
            if stored_run is not None
            else None
        )
        # Resolving chart evidence is only needed for initial selection. A
        # refresh with a valid operator selection must not reconstruct every
        # candidate portfolio before returning unchanged selector values.
        preferred_backtest_id = (
            _preferred_backtest_id(recent_run_records, detail_adapter)
            if stable_selected_run_id is None and completed_run_id is None
            else None
        )
        if completed_run_id is not None:
            selected_value = completed_run_id
        elif stored_request_is_invalid:
            selected_value = None
        elif stored_request_is_unknown:
            selected_value = stored_run_id
        elif stable_selected_run_id is not None:
            selected_value = stable_selected_run_id
        else:
            selected_value = preferred_backtest_id
        initial_selector_hydration = triggered_id is None and bool(selected_options)
        options = _selector_options(recent_run_records)
        option_values = {option["value"] for option in options}
        for run in (completed_run, selected_run, stored_run):
            if run is not None and run.run_id not in option_values:
                options.append(
                    {
                        "label": _backtest_selector_label(run),
                        "value": run.run_id,
                    }
                )
                option_values.add(run.run_id)
        if stored_request_is_unknown and stored_run_id not in option_values:
            options.append(
                {
                    "label": f"Requested run not found — {stored_unknown_run_id}",
                    "value": stored_run_id,
                    "disabled": True,
                }
            )
        selector_options: Any = (
            no_update
            if (initial_selector_hydration and not stored_state_has_priority)
            or options == (selected_options or [])
            else options
        )
        selector_value: Any = no_update if selected_value == selected_run_id else selected_value
        return selector_options, selector_value

    @app.callback(
        Output("selected-run-detail", "children"),
        Input("selected-run-state", "data"),
        Input("selected-run-selector", "value"),
        Input("refresh-runs", "n_clicks"),
        Input("launch-message", "children"),
        Input("cancellation-message", "children", allow_optional=True),
        Input("stale-recovery-message", "children"),
    )
    def inspect_run(
        stored_run_id: str | None,
        selected_run_id: str | None,
        _: int,
        __: int,
        ___: int,
        ____: int,
    ):
        run_id = stored_run_id or selected_run_id
        if not run_id:
            return _run_detail_panel(None)

        if run_id == _INVALID_REQUESTED_RUN_STATE:
            return html.Section(
                [
                    html.H2("Invalid Results link"),
                    html.P(
                        (
                            "The requested run identity is missing or malformed. "
                            "No previously selected run is being shown for this link."
                        ),
                        className="error-state",
                    ),
                ],
                className="panel run-detail-panel",
            )

        unknown_requested_run_id = _unknown_requested_run_id(run_id)
        if unknown_requested_run_id is not None:
            run_id = unknown_requested_run_id

        try:
            run = runs.get_run(run_id)
        except (KeyError, ValueError, RunServiceError):
            run = None
        if run is None:
            return html.Section(
                [
                    html.H2("Run not found"),
                    html.P(
                        (
                            "Requested run not found: no persisted run matches "
                            "the identity in this Results link."
                        ),
                        className="error-state",
                    ),
                    html.P(["Requested run: ", html.Code(run_id)]),
                    html.P(
                        "The Results route has been preserved and no other run is being shown in its place."
                    ),
                ],
                className="panel run-detail-panel",
            )

        detail_view: SelectedRunDetailView | None
        try:
            detail_view = detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            detail_view = SelectedRunDetailView(
                configuration_fields=(),
                parameters=(),
                market_data=(),
                execution=(),
                ranking=(),
                screening=(),
                lineage_fields=(),
                manifest_fields=(),
                artifacts=(),
                result_summary=ResultSummaryView(
                    status="empty",
                    message="No persisted result summary is available for this run.",
                    rows=(),
                ),
                evidence=RunEvidenceView(
                    notices=(),
                    metrics=(),
                    trades=(),
                    orders=(),
                    equity_curve=(),
                    drawdown_curve=(),
                    validation=(),
                    provenance=(),
                    warnings=(),
                ),
                warnings=(f"Run detail retrieval failed: {exc}",),
            )

        return _run_detail_panel(
            run,
            runs.events_for_run(run_id),
            detail=detail_view,
        )

    @app.callback(
        Output("results-operator-context", "children"),
        Output("results-operator-context", "className"),
        Input("selected-run-state", "data"),
        Input("refresh-runs", "n_clicks"),
        Input("review-message", "children"),
        Input("stale-recovery-message", "children"),
    )
    def update_results_operator_context(
        run_id: str | None,
        _refresh_clicks: int,
        _review_message: object,
        _stale_recovery_message: object = None,
    ):
        run_id = _persisted_selected_run_id(run_id)
        if not run_id:
            context = _results_operator_context(None)
            return context.children, context.className
        try:
            run = runs.get_run(run_id)
        except (KeyError, ValueError, RunServiceError):
            run = None
        if run is None:
            context = _results_operator_context(None)
            return context.children, context.className
        try:
            detail = detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, ValueError):
            detail = None
        try:
            review = load_durable_review(
                dashboard_database,
                artifact_root,
                run_id,
            )
            human_decision = review.display_state
        except (KeyError, RuntimeError, ValueError):
            human_decision = "Unavailable"
        context = _results_operator_context(
            run,
            detail,
            human_decision=human_decision,
        )
        return context.children, context.className

    @app.callback(
        Output("cancellation-message", "children"),
        Output("cancellation-message", "className"),
        Input("cancel-selected-run", "n_clicks"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def request_selected_run_cancellation(
        n_clicks: int | None,
        run_id: str | None,
        pathname: str | None = "/research/backtest-results",
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not n_clicks:
            return no_update, no_update
        run_id = _persisted_selected_run_id(run_id)
        if not run_id:
            return (
                "No run is selected for cancellation.",
                "cancellation-message error-state",
            )

        submission = research_launches.get_for_run(run_id)
        if (
            submission is not None
            and submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
        ):
            return (
                "Cancellation is disabled because the submission outcome is unknown. Reconciliation is required.",
                "cancellation-message error-state",
            )

        try:
            run = runs.request_fixture_cancellation(run_id)
        except (KeyError, ValueError, RunServiceError) as exc:
            return (
                f"Cancellation request failed: {exc}",
                "cancellation-message error-state",
            )

        if run.status == "running":
            return (
                (
                    "Cancellation requested. The run remains active while "
                    "waiting for fixture acknowledgement."
                ),
                "cancellation-message cancellation-message-pending",
            )

        return (
            (
                f"Run is already {run.status}; no cancellation request "
                "was applied."
            ),
            "cancellation-message",
        )

    @app.callback(
        Output("stale-recovery-message", "children"),
        Output("stale-recovery-message", "className"),
        Input("recover-stale-runs", "n_clicks"),
        State("stale-before-input", "value"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def recover_stale_runs(
        _: int,
        stale_before: str | None,
        pathname: str | None = "/research/backtest-results",
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        return (
            "Age-only recovery is disabled. A timestamp does not prove whether a durable submission started; use claim-aware reconciliation.",
            "stale-recovery-message error-state",
        )
