"""One-shot operator diagnostic; never an order worker or vault-value reader.

Run only under the explicit, bounded operator authorization for this diagnostic.
This does not adopt OneCLI or satisfy ADR 0010. The admin endpoint is local
operator access. Only a newly created identity is changed; the stored Dedicated
Paper Account pair and existing agents are never modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import UUID, uuid4

from execution.paper_read_transport import PaperReadError, PaperReadTransport, strict_json

TARGET = "https://paper-api.alpaca.markets/v2/account"
PAIR = {
    "Dedicated Paper Account - Key ID": "APCA-API-KEY-ID",
    "Dedicated Paper Account - Secret": "APCA-API-SECRET-KEY",
}
GATEWAY_PROXY_PORT = 10255


class CheckFailed(RuntimeError):
    def __init__(self):
        super().__init__("authentication_check_inconclusive")


def identity(value):
    if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
        raise CheckFailed()
    return value


class LocalAdmin:
    """Fixed loopback management endpoint; no redirects or environment proxies."""

    def call(self, method, path, payload=None, *, raw=False):
        connection = http.client.HTTPConnection("127.0.0.1", 10254, timeout=8)
        try:
            body = None if payload is None else json.dumps(payload).encode()
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read(262145)
            if response.status not in {200, 201, 204} or len(data) > 262144:
                raise CheckFailed()
            return data if raw else (strict_json(data, limit=262144) if data else None)
        except Exception:
            raise CheckFailed() from None
        finally:
            connection.close()


def select_pair(metadata):
    if type(metadata) is not list:
        raise CheckFailed()
    selected = []
    for name, header in PAIR.items():
        rows = [row for row in metadata if type(row) is dict and row.get("name") == name]
        if len(rows) != 1:
            raise CheckFailed()
        row = rows[0]
        injection = row.get("injectionConfig")
        if (row.get("type") != "generic" or row.get("hostPattern") != "paper-api.alpaca.markets"
                or row.get("pathPattern") not in {None, "", "/v2/account"}
                or type(injection) is not dict or injection.get("headerName") != header
                or injection.get("valueFormat") != "{value}"
                or any(key in injection for key in ("paramName", "paramFormat", "pathTemplate", "pathRegex", "pathReplacement"))
                or any(key in row for key in ("value", "encryptedValue", "accessToken"))):
            raise CheckFailed()
        selected.append(identity(row.get("id")))
    if len(set(selected)) != 2:
        raise CheckFailed()
    return selected


def account_result(client):
    try:
        account = client.get("/v2/account")
        if type(account) is not dict:
            raise CheckFailed()
        account_id = identity(account.get("id"))
        status = account.get("status")
        if status not in {"ONBOARDING", "SUBMISSION_FAILED", "SUBMITTED", "ACCOUNT_UPDATED",
                          "APPROVAL_PENDING", "ACTIVE", "REJECTED", "DISABLED", "ACCOUNT_CLOSED"}:
            raise CheckFailed()
        return {"result": "authenticated", "http_status": 200, "account_status": status,
                "account_fingerprint": hashlib.sha256(account_id.encode()).hexdigest()}
    except PaperReadError as error:
        # A 401/403 is rejection on the checked path, not proof of deletion,
        # expiration, live-key validity, or gateway-versus-broker provenance.
        return {"result": "rejected" if error.http_status in {401, 403} else "inconclusive",
                "http_status": error.http_status, "reason": error.reason.value}


def run_check(admin, *, proxy_port, temporary_root, transport_factory=PaperReadTransport):
    created_identifier = "qf-auth-check-" + uuid4().hex
    report = {"target": TARGET, "pair": "Dedicated Paper Account", "result": "inconclusive",
              "orders_enabled": False, "identity_removed": False,
              "diagnostic_identifier": created_identifier,
              "started_at": datetime.now(timezone.utc).isoformat()}
    agent_id = None
    client = None
    try:
        secrets = select_pair(admin.call("GET", "/v1/secrets"))
        created = admin.call("POST", "/v1/agents", {
            "name": "Quant Factory temporary authentication check", "identifier": created_identifier,
        })
        agent_id = identity(created.get("id"))
        report["temporary_agent_id"] = agent_id
        for secret_id in secrets:
            admin.call("PUT", f"/v1/agents/{agent_id}/grants/secrets/{secret_id}")
        grants = admin.call("GET", f"/v1/agents/{agent_id}/grants")
        if (grants.get("mode") != "grants" or grants.get("connections") != []
                or sorted(item["secretId"] for item in grants["secrets"]) != sorted(secrets)):
            raise CheckFailed()
        report["granted_secret_count"] = len(secrets)
        token = admin.call("POST", f"/v1/agents/{agent_id}/regenerate-token")["accessToken"]
        if type(token) is not str or not re.fullmatch(r"[!-~]{16,1024}", token):
            raise CheckFailed()
        ca = admin.call("GET", "/v1/gateway/ca", raw=True)
        with tempfile.TemporaryDirectory(prefix="qf-auth-check-", dir=temporary_root) as directory:
            capability, certificate = Path(directory) / "identity", Path(directory) / "ca.pem"
            for destination, data in ((capability, token.encode()), (certificate, ca)):
                with destination.open("xb") as output:
                    os.fchmod(output.fileno(), 0o600)
                    output.write(data)
            client = transport_factory(proxy_url=f"http://127.0.0.1:{proxy_port}",
                                       identity_file=str(capability), ca_file=str(certificate))
            report.update(account_result(client))
    except Exception:
        report["result"] = "inconclusive"
    finally:
        if client is not None:
            client.close()
        try:
            # Recover an owned identity after an ambiguous create response without
            # deleting anything merely because its display name looks similar.
            agents = admin.call("GET", "/v1/agents")
            owned = [row for row in agents if row.get("identifier") == created_identifier]
            if agent_id is None and len(owned) == 1:
                agent_id = identity(owned[0]["id"])
            if agent_id is not None:
                if len(owned) != 1 or identity(owned[0]["id"]) != agent_id:
                    raise CheckFailed()
                # Remove grants before deleting the identity so their compiled
                # policy rows are retired through OneCLI's supported API.
                grants = admin.call("GET", f"/v1/agents/{agent_id}/grants")
                for item in grants["secrets"]:
                    secret_id = identity(item["secretId"])
                    admin.call("DELETE", f"/v1/agents/{agent_id}/grants/secrets/{secret_id}")
                admin.call("DELETE", f"/v1/agents/{agent_id}")
            remaining = admin.call("GET", "/v1/agents")
            report["identity_removed"] = not any(
                row.get("identifier") == created_identifier for row in remaining)
        except Exception:
            report["identity_removed"] = False
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-authorized-read-only-2026-09-03", action="store_true")
    args = parser.parse_args()
    try:
        if not args.operator_authorized_read_only_2026_09_03:
            raise CheckFailed()
        result = run_check(LocalAdmin(), proxy_port=GATEWAY_PROXY_PORT, temporary_root="/dev/shm")
    except Exception:
        result = {"result": "inconclusive", "orders_enabled": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("result") == "authenticated" and result.get("identity_removed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
