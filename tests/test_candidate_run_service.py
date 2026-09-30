"""Focused durable-claim tests for the explicit candidate screening seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestration import (
    CANDIDATE_SCREENING_LAUNCH_POLICY,
    CANDIDATE_SCREENING_REQUEST_PROTOCOL_VERSION,
    CandidateRunService,
    DurableResearchLaunchService,
    ResearchLaunchConflictError,
    ResearchLaunchError,
    ResearchLaunchInvocationUnknownError,
)
from persistence import (
    PersistenceService,
    ResearchLaunchOperation,
    ResearchSubmissionState,
    RunStage,
    RunStatus,
    StrategyLifecycle,
)
from persistence.models import normalized_configuration_document
from tests.test_run_lineage import _service_with_lineage_run


def _candidate_configuration(path: Path, *, suffix: str = "one") -> str:
    persistence = PersistenceService(path)
    try:
        strategy_id = f"candidate_{suffix}"
        persistence.register_strategy(
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            display_name=f"Candidate {suffix}",
            description="Deterministic candidate-dispatch contract fixture",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        return persistence.upsert_configuration(
            normalized_configuration_document(
                experiment_id=f"candidate_screening_{suffix}",
                strategy_id=strategy_id,
                strategy_version="1.0.0",
                market_data={"provider": "deterministic-test"},
                parameters={"window": 10},
                execution={"mode": "deterministic-test"},
                ranking={"columns": ["total_return"], "ascending": [False]},
                screening={"minimum_trades": 1},
            )
        ).configuration_id
    finally:
        persistence.close()


def _key(suffix: str) -> str:
    return f"candidate_{suffix:0<24}"


def _acknowledging_adapter(calls: list[str]):
    def adapter(submission, claims):
        calls.append(submission.run_id)
        return claims.bind_prefect_identity(
            idempotency_key=submission.idempotency_key,
            run_id=submission.run_id,
            configuration_id=submission.configuration_id,
            canonical_request_json=submission.canonical_request_json,
            request_fingerprint=submission.request_fingerprint,
            prefect_flow_run_id=f"deterministic-{submission.run_id}",
        )

    return adapter


def _candidate_source_with_lineage(
    tmp_path: Path,
    *,
    result_status: str | None = "passed",
    source_status: RunStatus = RunStatus.SUCCEEDED,
) -> tuple[Path, str, str]:
    source_run_id = "candidate-source-screening"
    persistence, configuration_id = _service_with_lineage_run(
        tmp_path,
        run_id=source_run_id,
    )
    database = tmp_path / "state" / f"{source_run_id}.sqlite3"
    try:
        persistence.update_strategy_lifecycle(
            "fixture_strategy",
            "1.0.0",
            lifecycle=StrategyLifecycle.CANDIDATE,
            active=True,
        )
        persistence.connection.execute(
            "UPDATE experiment_runs SET stage=? WHERE run_id=?",
            (RunStage.SCREENING.value, source_run_id),
        )
        persistence.connection.commit()
        if result_status is not None:
            persistence.results.add_parameter_result(
                run_id=source_run_id,
                row_id="source-variant",
                normalized_parameters={"window": 10},
                metrics={"total_return": 0.1 if result_status == "passed" else -0.1},
                ranking_position=1,
                screening_status=result_status,
                rejection_reasons=(
                    "" if result_status == "passed" else "deterministic rejection"
                ),
            )
            persistence.connection.commit()
        persistence.transition_run(source_run_id, RunStatus.RUNNING)
        persistence.transition_run(source_run_id, source_status)
        persistence.persist_run_manifest(
            persistence.build_run_manifest(source_run_id)
        )
    finally:
        persistence.close()
    return database, configuration_id, source_run_id


def test_candidate_screening_claim_is_distinct_and_replays_one_adapter_invocation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "candidate.sqlite3"
    configuration_id = _candidate_configuration(database)
    calls: list[str] = []
    service = CandidateRunService(
        database=database,
        screening_adapter=_acknowledging_adapter(calls),
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )

    first = service.launch_screening(
        idempotency_key=_key("replay"),
        configuration_id=configuration_id,
    )
    second = service.launch_screening(
        idempotency_key=_key("replay"),
        configuration_id=configuration_id,
    )

    assert first.claim.created is True
    assert first.claim.run.stage == RunStage.SCREENING
    assert first.dispatch.invoked is True
    assert first.dispatch.submission.state == ResearchSubmissionState.ACKNOWLEDGED
    assert second.claim.created is False
    assert second.claim.run.run_id == first.claim.run.run_id
    assert second.claim.run.stage == RunStage.SCREENING
    assert second.claim.run.status == RunStatus.RUNNING
    assert second.dispatch.invoked is False
    assert calls == [first.claim.run.run_id]
    request = json.loads(first.claim.submission.canonical_request_json)
    assert request["protocol_version"] == CANDIDATE_SCREENING_REQUEST_PROTOCOL_VERSION
    assert request["accepted_launch_policy"] == CANDIDATE_SCREENING_LAUNCH_POLICY
    assert request["candidate_stage"] == RunStage.SCREENING.value
    assert "fixture_stage" not in request
    persistence = PersistenceService(database)
    try:
        messages = tuple(
            event.message
            for event in persistence.events.list_for_run(first.claim.run.run_id)
        )
        assert messages == (
            "Run created for explicit candidate screening submission.",
            "Run started through acknowledged Prefect candidate screening execution.",
        )
        assert all("fixture" not in message.lower() for message in messages)
    finally:
        persistence.close()


def test_candidate_screening_key_conflict_creates_nothing_and_does_not_reinvoke(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "conflict.sqlite3"
    first_configuration = _candidate_configuration(database, suffix="one")
    second_configuration = _candidate_configuration(database, suffix="two")
    calls: list[str] = []
    service = CandidateRunService(
        database=database,
        screening_adapter=_acknowledging_adapter(calls),
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )
    key = _key("conflict")
    first = service.launch_screening(
        idempotency_key=key,
        configuration_id=first_configuration,
    )

    with pytest.raises(ResearchLaunchConflictError):
        service.launch_screening(idempotency_key=key, configuration_id=second_configuration)

    persistence = PersistenceService(database)
    try:
        runs = persistence.runs.list()
        assert len(runs) == 1
        assert runs[0].run_id == first.claim.run.run_id
        assert runs[0].stage == RunStage.SCREENING
    finally:
        persistence.close()
    assert calls == [first.claim.run.run_id]


def test_candidate_screening_rejects_non_candidate_before_claim_or_adapter(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "wrong-lifecycle.sqlite3"
    configuration_id = _candidate_configuration(database)
    persistence = PersistenceService(database)
    try:
        persistence.connection.execute(
            "UPDATE strategies SET lifecycle=?",
            (StrategyLifecycle.INFRASTRUCTURE_FIXTURE.value,),
        )
        persistence.connection.commit()
    finally:
        persistence.close()
    calls: list[str] = []
    service = CandidateRunService(
        database=database,
        screening_adapter=_acknowledging_adapter(calls),
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )

    with pytest.raises(ResearchLaunchError, match="not approved for screening launch"):
        service.launch_screening(
            idempotency_key=_key("lifecycle"),
            configuration_id=configuration_id,
        )

    assert calls == []
    persistence = PersistenceService(database)
    try:
        assert persistence.runs.list() == ()
    finally:
        persistence.close()


def test_candidate_adapter_failure_stays_unknown_and_never_reinvokes(tmp_path: Path) -> None:
    database = tmp_path / "state" / "unknown.sqlite3"
    configuration_id = _candidate_configuration(database)
    calls: list[str] = []

    def failing_adapter(submission, _claims):
        calls.append(submission.run_id)
        raise RuntimeError("controlled deterministic adapter failure")

    service = CandidateRunService(
        database=database,
        screening_adapter=failing_adapter,
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )
    key = _key("unknown")

    with pytest.raises(ResearchLaunchInvocationUnknownError):
        service.launch_screening(idempotency_key=key, configuration_id=configuration_id)
    replay = service.launch_screening(idempotency_key=key, configuration_id=configuration_id)

    assert replay.dispatch.invoked is False
    assert replay.dispatch.submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
    assert calls == [replay.claim.run.run_id]
    persistence = PersistenceService(database)
    try:
        run = persistence.runs.get(replay.claim.run.run_id)
        assert run is not None
        assert run.status == RunStatus.CREATED
    finally:
        persistence.close()


def test_candidate_service_rejects_fixture_claim_service(tmp_path: Path) -> None:
    database = tmp_path / "state" / "fixture-contract.sqlite3"
    with pytest.raises(ValueError, match="candidate-screening claim contract"):
        CandidateRunService(
            claim_service=DurableResearchLaunchService(database=database),
            screening_adapter=_acknowledging_adapter([]),
        )


@pytest.mark.parametrize(
    "operation",
    (
        ResearchLaunchOperation.HISTORICAL_RELAUNCH,
        ResearchLaunchOperation.REPRODUCTION,
    ),
)
def test_candidate_service_forwards_supported_operation_and_screening_source(
    tmp_path: Path,
    operation: ResearchLaunchOperation,
) -> None:
    database, configuration_id, source_run_id = _candidate_source_with_lineage(
        tmp_path
    )
    calls: list[str] = []
    service = CandidateRunService(
        database=database,
        screening_adapter=_acknowledging_adapter(calls),
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )

    result = service.launch_screening(
        idempotency_key=_key(operation.value),
        configuration_id=configuration_id,
        operation=operation,
        source_run_id=source_run_id,
    )

    request = json.loads(result.claim.submission.canonical_request_json)
    assert request["operation_kind"] == operation.value
    assert request["source_run_id"] == source_run_id
    assert result.claim.run.stage == RunStage.SCREENING
    assert result.dispatch.invoked is True
    assert calls == [result.claim.run.run_id]


@pytest.mark.parametrize(
    "operation",
    (
        ResearchLaunchOperation.HISTORICAL_RELAUNCH,
        ResearchLaunchOperation.REPRODUCTION,
    ),
)
def test_candidate_service_rejects_terminal_all_screened_out_source_before_claim(
    tmp_path: Path,
    operation: ResearchLaunchOperation,
) -> None:
    database, configuration_id, source_run_id = _candidate_source_with_lineage(
        tmp_path,
        result_status="screened_out",
    )
    calls: list[str] = []
    service = CandidateRunService(
        database=database,
        screening_adapter=_acknowledging_adapter(calls),
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )

    with pytest.raises(ResearchLaunchError, match="at least one passing variant"):
        service.launch_screening(
            idempotency_key=_key(f"reject-{operation.value}"),
            configuration_id=configuration_id,
            operation=operation,
            source_run_id=source_run_id,
        )

    assert calls == []
    persistence = PersistenceService(database)
    try:
        assert tuple(run.run_id for run in persistence.runs.list()) == (source_run_id,)
        assert persistence.connection.execute(
            "SELECT COUNT(*) FROM research_run_submissions"
        ).fetchone()[0] == 0
    finally:
        persistence.close()


@pytest.mark.parametrize(
    "operation",
    (
        ResearchLaunchOperation.HISTORICAL_RELAUNCH,
        ResearchLaunchOperation.REPRODUCTION,
    ),
)
@pytest.mark.parametrize("result_status", (None, "unexpected_status"))
def test_candidate_service_rejects_incomplete_or_malformed_succeeded_source_before_claim(
    tmp_path: Path,
    operation: ResearchLaunchOperation,
    result_status: str | None,
) -> None:
    database, configuration_id, source_run_id = _candidate_source_with_lineage(
        tmp_path,
        result_status=result_status,
    )
    calls: list[str] = []
    service = CandidateRunService(
        database=database,
        screening_adapter=_acknowledging_adapter(calls),
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )

    with pytest.raises(ResearchLaunchError, match="nonempty, valid"):
        service.launch_screening(
            idempotency_key=_key(f"invalid-{operation.value}-{result_status}"),
            configuration_id=configuration_id,
            operation=operation,
            source_run_id=source_run_id,
        )

    assert calls == []
    persistence = PersistenceService(database)
    try:
        assert tuple(run.run_id for run in persistence.runs.list()) == (source_run_id,)
        assert persistence.connection.execute(
            "SELECT COUNT(*) FROM research_run_submissions"
        ).fetchone()[0] == 0
    finally:
        persistence.close()


def test_candidate_historical_relaunch_keeps_failed_technical_source_recoverable(
    tmp_path: Path,
) -> None:
    database, configuration_id, source_run_id = _candidate_source_with_lineage(
        tmp_path,
        result_status=None,
        source_status=RunStatus.FAILED,
    )
    calls: list[str] = []
    service = CandidateRunService(
        database=database,
        screening_adapter=_acknowledging_adapter(calls),
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )

    result = service.launch_screening(
        idempotency_key=_key("failed-technical-relaunch"),
        configuration_id=configuration_id,
        operation=ResearchLaunchOperation.HISTORICAL_RELAUNCH,
        source_run_id=source_run_id,
    )

    assert result.dispatch.invoked is True
    assert calls == [result.claim.run.run_id]
