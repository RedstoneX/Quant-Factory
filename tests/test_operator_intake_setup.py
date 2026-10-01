from __future__ import annotations

from dataclasses import asdict
import base64
import json
import sqlite3

import pytest

from dashboard.app import create_app
from dashboard.callbacks.setup import _parameter_controls
from dashboard.callbacks.ideas import _decode_candidate_upload
from dashboard.pages.ideas import layout as ideas_layout
from dashboard.run_adapter import (
    IdeaDraftView,
    list_setup_strategies,
    persist_bounded_idea_configuration,
    save_idea_draft,
)
from persistence import LATEST_SCHEMA_VERSION, PersistenceService, StrategyLifecycle
from strategies.spym_rsi_mean_reversion_fixture import (
    SPYM_RSI_ENTRY_THRESHOLD,
    SPYM_RSI_EXIT_THRESHOLD,
    SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC,
    SPYM_RSI_WINDOW,
)


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float)):
        yield from _walk(children)


def _register_fixture(path) -> None:
    spec = SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC
    service = PersistenceService(path)
    try:
        service.register_strategy(
            strategy_id=spec.identity.strategy_id,
            strategy_version=spec.identity.version,
            display_name=spec.identity.name,
            description=spec.identity.description,
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
            active=True,
        )
    finally:
        service.close()


