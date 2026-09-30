from __future__ import annotations

from dataclasses import asdict
import json
import sqlite3

import pytest

from dashboard.callbacks.setup import _parameter_controls
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
        assert version == LATEST_SCHEMA_VERSION == 6
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
