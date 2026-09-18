"""Canary-only roles for a disposable proof; never emit bodies or capabilities."""
import base64
import hashlib
import hmac
import http.client
import json
from pathlib import Path
import re
import socket
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LIMIT = 1024 * 1024
CANARY = re.compile(rb"qf_canary_[0-9a-f]{64}")


def leaks(body, token=b""):
    variants = [token, base64.b64encode(b"qf:" + token)] if token else []
    return bool(CANARY.search(body)) or any(value in body for value in variants)


def exchange(host, port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(host, port, timeout=4)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("response exceeds bound")
        return response.status, data
    finally:
        conn.close()


def admin(method, path, body=None):
    encoded = None if body is None else json.dumps(body).encode()
    status, data = exchange("onecli", 10254, method, path, encoded,
                            {"Content-Type": "application/json"})
    if status not in (200, 201, 204):
        raise ValueError("admin operation failed")
    return json.loads(data) if data else None


def prepare():
    # This reads only our freshly generated harmless fixture, never stored secrets.
    canary = Path("/fixture/canary").read_text()
    agent = admin("POST", "/v1/agents", {"name": "QF isolated proof", "identifier": "qf-proof"})
    token = admin("POST", "/v1/agents/" + agent["id"] + "/regenerate-token")["accessToken"]
    secret = admin("POST", "/v1/secrets", {
        "name": "Fresh harmless proof canary", "type": "generic", "value": canary,
        "hostPattern": "fixture.qf.test", "pathPattern": "/allowed",
        "injectionConfig": {"headerName": "X-QF-Test-Secret", "valueFormat": "{value}"},
    })
    grant = "/v1/agents/" + agent["id"] + "/grants/secrets/" + secret["id"]
    admin("PUT", grant)
    Path("/control/grant").write_text(grant)
    capability = Path("/actor/capability")
    capability.write_text(token)
    # Host parent directory is root-only; this file is mounted only into actor.
    capability.chmod(0o444)
    status, ca = exchange("onecli", 10254, "GET", "/v1/gateway/ca")
    if status != 200 or b"BEGIN CERTIFICATE" not in ca:
        raise ValueError("CA export failed")
    Path("/actor/gateway-ca.pem").write_bytes(ca)
    Path("/actor/gateway-ca.pem").chmod(0o444)
    return {"prepared": True, "agent_id": agent["id"], "ca_sha256": hashlib.sha256(ca).hexdigest()}


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        expected = Path("/fixture/canary").read_text()
        actual = self.headers.get("X-QF-Test-Secret", "")
        result = {"fixture": "qf-owned-canary", "injected": hmac.compare_digest(actual, expected),
                  "proxy_auth_absent": "Proxy-Authorization" not in self.headers}
        # Explicit malicious-fixture test: only this newly generated harmless
        # canary may be reflected. The actor emits detection booleans, not bytes.
        if self.headers.get("X-QF-Proof-Reflect") == "canary":
            result["reflected"] = actual
        body = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def request_case(path, token, authorized=True, reflect=False):
    headers = {"X-QF-Proof-Reflect": "canary"} if reflect else {}
    if authorized:
        headers["Proxy-Authorization"] = "Basic " + base64.b64encode(b"qf:" + token).decode()
    try:
        status, body = exchange("gateway-relay", 10255, "GET", path, headers=headers)
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            data = None
        fixture = type(data) is dict and data.get("fixture") == "qf-owned-canary"
        listing = type(data) is list and any(
            type(item) is dict and item.get("name") == "Fresh harmless proof canary"
            and type(item.get("id")) is str and re.fullmatch(
                r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", item["id"])
            for item in data)
        return {"status": status, "denied": status in (401, 403, 407),
                "fixture": fixture, "injected": fixture and data.get("injected") is True,
                "admin_listing_shape": bool(listing),
                "proxy_auth_absent": fixture and data.get("proxy_auth_absent") is True,
                "response_leak": leaks(body, token), "response_bytes": len(body)}
    except Exception:
        # Connection failures are not positive evidence of an explicit policy denial.
        return {"status": None, "denied": False, "transport_error": True}


def reachable(host, port):
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def actor():
    token = Path("/actor/capability").read_bytes()
    targets = {
        "allowed": "http://fixture.qf.test:8080/allowed",
        "wrong_path": "http://fixture.qf.test:8080/forbidden",
        "wrong_host": "http://wrong.qf.test:8080/allowed",
        "admin_proxy": "http://onecli:10254/v1/secrets",
        "admin_loopback_proxy": "http://127.0.0.1:10254/v1/secrets",
        "relay_admin_proxy": "http://gateway-relay:10254/v1/secrets",
    }
    result = {name: request_case(url, token) for name, url in targets.items()}
    result["wrong_identity"] = request_case(targets["allowed"], b"qf-invalid-proof-capability")
    result["missing_identity"] = request_case(targets["allowed"], b"", False)
    result["missing_identity_admin"] = request_case(targets["admin_loopback_proxy"], b"", False)
    result["canary_reflection"] = request_case(targets["allowed"], token, reflect=True)
    ips = json.loads(Path("/actor/private-addresses.json").read_text())
    result["direct_blocked"] = {
        "admin_dns": not reachable("onecli", 10254),
        "admin_ip": not reachable(ips["onecli"], 10254),
        "database_ip": not reachable(ips["db"], 5432),
        "relay_admin": not reachable("gateway-relay", 10254),
        "fixture_ip": not reachable(ips["fixture"], 8080),
        # TCP only: no HTTP, account, data or external application interaction.
        "internet_tcp": not reachable("1.1.1.1", 443),
    }
    return result


def main():
    try:
        role = sys.argv[1]
        if role == "fixture":
            HTTPServer(("0.0.0.0", 8080), Fixture).serve_forever()
            return 0
        if role == "prepare":
            result = prepare()
        elif role == "actor":
            result = actor()
        elif role == "revoke":
            admin("DELETE", Path("/control/grant").read_text())
            result = {"revoked": True}
        elif role == "ready":
            status, _ = exchange("onecli", 10254, "GET", "/v1/health")
            result = {"ready": status == 200}
        else:
            raise ValueError("unknown role")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print('{"error":"proof role failed"}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
