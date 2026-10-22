"""ADR 0011 proofs that outer fixture-launch retry is disabled."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration import FixtureRunService
from orchestration.run_service import FixtureRetryPolicy
from persistence import PersistenceService, RunEventType
from prefect_spike.fixture_flow import (
    PrefectRunReference,
    _validated_claim_boundary,
    deterministic_fixture_body,
)
import prefect_spike.fixture_flow as fixture_flow
from tests.test_run_service import _configuration


def _assert_no_launch_mutation(database: Path) -> None:
    service = PersistenceService(database)
    try:
        assert service.runs.list() == ()
        assert service.connection.execute(
            "SELECT COUNT(*) FROM research_run_submissions"
        ).fetchone()[0] == 0
    finally:
        service.close()


def test_outer_retry_policy_is_rejected_before_claim(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    with pytest.raises(ValueError, match="outer fixture-launch retries are disabled"):
        FixtureRunService(database=database).launch_fixture(
            configuration_id=configuration_id,
            run_id="qf-retry-policy-disabled",
            retry_policy=FixtureRetryPolicy(max_attempts=2),
        )
    _assert_no_launch_mutation(database)


def test_outer_transient_failure_injection_is_rejected_before_claim(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    with pytest.raises(ValueError, match="outer fixture-launch retries are disabled"):
        FixtureRunService(database=database).launch_fixture(
            configuration_id=configuration_id,
            run_id="qf-transient-retry-disabled",
            controlled_transient_failures=1,
        )
    _assert_no_launch_mutation(database)


def test_internal_task_retry_records_one_idempotent_event_on_one_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    if fixture_flow.deterministic_retry_task is None:
        pytest.skip("Prefect is unavailable")
    monkeypatch.setattr(
        fixture_flow,
        "get_run_logger",
        lambda: SimpleNamespace(warning=lambda *_args: None, info=lambda *_args: None),
    )
    marker = tmp_path / "attempts" / "internal-retry.txt"
    invocations: list[str] = []

    def launcher(**kwargs):
        invocations.append(kwargs["quant_factory_run_id"])
        kwargs.pop("attempt_marker_path")
        _validated_claim_boundary(
            database_path=kwargs["database_path"],
            idempotency_key=kwargs["idempotency_key"],
            configuration_id=kwargs["configuration_id"],
            quant_factory_run_id=kwargs["quant_factory_run_id"],
            canonical_request_json=kwargs["canonical_request_json"],
            request_fingerprint=kwargs["request_fingerprint"],
            operation_kind=kwargs["operation_kind"],
            source_run_id=kwargs["source_run_id"],
            source_lineage=kwargs["source_lineage"],
            prefect_reference=PrefectRunReference(flow_run_id="prefect-retry"),
        )
        task_body = fixture_flow.deterministic_retry_task.fn
        with pytest.raises(RuntimeError, match="controlled first-attempt failure"):
            task_body(str(database), kwargs["quant_factory_run_id"], str(marker))
        assert task_body(str(database), kwargs["quant_factory_run_id"], str(marker)) == {
            "deterministic_value": 1729
        }
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id="prefect-retry",
        )

    result = FixtureRunService(database=database, fixture_launcher=launcher).launch_fixture(
        idempotency_key="launch_internal_retry_001",
        configuration_id=configuration_id,
        run_id="qf-internal-retry",
        attempt_marker_path=marker,
    )

    persistence = PersistenceService(database)
    try:
        retry_events = [
            event
            for event in persistence.events.list_for_run(result.run.run_id)
            if event.event_type == RunEventType.RUN_RETRY_SCHEDULED
        ]
        assert len(persistence.runs.list()) == 1
    finally:
        persistence.close()
    assert invocations == ["qf-internal-retry"]
    assert len(retry_events) == 1
    assert retry_events[0].source == "prefect"
