from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_gateway.authority import OPERATION_LEVELS
from agent_gateway.cli import build_parser, request_document
from agent_gateway.contracts import GatewayIdentity, GatewayRequest
from agent_gateway.service import AgentResearchGateway
from agent_gateway.ssh_command import allowed_arguments
from persistence import PersistenceService, RunStage, RunStatus, StrategyLifecycle


def _candidate(*, title: str) -> dict:
    return {
        "schema": "qf_candidate_v1",
        "candidate": {"title": title, "status": "draft"},
        "hypothesis": {
            "behavior": "A bounded same-session effect may persist after costs.",
            "failure_theory": ["The apparent effect may be noise."],
        },
        "market": {"holding_style": "intraday", "overnight_positions": False},
        "rules": {"entry": ["Enter only after a completed bar."], "exit": ["Exit in-session."]},
        "sources": [
            {
                "type": "owner_observation",
                "title": "Owner observation",
                "retrieved_at": "2026-10-02T00:00:00Z",
                "claim": "A bounded behavior may exist.",
                "collected_by": "test-agent",
            }
        ],
        "fixed": {"flat_by_close": True},
        "variables": {"lookback": {"values": [5, 10]}},
        "variants": [],
        "open_questions": [],
        "data_needs": {"minimum_resolution": "5m"},
        "exclusions": ["No overnight holding."],
        "prior_work": {"possible_duplicates": []},
        "evaluation": {"use_qf_standard_screen": True},
    }


def _request(operation: str, *, arguments=None, request_id="req_1234567890abcdef", payload=None):
    return GatewayRequest(request_id=request_id, operation=operation, arguments=arguments or {}, payload=payload)


@pytest.fixture
def gateway(tmp_path: Path) -> AgentResearchGateway:
    return AgentResearchGateway(
        database=tmp_path / "qf.sqlite3",
        gateway_database=tmp_path / "gateway.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )


@pytest.fixture
def identities():
    return {
        "reader": GatewayIdentity("reader-local", "local-provider", "reader", "local", 0, os.getuid()),
        "codex": GatewayIdentity("codex-local", "openai", "codex", "local", 2, os.getuid()),
        "claude": GatewayIdentity("claude-local", "anthropic", "claude-code", "local", 1, os.getuid()),
    }


def _submit(gateway, identity, title: str, index: int) -> str:
    response = gateway.handle(
        _request("candidate.submit", payload=json.dumps(_candidate(title=title)), request_id=f"req_submit_{index:010d}"),
        identity,
    )
    assert response.ok, response.error
    return response.result["candidate_id"]


def _link_run(tmp_path: Path, candidate_id: str, *, finish: bool, suffix: str):
    service = PersistenceService(tmp_path / "qf.sqlite3")
    try:
        strategy_id = f"candidate_strategy_{suffix}"
        service.register_strategy(
            strategy_id=strategy_id, strategy_version="1.0.0", display_name="Candidate", description="",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        config = service.upsert_configuration(
            {"experiment_id": f"e_{suffix}", "strategy_id": strategy_id, "strategy_version": "1.0.0"}
        )
        service.link_idea_configuration(draft_id=candidate_id, configuration_id=config.configuration_id)
        run = service.create_run(
            configuration_id=config.configuration_id, strategy_id=strategy_id, strategy_version="1.0.0", stage=RunStage.OOS
        )
        if finish:
            service.transition_run(run.run_id, RunStatus.RUNNING)
            run = service.transition_run(run.run_id, RunStatus.SUCCEEDED)
        return run
    finally:
        service.close()


def test_candidate_status_is_a_level_zero_read_operation():
    assert OPERATION_LEVELS["candidate.status"] == OPERATION_LEVELS["candidate.list"] == 0


def test_candidate_status_lists_only_own_ideas_with_latest_run(gateway, identities, tmp_path):
    mine = _submit(gateway, identities["codex"], "Mine with run", 1)
    mine_unrun = _submit(gateway, identities["codex"], "Mine without run", 2)
    theirs = _submit(gateway, identities["claude"], "Someone else's idea", 3)
    run = _link_run(tmp_path, mine, finish=True, suffix="a")

    response = gateway.handle(_request("candidate.status"), identities["codex"])
    assert response.ok, response.error
    by_id = {row["candidate_id"]: row for row in response.result["candidates"]}
    assert set(by_id) == {mine, mine_unrun}
    assert theirs not in by_id
    assert by_id[mine]["status"] == "draft"
    assert by_id[mine]["latest_run"]["run_id"] == run.run_id
    assert by_id[mine]["latest_run"]["status"] == "succeeded"
    assert by_id[mine]["latest_run"]["completed_at"] == run.completed_at
    assert by_id[mine_unrun]["latest_run"] is None
    assert response.result["finished_since"] is None

    empty = gateway.handle(_request("candidate.status"), identities["reader"])
    assert empty.ok and empty.result["candidates"] == []


def test_finished_since_returns_only_ideas_whose_latest_run_finished_after_it(gateway, identities, tmp_path):
    finished = _submit(gateway, identities["codex"], "Finished idea", 1)
    unfinished = _submit(gateway, identities["codex"], "Unfinished idea", 2)
    _submit(gateway, identities["codex"], "Never run idea", 3)
    run = _link_run(tmp_path, finished, finish=True, suffix="a")
    _link_run(tmp_path, unfinished, finish=False, suffix="b")

    before = gateway.handle(
        _request("candidate.status", arguments={"finished_since": "2000-01-01T00:00:00Z"}), identities["codex"]
    )
    assert before.ok, before.error
    assert [row["candidate_id"] for row in before.result["candidates"]] == [finished]
    assert before.result["finished_since"] == "2000-01-01T00:00:00Z"

    after = gateway.handle(_request("candidate.status", arguments={"finished_since": run.completed_at}), identities["codex"])
    assert after.ok and after.result["candidates"] == []


def test_candidate_status_rejects_oversized_finished_since(gateway, identities):
    response = gateway.handle(_request("candidate.status", arguments={"finished_since": "x" * 41}), identities["codex"])
    assert response.ok is False


def test_cli_builds_candidate_status_request():
    parser = build_parser()
    plain = request_document(parser.parse_args(["candidate", "status"]))
    assert plain["operation"] == "candidate.status"
    assert plain["arguments"] == {}
    since = request_document(parser.parse_args(["candidate", "status", "--finished-since", "2026-10-20T00:00:00Z"]))
    assert since["operation"] == "candidate.status"
    assert since["arguments"] == {"finished_since": "2026-10-20T00:00:00Z"}


@pytest.mark.parametrize(
    "command",
    ["qf-agent candidate status", "qf-agent candidate status --finished-since 2026-10-20T00:00:00Z"],
)
def test_ssh_grammar_accepts_candidate_status(command):
    assert allowed_arguments(command)


def test_ssh_grammar_rejects_candidate_status_with_unknown_option():
    with pytest.raises(ValueError):
        allowed_arguments("qf-agent candidate status --other x")