def _callback(app, output_fragment: str):
    entry = next(
        value for key, value in app.callback_map.items() if output_fragment in key
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def test_v5_database_migrates_idea_drafts_once(tmp_path) -> None:
    path = tmp_path / "operator.sqlite3"
    service = PersistenceService(path)
    service.close()
    connection = sqlite3.connect(path)
    connection.execute("DROP INDEX idx_idea_drafts_updated")
    connection.execute("DROP TABLE idea_drafts")
    connection.execute(
        "UPDATE schema_metadata SET schema_version=5, "
        "migration_id='005_durable_research_launch_claims'"
    )
    connection.commit()
    connection.close()

    migrated = PersistenceService(path)
    try:
        version = migrated.connection.execute(
            "SELECT schema_version FROM schema_metadata"
        ).fetchone()["schema_version"]
        assert version == LATEST_SCHEMA_VERSION == 7
        assert migrated.idea_drafts.list() == ()
    finally:
        migrated.close()


def test_idea_draft_is_durable_and_linked_setup_cannot_be_discarded(tmp_path) -> None:
    path = tmp_path / "operator.sqlite3"
    _register_fixture(path)
    saved = save_idea_draft(
        {
            "title": "Owner observation",
            "description": "Capture only",
            "source_url": "https://example.com/source",
            "attribution": "Owner",
            "notes": "Question remains open",
        },
        database=path,
    )

    restarted = PersistenceService(path)
    try:
        assert restarted.idea_drafts.get(saved.draft_id).title == "Owner observation"
    finally:
        restarted.close()

    configuration_id = persist_bounded_idea_configuration(
        draft_id=saved.draft_id,
        strategy_identity="spym_rsi_mean_reversion_fixture@1.0.0",
        parameters={
            "window": SPYM_RSI_WINDOW,
            "entry_threshold": SPYM_RSI_ENTRY_THRESHOLD,
            "exit_threshold": SPYM_RSI_EXIT_THRESHOLD,
        },
        database=path,
    )
    service = PersistenceService(path)
    try:
        draft = service.idea_drafts.get(saved.draft_id)
        assert draft.configuration_id == configuration_id
        configuration = service.configurations.get(configuration_id)
        document = json.loads(configuration.canonical_config_json)
        assert document["parameters"] == {
            "entry_threshold": SPYM_RSI_ENTRY_THRESHOLD,
            "exit_threshold": SPYM_RSI_EXIT_THRESHOLD,
            "window": SPYM_RSI_WINDOW,
        }
        assert document["market_data"] == {
            "kind": "strategy_specification_requirements",
            "requirements": json.loads(
                json.dumps(asdict(SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC.data))
            ),
        }
        assert document["execution"] == asdict(
            SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC.assumptions
        )
        assert document["ranking"] == {}
        assert document["screening"] == {}
        with pytest.raises(ValueError, match="cannot be discarded"):
            service.delete_idea_draft(saved.draft_id)
    finally:
        service.close()


def test_setup_rejects_values_outside_approved_specification(tmp_path) -> None:
    path = tmp_path / "operator.sqlite3"
    _register_fixture(path)
    draft = save_idea_draft({"title": "Bounded"}, database=path)
    strategies = list_setup_strategies(path)
    assert [strategy.identity for strategy in strategies] == [
        "spym_rsi_mean_reversion_fixture@1.0.0"
    ]
    controls = _parameter_controls(strategies[0].identity, strategies)
    dropdown_values = [
        child.options[0]["value"]
        for child in controls
        if getattr(child, "id", None)
    ]
    assert dropdown_values == [
        SPYM_RSI_WINDOW,
        SPYM_RSI_ENTRY_THRESHOLD,
        SPYM_RSI_EXIT_THRESHOLD,
    ]

    with pytest.raises(ValueError, match="pre-approved allowed value"):
        persist_bounded_idea_configuration(
            draft_id=draft.draft_id,
            strategy_identity=strategies[0].identity,
            parameters={
                "window": 999,
                "entry_threshold": SPYM_RSI_ENTRY_THRESHOLD,
                "exit_threshold": SPYM_RSI_EXIT_THRESHOLD,
            },
            database=path,
        )
    service = PersistenceService(path)
    try:
        assert service.configurations.list() == ()
        assert service.idea_drafts.get(draft.draft_id).configuration_id is None
    finally:
        service.close()


def test_ideas_layout_hydrates_latest_durable_draft_without_source_fetch() -> None:
    draft = IdeaDraftView(
        draft_id="idea_12345678",
        title="Saved locally",
        description="",
        source_url="https://example.com/text-only",
        attribution="Owner",
        notes="",
        configuration_id=None,
        created_at="2026-09-30T00:00:00Z",
        updated_at="2026-09-30T00:01:00Z",
    )
    page = ideas_layout(drafts=(draft,))
    store = next(
        child
        for child in page.children
        if getattr(child, "id", None) == "idea-draft-store"
    )
    assert store.data["draft_id"] == draft.draft_id
    assert store.data["source_url"] == "https://example.com/text-only"


def test_candidate_upload_and_saved_packet_render_as_readable_brief() -> None:
    candidate = {
        "schema": "qf_candidate_v1",
        "candidate": {"title": "Readable Candidate", "status": "draft"},
        "sources": [{"type": "owner_observation"}],
        "hypothesis": {
            "behavior": "An intraday behavior may persist.",
            "failure_theory": ["The effect may be noise."],
        },
        "market": {"holding_style": "intraday", "overnight_positions": False},
        "rules": {"entry": ["Use a fixed intraday trigger."]},
        "fixed": {"flat_by_close": True},
        "variables": {"lookback": {"values": [5, 10]}},
        "variants": [{"id": "base", "difference": "Base logic."}],
        "open_questions": [
            {"question": "Which completed bar confirms entry?", "importance": "high"}
        ],
        "data_needs": {"minimum_resolution": "5m"},
        "exclusions": ["No overnight holding."],
        "prior_work": {"possible_duplicates": ["Prior fixture"]},
        "evaluation": {"use_qf_standard_screen": True},
    }
    draft = IdeaDraftView(
        draft_id="idea_candidate",
        title="Owner wording",
        description="Owner context",
        source_url="",
        attribution="Owner",
        notes="",
        configuration_id=None,
        created_at="2026-10-01T12:00:00Z",
        updated_at="2026-10-01T12:01:00Z",
        candidate_json=json.dumps(candidate),
    )

    page = ideas_layout(drafts=(draft,))
    rendered = str(page)

    for expected in (
        "Readable Candidate",
        "Source attribution",
        "Source rules",
        "QF interpretation",
        "Market & session",
        "Testable rules",
        "Fixed rules",
        "VectorBT sweep variables",
        "Structural variants",
        "Open questions",
        "Data needs",
        "Exclusions",
        "Prior-work claims",
        "Evaluation boundary",
    ):
        assert expected in rendered
    assert "Continue to Set up" in rendered
    continue_link = next(
        component
        for component in _walk(page)
        if getattr(component, "id", None) == "continue-idea-to-setup"
    )
    assert continue_link.href is None
    assert "action-disabled" in continue_link.className

    yaml_text = "schema: qf_candidate_v1\n"
    encoded = base64.b64encode(yaml_text.encode()).decode()
    assert _decode_candidate_upload(
        f"data:text/yaml;base64,{encoded}", "candidate.yaml"
    ) == yaml_text

    with pytest.raises(ValueError, match=".yaml, .yml, or .json"):
        _decode_candidate_upload(
            f"data:text/plain;base64,{encoded}", "candidate.txt"
        )


def test_new_setup_draft_is_known_to_run_preflight_without_server_restart(
    tmp_path,
) -> None:
    path = tmp_path / "operator.sqlite3"
    _register_fixture(path)
    draft = save_idea_draft({"title": "Fresh draft"}, database=path)
    app = create_app(
        review_database=path,
        catalog_snapshot=(None, (), None),
    )

    save_setup = _callback(app, "created-configuration-state.data")
    _, _, created, _, selected_id = save_setup(
        1,
        draft.to_store(),
        "spym_rsi_mean_reversion_fixture@1.0.0",
        [
            {"type": "setup-parameter", "name": "window"},
            {"type": "setup-parameter", "name": "entry_threshold"},
            {"type": "setup-parameter", "name": "exit_threshold"},
        ],
        [
            SPYM_RSI_WINDOW,
            SPYM_RSI_ENTRY_THRESHOLD,
            SPYM_RSI_EXIT_THRESHOLD,
        ],
    )
    assert created["configuration_id"] == selected_id

    launch = _callback(app, "launch-message.children")
    _, message, _, _, _, disabled, _, _ = launch(
        1,
        selected_id,
        None,
        "/research/run-test",
    )
    assert "did not pass preflight" in str(message)
    assert "could not be found" not in str(message)
    assert disabled is True
