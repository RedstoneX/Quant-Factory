"""Authenticated Dashboard client for the existing Agent Research Gateway."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
from typing import Any

GATEWAY_PROTOCOL = "qf_agent_gateway_v1"
DEFAULT_SOCKET = "/run/quant-factory/agent-gateway.sock"
MAX_RESPONSE_BYTES = 1_024_000
CREDENTIAL_ENVIRONMENT_VARIABLE = "QF_AGENT_CREDENTIAL_FILE"
SOCKET_ENVIRONMENT_VARIABLE = "QF_AGENT_SOCKET"


def gateway_status() -> dict[str, Any]:
    return _request("bootstrap", request_id="qfui_bootstrap_status_0001")


def submit_candidate(payload: str) -> dict[str, Any]:
    canonical = str(payload).strip()
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return _request("candidate.submit", payload=canonical, request_id=f"qfui_{digest[:48]}")


def _request(operation: str, *, request_id: str, payload: str | None = None) -> dict[str, Any]:
    credential_path = os.environ.get(CREDENTIAL_ENVIRONMENT_VARIABLE)
    if not credential_path:
        return _unavailable("Dashboard gateway credential path is not configured.")
    try:
        credential = Path(credential_path).read_text(encoding="utf-8").strip()
    except OSError:
        return _unavailable("Dashboard gateway credential is unavailable.")
    if not credential:
        return _unavailable("Dashboard gateway credential is empty.")
    document: dict[str, Any] = {
        "protocol": GATEWAY_PROTOCOL, "request_id": request_id,
        "credential": credential, "operation": operation,
        "arguments": {}, "payload": payload,
    }
    try:
        response = _send(document, os.environ.get(SOCKET_ENVIRONMENT_VARIABLE, DEFAULT_SOCKET))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return _unavailable("Authenticated Candidate intake is temporarily unavailable.")
    return response if isinstance(response, dict) else _unavailable("Authenticated Candidate intake returned an invalid response.")


def _send(document: dict[str, Any], socket_path: str) -> dict[str, Any]:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(120)
        client.connect(socket_path)
        client.sendall(encoded)
        response = b""
        while not response.endswith(b"\n"):
            chunk = client.recv(65_536)
            if not chunk:
                break
            response += chunk
            if len(response) > MAX_RESPONSE_BYTES:
                raise RuntimeError("gateway response exceeds size limit")
    parsed = json.loads(response)
    if not isinstance(parsed, dict):
        raise RuntimeError("gateway response is invalid")
    return parsed


def _unavailable(message: str) -> dict[str, Any]:
    return {"protocol": GATEWAY_PROTOCOL, "ok": False, "error": {"code": "gateway_unavailable", "message": message}}


__all__ = ["gateway_status", "submit_candidate"]
