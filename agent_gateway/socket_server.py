"""Private Unix-socket transport for the agent research gateway."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import socketserver
import struct
from typing import Mapping

from agent_gateway.contracts import (
    MAX_REQUEST_BYTES,
    GatewayError,
    GatewayIdentity,
    GatewayRequest,
    failure,
)
from agent_gateway.service import AgentResearchGateway


class PeerPolicy:
    def __init__(
        self,
        *,
        local_uids: set[int],
        remote_uid: int,
        authorities: Mapping[str, int],
    ) -> None:
        self.local_uids = frozenset(local_uids)
        self.remote_uid = remote_uid
        self.authorities = dict(authorities)

    def identity(self, *, peer_uid: int, claimed_agent: str | None) -> GatewayIdentity:
        if peer_uid == self.remote_uid:
            agent_id, transport = "grok-remote", "ssh"
        elif peer_uid in self.local_uids and claimed_agent in {"codex-local", "claude-local"}:
            agent_id, transport = claimed_agent, "local"
        else:
            raise GatewayError("peer_denied", "operating-system peer is not authorized")
        level = self.authorities.get(agent_id)
        if level is None:
            raise GatewayError("invalid_agent", "agent identity is not configured")
        return GatewayIdentity(agent_id, transport, peer_uid, level)


class _GatewayHandler(socketserver.StreamRequestHandler):
    server: "GatewayUnixServer"

    def handle(self) -> None:
        request_id = "invalid_request_000000000000"
        try:
            raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                raise GatewayError("request_too_large", "gateway request exceeds size limit")
            if not raw:
                raise GatewayError("invalid_request", "gateway request is empty")
            document = json.loads(raw)
            if not isinstance(document, dict):
                raise GatewayError("invalid_request", "gateway request must be an object")
            request = GatewayRequest.from_document(document)
            request_id = request.request_id
            peer_uid = _peer_uid(self.request)
            identity = self.server.peer_policy.identity(
                peer_uid=peer_uid,
                claimed_agent=request.claimed_agent,
            )
            response = self.server.gateway.handle(request, identity)
        except GatewayError as exc:
            response = failure(request_id, exc.code, exc.safe_message)
        except (json.JSONDecodeError, UnicodeDecodeError):
            response = failure(request_id, "invalid_json", "gateway request is not valid JSON")
        except Exception:
            response = failure(
                request_id,
                "internal_error",
                "gateway transport failed without exposing internal details",
            )
        self.wfile.write(
            json.dumps(response.document(), sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
        )


class GatewayUnixServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(
        self,
        socket_path: str | Path,
        *,
        gateway: AgentResearchGateway,
        peer_policy: PeerPolicy,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.gateway = gateway
        self.peer_policy = peer_policy
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_socket():
            if not self.socket_path.is_socket():
                raise RuntimeError("gateway socket path exists and is not a socket")
            self.socket_path.unlink()
        super().__init__(str(self.socket_path), _GatewayHandler)
        os.chmod(self.socket_path, 0o660)

    def server_close(self) -> None:
        super().server_close()
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass


def _peer_uid(connection: socket.socket) -> int:
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    _pid, uid, _gid = struct.unpack("3i", credentials)
    return uid
