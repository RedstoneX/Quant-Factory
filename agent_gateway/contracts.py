"""Stable JSON contracts for the provider-neutral agent gateway."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping


GATEWAY_PROTOCOL = "qf_agent_gateway_v1"
MAX_REQUEST_BYTES = 256_000
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_AGENT_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class GatewayError(ValueError):
    """An expected fail-closed response safe to return to an agent."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class GatewayIdentity:
    agent_id: str
    transport: str
    peer_uid: int | None
    authority_level: int

    def __post_init__(self) -> None:
        if not _AGENT_ID.fullmatch(self.agent_id):
            raise GatewayError("invalid_agent", "agent identity is not recognized")
        if self.transport not in {"local", "ssh"}:
            raise GatewayError("invalid_transport", "transport identity is not recognized")
        if self.authority_level not in {0, 1, 2}:
            raise GatewayError("invalid_authority", "authority level is not recognized")


@dataclass(frozen=True)
class GatewayRequest:
    request_id: str
    operation: str
    arguments: dict[str, Any]
    payload: str | None = None
    claimed_agent: str | None = None

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "GatewayRequest":
        if document.get("protocol") != GATEWAY_PROTOCOL:
            raise GatewayError("invalid_protocol", "gateway protocol is not supported")
        request_id = document.get("request_id")
        operation = document.get("operation")
        arguments = document.get("arguments", {})
        payload = document.get("payload")
        claimed_agent = document.get("agent")
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise GatewayError("invalid_request_id", "request identity is invalid")
        if not isinstance(operation, str) or not operation or len(operation) > 80:
            raise GatewayError("invalid_operation", "gateway operation is invalid")
        if not isinstance(arguments, dict):
            raise GatewayError("invalid_arguments", "operation arguments must be an object")
        if payload is not None and not isinstance(payload, str):
            raise GatewayError("invalid_payload", "request payload must be text")
        if claimed_agent is not None and (
            not isinstance(claimed_agent, str) or not _AGENT_ID.fullmatch(claimed_agent)
        ):
            raise GatewayError("invalid_agent", "agent identity is not recognized")
        return cls(request_id, operation, dict(arguments), payload, claimed_agent)


@dataclass(frozen=True)
class GatewayResponse:
    request_id: str
    ok: bool
    result: Any | None = None
    error: dict[str, str] | None = None

    def document(self) -> dict[str, Any]:
        return {"protocol": GATEWAY_PROTOCOL, **asdict(self)}


def success(request_id: str, result: Any) -> GatewayResponse:
    return GatewayResponse(request_id=request_id, ok=True, result=result)


def failure(request_id: str, code: str, message: str) -> GatewayResponse:
    return GatewayResponse(
        request_id=request_id,
        ok=False,
        error={"code": code, "message": message},
    )
