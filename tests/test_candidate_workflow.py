from __future__ import annotations

from dashboard.candidate_workflow import (
    candidate_configuration_binding,
    candidate_identity_for_configuration,
)
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from persistence import PersistenceService, RunStage, StrategyLifecycle
from research_intake import import_candidate_as_idea, record_candidate_decision


def _candidate() -> dict:
    return {
        "schema": "qf_candidate_v1",
        "candidate": {
            "title": "MES first-hour continuation",
            "family": "intraday_momentum",
            "status": "ready_for_review",
        },
        "sources": [{"type": "owner_observation"}],
        "hypothesis": {
            "behavior": "A first-hour move may continue within the same session.",
            "failure_theory": ["The move may reverse after the first hour."],
        },
        "market": {"holding_style": "intraday", "overnight_positions": False},
        "rules": {"entry": ["Use a fixed first-hour trigger."]},
        "fixed": {"flat_by_close": True},
        "variables": {},
        "variants": [],
        "open_questions": [],
        "evaluation": {"use_qf_standard_screen": True},
    }


def _linked_candidate(path):
    imported = import_candidate_as_idea(_candidate(), database=path)
    approved = record_candidate_decision(
        draft_id=imported.draft.draft_id,
        decision="owner_approved",
        database=path,
    )
    service = PersistenceService(path)
    try:
        service.register_strategy(
            strategy_id="mes_first_hour_candidate",
            strategy_version="1.0.0",
            display_name="MES first-hour candidate",
            description="Focused identity test",
            lifecycle=StrategyLifecycle.CANDIDATE,
            active=True,
        )
        configuration = service.upsert_configuration(
            {
                "experiment_id": "mes_first_hour_candidate",
                "strategy_id": "mes_first_hour_candidate",
                "strategy_version": "1.0.0",
                "market_data": {"symbol": "MES", "interval": "1m"},
                "parameters": {"window": 60},
                "execution": {"fees": "fixed"},
                "ranking": {},
                "screening": {},
            }
        )
        service.link_idea_configuration(
            draft_id=approved.draft.draft_id,
            configuration_id=configuration.configuration_id,
        )
        run = service.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id="mes_first_hour_candidate",
            strategy_version="1.0.0",
            stage=RunStage.SCREENING,
        )
        return approved.draft.draft_id, configuration.configuration_id, run.run_id
    finally:
        service.close()


def test_owner_decision_and_exact_candidate_binding_are_durable(tmp_path) -> None:
    path = tmp_path / "qf.sqlite3"
    candidate_id, configuration_id, _run_id = _linked_candidate(path)

    binding = candidate_configuration_binding(candidate_id, database=path)
    identity = candidate_identity_for_configuration(configuration_id, database=path)

    assert binding.bound is True
    assert binding.configuration.configuration_id == configuration_id
    assert binding.identity == identity
    assert identity.candidate_id == candidate_id
    assert identity.status == "owner_approved"
    assert len(identity.version_fingerprint) == 64


def test_run_detail_retains_candidate_identity(tmp_path) -> None:
    path = tmp_path / "qf.sqlite3"
    candidate_id, _configuration_id, run_id = _linked_candidate(path)

    detail = RunDetailDashboardAdapter(database=path).selected_run_detail(run_id)
    fields = {field.label: field.value for field in detail.configuration_fields}
    assert fields["Candidate"] == "MES first-hour continuation"
    assert fields["Candidate ID"] == candidate_id
    assert len(fields["Candidate version"]) == 64
    assert "first-hour move" in fields["Candidate rationale"]
    assert "flat_by_close" in fields["Candidate fixed definition"]
    assert "use_qf_standard_screen" in fields["Candidate evidence contract"]
