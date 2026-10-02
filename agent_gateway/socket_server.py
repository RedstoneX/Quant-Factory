"""Private Unix-socket transport for the agent research gateway."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import socketserver
import struct

from agent_gateway.contracts import (
    MAX_REQUEST_BYTES,
    GatewayError,
    GatewayIdentity,
    GatewayRequest,
    credential_from_document,
    failure,
)
from agent_gateway.service import AgentResearchGateway


@dataclass(frozen=True)
class IdentityRegistration:
    identity: GatewayIdentity
    credential_sha256: str | None = None

    def __post_init__(self) -> None:
        digest = self.credential_sha256
        if self.identity.peer_uid is not None:
            raise GatewayError("invalid_identity_registry", "registered identity cannot contain a peer UID")
        if self.identity.transport == "local":
            if digest is None or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise GatewayError("invalid_identity_registry", "local identity credential digest is invalid")
        elif digest is not None:
            raise GatewayError("invalid_identity_registry", "non-local identity cannot use a local credential")


class PeerPolicy:
    def __init__(
        self,
        *,
        local_uids: set[int],
        remote_uid: int,
        registrations: tuple[IdentityRegistration, ...],
    ) -> None:
        self.local_uids = frozenset(local_uids)
        self.remote_uid = remote_uid
        self.registrations = registrations
        agent_ids = [item.identity.agent_id for item in registrations]
        digests = [item.credential_sha256 for item in registrations if item.credential_sha256]
        remote = [item for item in registrations if item.identity.transport == "ssh"]
        if len(agent_ids) != len(set(agent_ids)) or len(digests) != len(set(digests)):
            raise GatewayError("invalid_identity_registry", "agent registrations must be unique")
        if len(remote) != 1:
            raise GatewayError("invalid_identity_registry", "exactly one SSH identity must be registered")
        self.remote_registration = remote[0]

    def identity(self, *, peer_uid: int, credential: str | None) -> GatewayIdentity:
        if peer_uid == self.remote_uid:
            if credential is not None:
                raise GatewayError("peer_denied", "operating-system peer is not authorized")
            return replace(self.remote_registration.identity, peer_uid=peer_uid)
        if peer_uid not in self.local_uids or credential is None:
            raise GatewayError("peer_denied", "operating-system peer is not authorized")
        digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()
        for registration in self.registrations:
            if registration.credential_sha256 and hmac.compare_digest(
                digest, registration.credential_sha256
            ):
                return replace(registration.identity, peer_uid=peer_uid)
        raise GatewayError("peer_denied", "operating-system peer is not authorized")


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
                credential=credential_from_document(document),
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
