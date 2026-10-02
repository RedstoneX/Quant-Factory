"""Deployment composition root for the private agent research gateway."""

from __future__ import annotations

import os
from pathlib import Path

from agent_gateway.service import AgentResearchGateway
from agent_gateway.socket_server import GatewayUnixServer, PeerPolicy
from orchestration import CandidatePipelineRuntime
from prefect_spike.candidate_pipeline_flow import run_candidate_pipeline_flow


def _required_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value or not Path(value).is_absolute():
        raise RuntimeError(f"{name} must be an absolute path")
    return Path(value)


def _uid_set(value: str) -> set[int]:
    try:
        result = {int(item) for item in value.split(",") if item.strip()}
    except ValueError as exc:
        raise RuntimeError("QF_GATEWAY_LOCAL_UIDS must contain numeric UIDs") from exc
    if not result or any(item < 0 for item in result):
        raise RuntimeError("QF_GATEWAY_LOCAL_UIDS must contain authorized UIDs")
    return result


def _authorities(value: str) -> dict[str, int]:
    result: dict[str, int] = {}
    try:
        for entry in value.split(","):
            name, level = entry.split(":", 1)
            result[name] = int(level)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("QF_GATEWAY_AUTHORITIES is invalid") from exc
    if set(result) != {"codex-local", "claude-local", "grok-remote"}:
        raise RuntimeError("QF_GATEWAY_AUTHORITIES must configure the three approved agents")
    if any(level not in {0, 1, 2} for level in result.values()):
        raise RuntimeError("QF_GATEWAY_AUTHORITIES contains an invalid level")
    return result


def build_server() -> GatewayUnixServer:
    database = _required_path("QUANT_FACTORY_DB_PATH")
    artifact_root = _required_path("QUANT_FACTORY_ARTIFACT_ROOT")
    gateway_database = _required_path("QF_GATEWAY_DB_PATH")
    socket_path = _required_path("QF_GATEWAY_SOCKET_PATH")
    run_enabled = os.environ.get("QF_GATEWAY_RUN_REQUESTS_ENABLED", "false") == "true"

    def launch(_candidate_id: str, configuration_id: str, idempotency_key: str) -> str:
        runtime = CandidatePipelineRuntime.from_saved_configuration(
            database=database,
            artifact_root=artifact_root,
            configuration_id=configuration_id,
            pipeline_launcher=run_candidate_pipeline_flow,
            cache_only=True,
        )
        result = runtime.launch(idempotency_key=idempotency_key)
        return result.launch.claim.run.run_id

    gateway = AgentResearchGateway(
        database=database,
        gateway_database=gateway_database,
        artifact_root=artifact_root,
        run_launcher=launch if run_enabled else None,
    )
    try:
        remote_uid = int(os.environ["QF_GATEWAY_REMOTE_UID"])
    except (KeyError, ValueError) as exc:
        raise RuntimeError("QF_GATEWAY_REMOTE_UID must be numeric") from exc
    policy = PeerPolicy(
        local_uids=_uid_set(os.environ.get("QF_GATEWAY_LOCAL_UIDS", "")),
        remote_uid=remote_uid,
        authorities=_authorities(os.environ.get("QF_GATEWAY_AUTHORITIES", "")),
    )
    return GatewayUnixServer(socket_path, gateway=gateway, peer_policy=policy)


def main() -> None:
    server = build_server()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
