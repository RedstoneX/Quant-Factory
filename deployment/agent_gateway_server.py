"""Deployment composition root for the private agent research gateway."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_gateway.contracts import GatewayError, GatewayIdentity
from agent_gateway.service import AgentResearchGateway
from agent_gateway.socket_server import GatewayUnixServer, IdentityRegistration, PeerPolicy
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


def _identity_registry(path: Path) -> tuple[IdentityRegistration, ...]:
    try:
        document = json.loads(path.read_text())
        if not isinstance(document, dict):
            raise ValueError("identity registry must be an object")
        if document.get("schema") != "qf_agent_identity_registry_v1":
            raise ValueError("unsupported identity registry schema")
        rows = document["identities"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("identity registry must contain identities")
        registrations = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("identity registration must be an object")
            registrations.append(
                IdentityRegistration(
                    identity=GatewayIdentity(
                        agent_id=row["agent_id"],
                        provider=row["provider"],
                        client=row["client"],
                        transport=row["transport"],
                        authority_level=row["authority_level"],
                    ),
                    credential_sha256=row.get("credential_sha256"),
                )
            )
        return tuple(registrations)
    except (GatewayError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("QF_GATEWAY_IDENTITY_REGISTRY is invalid") from exc


def build_server() -> GatewayUnixServer:
    database = _required_path("QUANT_FACTORY_DB_PATH")
    artifact_root = _required_path("QUANT_FACTORY_ARTIFACT_ROOT")
    gateway_database = _required_path("QF_GATEWAY_DB_PATH")
    socket_path = _required_path("QF_GATEWAY_SOCKET_PATH")
    identity_registry = _required_path("QF_GATEWAY_IDENTITY_REGISTRY")
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
        registrations=_identity_registry(identity_registry),
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
