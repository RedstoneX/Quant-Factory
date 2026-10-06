"""Focused non-browser contracts for approved Setup and Run Test presentation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dash import dcc, html

from dashboard.candidate_workflow import CandidateConfigurationBinding, CandidateIdentityView
from dashboard.pages import run_test, setup
from dashboard.run_adapter import ConfigurationField, ConfigurationReadinessView, SavedConfigurationView


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _text(component: Any) -> str:
    values: list[str] = []
    for item in _walk(component):
        children = getattr(item, "children", None)
        if isinstance(children, str):
            values.append(children)
    return " ".join(values)


def _by_id(component: Any, component_id: str):
    return next(item for item in _walk(component) if getattr(item, "id", None) == component_id)


def _identity() -> CandidateIdentityView:
    return CandidateIdentityView(
        candidate_id="idea-1",
        version_fingerprint="a" * 64,
        title="Quiet overnight follow-through",
        family="daytime_momentum",
        status="owner_approved",
        attribution="Owner import",
        rationale="A quiet overnight range may precede a directional first move.",
        fixed_definition="One fixed entry and same-session exit.",
        evidence_contract="Enough trades, positive return, steady results.",
    )


def _configuration() -> SavedConfigurationView:
    return SavedConfigurationView(
        configuration_id="b" * 64,
        experiment_id="candidate-v1",
        strategy_id="candidate_strategy",
        strategy_version="1.0.0",
        strategy_name="Quiet overnight follow-through",
        lifecycle="candidate",
        active=True,
        parameters={"window": 15},
        execution={"fees": 0.0005},
        market_data={"instrument": "MES"},
        config_hash="c" * 64,
        document={"validation_runtime": {"entrypoint": "fixture"}},
    )


def _readiness(configuration: SavedConfigurationView) -> ConfigurationReadinessView:
    return ConfigurationReadinessView(
        configuration_id=configuration.configuration_id,
        experiment_id=configuration.experiment_id,
        strategy_name=configuration.strategy_name,
        strategy_identity="candidate_strategy@1.0.0",
        lifecycle="candidate",
        config_hash=configuration.config_hash,
        provider="Local",
        dataset="MES one-minute",
        instrument="MES",
        timeframe="1m",
        requested_coverage="2025-01-01 → 2025-02-01",
        actual_coverage="2025-01-01 → 2025-02-01",
        local_availability="Available",
        local_validation="Verified",
        parameters=(ConfigurationField("Window", "15"),),
        execution_assumptions=(ConfigurationField("Fees", "0.05%"),),
        blockers=(),
        state="ready",
    )


def _patch_binding(monkeypatch, module, binding, configurations=()):
    monkeypatch.setattr(module, "candidate_configuration_binding", lambda *_args, **_kwargs: binding)


def test_setup_blocked_state_uses_approved_hierarchy_without_fabricating_readiness(monkeypatch) -> None:
    draft = SimpleNamespace(draft_id="idea-1", title="Quiet overnight follow-through", attribution="Owner import")
    binding = CandidateConfigurationBinding(draft, _identity(), None, "implementation_required", "Exact implementation required.")
    _patch_binding(monkeypatch, setup, binding)

    page = setup.render_selected_setup("idea-1", database=Path("unused.sqlite3"))
    text = _text(page)

    assert "Define the experiment" in text
    assert "Fixed-rule preview" in text
    assert "Implementation required" in text
    assert "Idea queue" not in text
    assert "How the rule fits in one trading day" not in text
    assert _by_id(page, "save-idea-configuration").disabled is True
    assert "setup-approved-identity" in str(page)
    assert "setup-ref-workspace" in str(page)
    assert _by_id(page, "configuration-selector").disabled is True
    assert _by_id(page, "review-test-action").href == "/research/ideas"
    assert _by_id(page, "review-test-action").children == "Review accepted Candidate"
    assert _by_id(page, "save-idea-configuration").disabled is True


def test_run_test_blocked_state_is_compact_truthful_and_non_launchable(monkeypatch) -> None:
    draft = SimpleNamespace(draft_id="idea-1", title="Quiet overnight follow-through", attribution="Owner import")
    binding = CandidateConfigurationBinding(draft, _identity(), None, "implementation_required", "Exact implementation required.")
    monkeypatch.setattr(run_test, "candidate_configuration_binding", lambda *_args, **_kwargs: binding)

    page = run_test.layout(database=Path("unused.sqlite3"))
    text = _text(page)

    assert "Review before running" in text
    assert text.count("Run status") == 1
    assert text.count("Evidence outcome") == 1
    assert text.count("Human decision") == 1
    assert text.count("Next safe action") == 1
    assert "What test is this?" not in text
    assert "What needs you?" not in text
    assert "Immutable run contract" in text
    assert "Implementation needed" in text
    assert "Preflight" in text
    assert "Exact implementation required." in text
    assert _by_id(page, "confirm-run-test").options[0]["disabled"] is True
    assert _by_id(page, "launch-run").disabled is True
    assert "run-callback-controls" in str(page)


def test_run_test_uses_only_exact_browser_selection_and_requires_confirmation(monkeypatch) -> None:
    configuration = _configuration()
    draft = SimpleNamespace(draft_id="idea-1", title="Quiet overnight follow-through", attribution="Owner import")
    binding = CandidateConfigurationBinding(draft, _identity(), configuration, None, None)
    monkeypatch.setattr(run_test, "candidate_configuration_binding", lambda draft_id, **_kwargs: binding if draft_id == "idea-1" else CandidateConfigurationBinding(None, None, None, "candidate_missing", "Selected Candidate missing."))
    monkeypatch.setattr(run_test, "configuration_readiness", lambda selected, _catalog: _readiness(selected))

    selected = run_test.render_selected_run_test("idea-1", configuration.configuration_id, database=Path("unused.sqlite3"))
    selected_text = _text(selected)
    assert "MES · 1m" in selected_text
    assert "Window: 15" in selected_text
    assert "Review and run test" in selected_text
    assert next(item for item in _walk(selected) if isinstance(item, html.Select)).disabled is True
    assert _by_id(selected, "launch-run").disabled is True
    assert _by_id(selected, "confirm-run-test").options[0]["disabled"] is False

    mismatch = run_test.render_selected_run_test("idea-1", "other-configuration", database=Path("unused.sqlite3"))
    mismatch_text = _text(mismatch)
    assert "selected saved setup does not match this Candidate" in mismatch_text
    assert "MES · 1m" not in mismatch_text
    assert "Window: 15" not in mismatch_text

    missing = run_test.render_selected_run_test("other-idea", configuration.configuration_id, database=Path("unused.sqlite3"))
    assert "MES · 1m" not in _text(missing)
    assert _by_id(missing, "launch-run").disabled is True


def test_ready_states_keep_real_controls_and_launch_confirmation(monkeypatch) -> None:
    draft = SimpleNamespace(draft_id="idea-1", title="Quiet overnight follow-through", attribution="Owner import")
    configuration = _configuration()
    readiness = _readiness(configuration)
    binding = CandidateConfigurationBinding(draft, _identity(), configuration, None, None)
    _patch_binding(monkeypatch, setup, binding, (configuration,))
    _patch_binding(monkeypatch, run_test, binding, (configuration,))

    monkeypatch.setattr(setup, "candidate_setup_definition", lambda _identity: SimpleNamespace(experiment=SimpleNamespace(strategy_id="mes_15m_orb_vwap_quality_candidate")))
    monkeypatch.setattr(setup, "_implementation_ready", lambda _configuration: True)
    setup_page = setup.render_selected_setup("idea-1", database=Path("unused.sqlite3"), readiness_by_id={configuration.configuration_id: readiness})
    monkeypatch.setattr(run_test, "configuration_readiness", lambda _configuration, _catalog: readiness)
    run_page = run_test.render_selected_run_test("idea-1", configuration.configuration_id, database=Path("unused.sqlite3"))

    assert _by_id(setup_page, "configuration-selector").value == configuration.configuration_id
    assert _by_id(setup_page, "review-test-action").href == "/research/run-test"
    assert "Continue to Run test" in _text(setup_page)
    assert "Ready for final review" in _text(run_page)
    assert "MES · 1m" in _text(run_page)
    assert "Window: 15" in _text(run_page)
    assert _by_id(run_page, "confirm-run-test").options[0]["disabled"] is False
    assert _by_id(run_page, "launch-run").children == "Run test"
    assert _by_id(run_page, "launch-run").disabled is True
