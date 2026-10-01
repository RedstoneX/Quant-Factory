from __future__ import annotations

import json

import pytest

from persistence import LATEST_SCHEMA_VERSION, PersistenceService, StrategyLifecycle
from research_intake import (
    CandidatePacketError,
    export_candidate_packet,
    import_candidate_as_idea,
    parse_candidate_packet,
    validate_candidate_packet,
)


def _candidate_document() -> dict:
    return {
        "schema": "qf_candidate_v1",
        "candidate": {
            "title": "15-minute ORB with VWAP confirmation",
            "one_line": "Trade opening-range breaks only with VWAP confirmation.",
            "family": "opening_range_breakout",
            "status": "draft",
        },
        "sources": [
            {
                "type": "youtube",
                "title": "ORB Strategy Explained",
                "url": "https://www.youtube.com/watch?v=example",
                "creator": "Example Trader",
            }
        ],
        "hypothesis": {
            "behavior": "Opening directional pressure may continue after the first range.",
            "failure_theory": [
                "The opening range may contain most of the move.",
                "VWAP confirmation may enter too late.",
            ],
        },
        "market": {
            "instruments": {"preferred": ["MES", "MNQ"]},
            "timeframe": "5m",
            "session": "US regular trading hours",
            "holding_style": "intraday",
            "overnight_positions": False,
        },
        "rules": {
            "setup": ["Build the opening range from 09:30 through 09:45 ET."],
            "long_entry": ["Close above range high while above VWAP."],
            "short_entry": ["Close below range low while below VWAP."],
            "exits": {"time_exit": "Flat by 15:55 ET."},
        },
        "fixed": {"max_trades_per_session": 1},
        "variables": {
            "opening_range_minutes": {"values": [5, 15, 30]},
            "target_r": {"values": [1.0, 2.0]},
        },
        "variants": [
            {
                "id": "plain_orb",
                "name": "Plain ORB",
                "difference": "No VWAP filter.",
            },
            {
                "id": "vwap_location",
                "name": "VWAP location",
                "difference": "Require price on the correct side of VWAP.",
            },
        ],
        "open_questions": [
            {
                "id": "breakout_definition",
                "question": "Does a touch count or must the bar close beyond the range?",
                "importance": "high",
            }
        ],
        "execution": {"use_qf_defaults": True},
        "exclusions": ["No overnight holding."],
        "evaluation": {"use_qf_standard_screen": True},
    }


def test_candidate_yaml_parses_and_distinguishes_sweep_from_review_readiness() -> None:
    yaml_text = """
schema: qf_candidate_v1
candidate:
  title: ORB test
  status: draft
sources:
  - type: owner_observation
hypothesis:
  behavior: Opening breakouts may continue intraday.
  failure_theory:
    - The opening move may already be exhausted.
market:
  holding_style: intraday
  overnight_positions: false
rules:
  long_entry:
    - Break above opening range.
variables:
  opening_range_minutes:
    values: [5, 15, 30]
  target_r:
    values: [1.0, 2.0]
open_questions:
  - question: Must the breakout close beyond the range?
    importance: high
"""
    document = parse_candidate_packet(yaml_text)
    result = validate_candidate_packet(document)

    assert result.valid is True
    assert result.review_ready is False
    assert result.parameter_combinations == 6
    assert not result.errors


def test_candidate_rejects_current_mandate_conflict_and_execution_control() -> None:
    document = _candidate_document()
    document["market"]["overnight_positions"] = True
    document["auto_launch"] = True

    result = validate_candidate_packet(document)

    codes = {issue.code for issue in result.errors}
    assert "overnight_positions" in codes
    assert "forbidden_control" in codes
    assert result.valid is False


def test_candidate_import_persists_canonical_packet_on_durable_idea(tmp_path) -> None:
    path = tmp_path / "qf.sqlite3"
    document = _candidate_document()

    imported = import_candidate_as_idea(document, database=path)

    assert imported.validation.valid is True
    assert imported.validation.parameter_combinations == 6
    assert imported.draft.title == document["candidate"]["title"]
    assert imported.draft.source_url.startswith("https://www.youtube.com/")
    assert imported.draft.candidate_json

    service = PersistenceService(path)
    try:
        persisted = service.idea_drafts.get(imported.draft.draft_id)
        assert persisted is not None
        stored = json.loads(persisted.candidate_json)
        assert stored["schema"] == "qf_candidate_v1"
        assert stored["variables"]["opening_range_minutes"]["values"] == [5, 15, 30]
        version = service.connection.execute(
            "SELECT schema_version FROM schema_metadata"
        ).fetchone()["schema_version"]
        assert version == LATEST_SCHEMA_VERSION == 7
    finally:
        service.close()


def test_linked_idea_candidate_packet_is_frozen(tmp_path) -> None:
    path = tmp_path / "qf.sqlite3"
    service = PersistenceService(path)
    try:
        draft = service.save_idea_draft(title="Frozen later")
        service.set_idea_candidate_packet(
            draft_id=draft.draft_id,
            candidate_json=json.dumps(_candidate_document()),
        )
        service.register_strategy(
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            display_name="Fixture",
            description="Fixture only",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
            active=True,
        )
        configuration = service.upsert_configuration(
            {
                "experiment_id": "fixture_experiment",
                "strategy_id": "fixture_strategy",
                "strategy_version": "1.0.0",
                "market_data": {},
                "parameters": {},
                "execution": {},
                "ranking": {},
                "screening": {},
            }
        )
        service.link_idea_configuration(
            draft_id=draft.draft_id,
            configuration_id=configuration.configuration_id,
        )
        with pytest.raises(ValueError, match="cannot change its candidate packet"):
            service.set_idea_candidate_packet(
                draft_id=draft.draft_id,
                candidate_json=json.dumps(_candidate_document()),
            )
    finally:
        service.close()


def test_candidate_round_trip_external_exchange_formats() -> None:
    document = _candidate_document()

    yaml_text = export_candidate_packet(document, format="yaml")
    json_text = export_candidate_packet(document, format="json")

    assert validate_candidate_packet(parse_candidate_packet(yaml_text)).valid
    assert validate_candidate_packet(parse_candidate_packet(json_text)).valid


def test_invalid_candidate_does_not_create_idea(tmp_path) -> None:
    document = _candidate_document()
    document["candidate"]["title"] = ""

    with pytest.raises(CandidatePacketError, match="candidate.title"):
        import_candidate_as_idea(document, database=tmp_path / "qf.sqlite3")

    service = PersistenceService(tmp_path / "qf.sqlite3")
    try:
        assert service.idea_drafts.list() == ()
    finally:
        service.close()
