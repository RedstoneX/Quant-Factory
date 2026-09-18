import importlib.util
from pathlib import Path

import pytest

from execution.paper_read_transport import PaperReadError, ReadFailure


SCRIPT = Path(__file__).parents[1] / "tools" / "check_alpaca_authentication.py"
SPEC = importlib.util.spec_from_file_location("check_alpaca_authentication", SCRIPT)
check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check)


KEY_ID = "11111111-1111-1111-1111-111111111111"
SECRET = "22222222-2222-2222-2222-222222222222"
AGENT = "33333333-3333-3333-3333-333333333333"
TOKEN = "token-that-must-never-appear-in-a-report-0123456789"
LEAK = "upstream-body-must-never-appear"


def metadata(header="APCA-API-KEY-ID", *, path="/v2/account"):
    first = {"id": KEY_ID, "name": "Dedicated Paper Account - Key ID", "type": "generic",
             "hostPattern": "paper-api.alpaca.markets", "pathPattern": path,
             "injectionConfig": {"headerName": header, "valueFormat": "{value}"}}
    second = {"id": SECRET, "name": "Dedicated Paper Account - Secret", "type": "generic",
              "hostPattern": "paper-api.alpaca.markets", "pathPattern": path,
              "injectionConfig": {"headerName": "APCA-API-SECRET-KEY", "valueFormat": "{value}"}}
    return [first, second]


class Admin:
    def __init__(self, rows=None):
        self.rows = rows or metadata()
        self.calls = []
        self.identifier = None
        self.created = False

    def call(self, method, path, payload=None, **_):
        self.calls.append((method, path, payload))
        if (method, path) == ("GET", "/v1/secrets"):
            return self.rows
        if (method, path) == ("POST", "/v1/agents"):
            self.identifier = payload["identifier"]
            self.created = True
            return {"id": AGENT}
        if method == "PUT":
            return None
        if (method, path) == ("GET", f"/v1/agents/{AGENT}/grants"):
            return {"mode": "grants", "connections": [], "secrets": [{"secretId": KEY_ID}, {"secretId": SECRET}]}
        if (method, path) == ("POST", f"/v1/agents/{AGENT}/regenerate-token"):
            return {"accessToken": TOKEN}
        if (method, path) == ("GET", "/v1/gateway/ca"):
            return b"public-ca"
        if (method, path) == ("GET", "/v1/agents"):
            return ([{"id": AGENT, "identifier": self.identifier}] if self.created else [])
        if method == "DELETE":
            if path == f"/v1/agents/{AGENT}":
                self.created = False
            return None
        raise AssertionError((method, path))


class AccountClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    def get(self, path):
        assert path == "/v2/account"
        return {"id": "44444444-4444-4444-4444-444444444444", "status": "ACTIVE", "cash": LEAK}

    def close(self):
        self.closed = True


def test_authenticated_check_is_fixed_get_only_removes_its_identity_and_hides_sensitive_fields(tmp_path):
    admin = Admin()
    made = []

    def factory(**kwargs):
        client = AccountClient(**kwargs)
        made.append(client)
        return client

    report = check.run_check(admin, proxy_port=10255, temporary_root=str(tmp_path), transport_factory=factory)

    assert report["result"] == "authenticated"
    assert report["orders_enabled"] is False and report["identity_removed"] is True
    assert report["account_status"] == "ACTIVE" and len(report["account_fingerprint"]) == 64
    assert TOKEN not in repr(report) and LEAK not in repr(report)
    assert made[0].closed is True
    assert not list(tmp_path.iterdir())
    assert [call[:2] for call in admin.calls if call[0] == "DELETE"] == [
        ("DELETE", f"/v1/agents/{AGENT}/grants/secrets/{KEY_ID}"),
        ("DELETE", f"/v1/agents/{AGENT}/grants/secrets/{SECRET}"),
        ("DELETE", f"/v1/agents/{AGENT}"),
    ]
    assert not any(method in {"PATCH", "POST"} and "/orders" in path for method, path, _ in admin.calls)


@pytest.mark.parametrize("rows", [metadata(header="Wrong"), metadata(path="*")])
def test_wrong_secret_metadata_fails_before_creating_an_identity(tmp_path, rows):
    admin = Admin(rows)
    report = check.run_check(admin, proxy_port=10255, temporary_root=str(tmp_path), transport_factory=AccountClient)
    assert report["result"] == "inconclusive" and report["identity_removed"] is True
    assert ("POST", "/v1/agents") not in [call[:2] for call in admin.calls]


def test_ambiguous_create_cleanup_never_deletes_a_similarly_named_identity(tmp_path):
    admin = Admin()
    def fail_create(method, path, payload=None, **kwargs):
        if (method, path) == ("POST", "/v1/agents"):
            admin.identifier = payload["identifier"]
            admin.created = True
            raise RuntimeError(LEAK)
        if (method, path) == ("GET", "/v1/agents"):
            return [{"id": AGENT, "identifier": admin.identifier}, {"id": KEY_ID, "identifier": admin.identifier}]
        return Admin.call(admin, method, path, payload, **kwargs)
    admin.call = fail_create
    report = check.run_check(admin, proxy_port=10255, temporary_root=str(tmp_path), transport_factory=AccountClient)
    assert report["result"] == "inconclusive" and report["identity_removed"] is False
    assert not any(method == "DELETE" for method, _, _ in admin.calls)
    assert LEAK not in repr(report)


@pytest.mark.parametrize("status", [401, 403])
def test_rejection_status_is_not_misreported_as_expired_or_deleted(tmp_path, status):
    admin = Admin()
    class Rejected(AccountClient):
        def get(self, path):
            raise PaperReadError(ReadFailure.GATEWAY_DENIED, http_status=status)
    report = check.run_check(admin, proxy_port=10255, temporary_root=str(tmp_path), transport_factory=Rejected)
    assert report["result"] == "rejected" and report["http_status"] == status
    assert "expired" not in repr(report).lower() and "deleted" not in repr(report).lower()
    assert report["identity_removed"] is True


def test_error_body_and_account_fields_never_escape_the_report(tmp_path):
    admin = Admin()
    class Broken(AccountClient):
        def get(self, path):
            raise RuntimeError(LEAK)
    report = check.run_check(admin, proxy_port=10255, temporary_root=str(tmp_path), transport_factory=Broken)
    assert report["result"] == "inconclusive" and report["identity_removed"] is True
    assert LEAK not in repr(report)
    assert not {"cash", "buying_power", "portfolio_value"} & set(report)
