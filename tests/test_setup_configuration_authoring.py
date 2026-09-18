"""Focused immutable Setup configuration authoring regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard.app import create_app
from dashboard.run_adapter import list_saved_configurations
from dashboard.setup_draft import (
    SetupDraftError,
    draft_fields,
    evaluate_setup_draft,
    load_persisted_base,
    save_setup_draft,
)
from persistence import PersistenceService, StrategyLifecycle, canonical_json
from persistence.database import transaction
from persistence.models import normalized_configuration_document
from strategies.spym_rsi_mean_reversion_fixture import (
    SPYM_RSI_ENTRY_THRESHOLD,
    SPYM_RSI_EXIT_THRESHOLD,
    SPYM_RSI_WINDOW,
)


def _seed_configuration(tmp_path: Path) -> tuple[Path, str]:
    database = tmp_path / "state" / "setup-authoring.sqlite3"
    service = PersistenceService(database)
    try:
        service.register_strategy(
            strategy_id="spym_rsi_mean_reversion_fixture",
            strategy_version="1.0.0",
            display_name="SPYM RSI fixture",
            description="Data-free Setup authoring regression fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
            active=True,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="setup_authoring_fixture",
                strategy_id="spym_rsi_mean_reversion_fixture",
                strategy_version="1.0.0",
                market_data={
                    "kind": "none",
                    "provider": "recorded-provider",
                    "dataset_id": "recorded-dataset",
                    "dataset": "recorded-feed",
                    "symbol": "SPYM",
                    "timeframe": "1m",
                    "coverage_start": "2025-10-31",
                    "coverage_end_policy": "latest_fully_completed_session",
                },
                parameters={
                    "fixture": "spym_databento_rsi_vectorbt_21c",
                    "strategy_parameters": {
                        "window": SPYM_RSI_WINDOW,
                        "entry_threshold": SPYM_RSI_ENTRY_THRESHOLD,
                        "exit_threshold": SPYM_RSI_EXIT_THRESHOLD,
                    },
                },
                execution={
                    "kind": "spym_databento_rsi_vectorbt_21c",
                    "broker_orders": "disabled",
                    "initial_cash": 10_000.0,
                    "fees": 0.0,
                    "slippage": 0.0,
                    "order_size": 1.0,
                    "strategy_fixture_only": True,
                    "profitability_research": False,
                },
                ranking={"columns": ("total_return",), "ascending": (False,)},
                screening={"minimum_trades": 0},
            )
        )
        return database, configuration.configuration_id
    finally:
        service.close()


def _base(database: Path, configuration_id: str):
    view = next(
        item
        for item in list_saved_configurations(database)
        if item.configuration_id == configuration_id
    )
    return load_persisted_base(database, view)


def _payload(base, **overrides: object):
    ids = []
    values = []
    for field in draft_fields(base):
        if not isinstance(field.value, (str, int, float, bool)):
            continue
        ids.append(
            {
                "type": "setup-draft-input",
                "configuration": base.configuration.configuration_id,
                "section": field.section,
                "path": field.path,
            }
        )
        values.append(overrides.get(f"{field.section}:{field.path}", field.value))
    return ids, values


def _evaluation(base, **overrides: object):
    ids, values = _payload(base, **overrides)
    return evaluate_setup_draft(
        base,
        field_ids=ids,
        field_values=values,
        catalog_snapshot=None,
    )


def test_fixture_draft_preserves_contract_and_saves_new_immutable_identity(
    tmp_path: Path,
) -> None:
    database, original_id = _seed_configuration(tmp_path)
    base = _base(database, original_id)
    original_json = canonical_json(base.document)

    evaluation = _evaluation(base, **{"execution:/fees": 0.001})

    assert evaluation.saveable
    assert evaluation.document["execution"]["fees"] == 0.001
    for preserved in (
        "experiment_id",
        "strategy_id",
        "strategy_version",
        "market_data",
        "parameters",
        "ranking",
        "screening",
    ):
        assert evaluation.document[preserved] == base.document[preserved]
    assert evaluation.document["execution"]["broker_orders"] == "disabled"
    assert evaluation.document["execution"]["strategy_fixture_only"] is True

    result = save_setup_draft(database, evaluation)
    assert result.created
    assert result.configuration.configuration_id != original_id
    assert result.configuration.configuration_id == evaluation.readiness.configuration_id

    service = PersistenceService(database)
    try:
        original = service.configurations.get(original_id)
        assert original is not None
        assert original.canonical_config_json == original_json
        assert len(service.configurations.list()) == 2
    finally:
        service.close()


def test_same_content_selects_existing_identity_without_duplicate_creation(
    tmp_path: Path,
) -> None:
    database, original_id = _seed_configuration(tmp_path)
    base = _base(database, original_id)
    evaluation = _evaluation(base, **{"execution:/fees": 0.001})
    first = save_setup_draft(database, evaluation)
    second = save_setup_draft(database, evaluation)

    assert first.created is True
    assert second.created is False
    assert second.configuration.configuration_id == first.configuration.configuration_id
    service = PersistenceService(database)
    try:
        assert len(service.configurations.list()) == 2
    finally:
        service.close()


def test_invalid_cost_and_fixed_contract_change_fail_before_mutation(
    tmp_path: Path,
) -> None:
    database, original_id = _seed_configuration(tmp_path)
    base = _base(database, original_id)
    ids, values = _payload(base, **{"execution:/fees": -0.01})
    fixed_index = next(
        index
        for index, identity in enumerate(ids)
        if identity["section"] == "execution" and identity["path"] == "/broker_orders"
    )
    values[fixed_index] = "enabled"
    evaluation = evaluate_setup_draft(
        base,
        field_ids=ids,
        field_values=values,
        catalog_snapshot=None,
    )

    assert not evaluation.saveable
    assert any("Fees must not be negative" in error for error in evaluation.errors)
    assert any("Broker Orders is fixed" in error for error in evaluation.errors)
    with pytest.raises(SetupDraftError):
        save_setup_draft(database, evaluation)
    service = PersistenceService(database)
    try:
        assert len(service.configurations.list()) == 1
    finally:
        service.close()


def test_identity_content_collision_rolls_back_and_preserves_draft(
    tmp_path: Path,
) -> None:
    database, original_id = _seed_configuration(tmp_path)
    base = _base(database, original_id)
    evaluation = _evaluation(base, **{"execution:/fees": 0.002})
    target_id = evaluation.readiness.configuration_id
    conflicting = dict(evaluation.document)
    conflicting["experiment_id"] = "conflicting_corrupt_record"

    service = PersistenceService(database)
    try:
        with transaction(service.connection):
            service.connection.execute(
                """
                INSERT INTO experiment_configurations
                (configuration_id, experiment_id, strategy_id, strategy_version,
                 canonical_config_json, config_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_id,
                    conflicting["experiment_id"],
                    conflicting["strategy_id"],
                    conflicting["strategy_version"],
                    canonical_json(conflicting),
                    target_id,
                    "2026-09-18T00:00:00+00:00",
                ),
            )
        before = tuple(service.configurations.list())
    finally:
        service.close()

    with pytest.raises(SetupDraftError, match="identity collision"):
        save_setup_draft(database, evaluation)

    service = PersistenceService(database)
    try:
        assert tuple(service.configurations.list()) == before
        original = service.configurations.get(original_id)
        assert original is not None
        assert original.canonical_config_json == canonical_json(base.document)
    finally:
        service.close()
    assert evaluation.document["execution"]["fees"] == 0.002


def test_registered_setup_callbacks_keep_draft_and_writes_page_owned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, original_id = _seed_configuration(tmp_path)
    base = _base(database, original_id)
    ids, values = _payload(base, **{"execution:/fees": 0.001})
    monkeypatch.setattr("dashboard.application.inspect_catalog", lambda: (None, (), None))
    app = create_app(review_database=database)

    preview_key = next(
        key for key in app.callback_map if "configuration-preview.children" in key
    )
    preview_entry = app.callback_map[preview_key]
    preview = getattr(preview_entry["callback"], "__wrapped__", preview_entry["callback"])
    outputs = preview(original_id, values, ids)
    assert outputs[1] is None
    assert outputs[4] is False
    assert "Unsaved changes" in outputs[6]

    save_key = next(
        key
        for key in app.callback_map
        if "configuration-selector.options" in key and "setup-save-message.children" in key
    )
    save_entry = app.callback_map[save_key]
    save = getattr(save_entry["callback"], "__wrapped__", save_entry["callback"])
    monkeypatch.setattr(
        "dashboard.callbacks.setup._callback_triggered_id",
        lambda: "save-configuration",
    )
    options, selected, message, class_name = save(
        1,
        "/research/setup",
        original_id,
        values,
        ids,
    )
    assert selected != original_id
    assert any(option["value"] == selected for option in options)
    assert "Saved a new immutable setup" in str(message)
    assert class_name == "save-message success-state"

    output_ids = {
        output.component_id
        for output in save_entry["output"]
    }
    assert output_ids == {
        "configuration-selector",
        "setup-save-message",
    }
