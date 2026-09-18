from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import http.client
import json
from pathlib import Path
import signal
from threading import Event, Thread

import pytest
import yaml

from execution.paper_read_transport import PaperReadError, ReadFailure
from execution.paper_worker import (
    ObservationError, ObservationFailure, PaperObserver, WorkerConfig, check_health,
    health_server, main, serve, validate_account, validate_positions,
)

ACCOUNT = "54c41ab9-eab7-4823-a47d-2a0b63b18590"
ASSET = "13b33184-593b-4dcf-a1d1-0fc11f26c2a1"
NOW = datetime(2026, 9, 3, 14, tzinfo=timezone.utc)
UNTRUSTED = "untrusted-private-value-must-not-be-printed"


def config(**changes):
    values = {
        "expected_account_id": ACCOUNT, "deployment_id": "paper-observer-fixture",
        "owner_attestation_reference": "owner-attestation:paper-observer-fixture-20260903",
        "proxy_url": "http://gateway-relay:10255", "identity_file": "/run/paper/identity",
        "ca_file": "/run/paper/gateway-ca.pem", "refresh_seconds": 30,
    }
    values.update(changes)
    return WorkerConfig(**values)


def account(**changes):
    values = {
        "id": ACCOUNT, "status": "ACTIVE", "currency": "USD", "cash": "10000.125",
        "equity": "10046.905", "buying_power": "20000.25", "trading_blocked": False,
        "account_blocked": False, "trade_suspended_by_user": False, "transfers_blocked": False,
    }
    values.update(changes)
    return values


def position(**changes):
    values = {
        "asset_id": ASSET, "symbol": "SCHX", "asset_class": "us_equity", "side": "long",
        "qty": "2", "avg_entry_price": "23.45", "cost_basis": "46.90", "market_value": "46.78",
        "current_price": "23.39", "unrealized_pl": "-0.12",
    }
    values.update(changes)
    return values


class Clock:
    now = NOW
    def __call__(self):
        return self.now


class FakeTransport:
    def __init__(self, **_):
        self.account = account()
        self.positions = [position()]
        self.calls = []
        self.error = None
        self.closed = False
    def get(self, path):
        self.calls.append(path)
        if self.error:
            raise self.error
        return deepcopy(self.account if path == "/v2/account" else self.positions)
    def close(self):
        self.closed = True


@pytest.mark.parametrize("changes", [
    {"expected_account_id": "not-uuid"}, {"expected_account_id": ACCOUNT.upper()},
    {"deployment_id": "unsafe deployment"}, {"deployment_id": True},
    {"owner_attestation_reference": ""}, {"owner_attestation_reference": "decision-271"},
    {"refresh_seconds": 29}, {"refresh_seconds": 301}, {"refresh_seconds": True}, {"refresh_seconds": 30.0},
    {"identity_file": "relative"}, {"ca_file": "relative"},
    {"proxy_url": "http://credentials@gateway-relay:10255"},
])
def test_strict_config_types_and_boundaries(changes):
    with pytest.raises(PaperReadError) as caught:
        config(**changes)
    assert caught.value.reason is ReadFailure.CONFIGURATION_INVALID
    assert caught.value.__context__ is None


def test_config_load_requires_exact_public_keys_and_rejects_duplicates(tmp_path):
    path = tmp_path / "worker.json"
    values = vars(config())
    path.write_text(json.dumps(values))
    assert WorkerConfig.load(str(path)) == config()
    path.write_text(json.dumps(values | {"APCA_API_SECRET_KEY": UNTRUSTED}))
    with pytest.raises(PaperReadError):
        WorkerConfig.load(str(path))
    path.write_text(json.dumps(values)[:-1] + ',"refresh_seconds":60}')
    with pytest.raises(PaperReadError):
        WorkerConfig.load(str(path))
    assert ACCOUNT not in repr(config())


def test_config_binding_preserves_the_configured_account_deployment_and_attestation_reference():
    configured = config()
    assert configured.binding.account_id == configured.expected_account_id
    assert configured.binding.deployment_id == configured.deployment_id
    assert configured.binding.owner_attestation_reference == configured.owner_attestation_reference


def test_cli_without_attestation_reference_remains_deployment_unready(tmp_path, capsys):
    path = tmp_path / "worker.json"
    values = vars(config())
    del values["owner_attestation_reference"]
    path.write_text(json.dumps(values))
    assert main(["observe", "--config", str(path)]) == 2
    health = json.loads(capsys.readouterr().out)
    assert health["ready"] is False and health["deployment_ready"] is False
    assert health["account_authorization_status"] == "not_configured"


def test_account_values_remain_exact_and_transfer_block_does_not_invent_order_policy():
    result = validate_account(account(transfers_blocked=True), ACCOUNT)
    assert result.cash == Decimal("10000.125")
    assert result.equity == Decimal("10046.905")
    assert result.buying_power == Decimal("20000.25")
    assert "10000" not in repr(result) and ACCOUNT not in repr(result)


@pytest.mark.parametrize("field,value,reason", [
    ("id", "1ec64240-a59a-467d-a2d1-cc2a2a28ae1f", ObservationFailure.ACCOUNT_MISMATCH),
    ("status", "ACCOUNT_CLOSED", ObservationFailure.ACCOUNT_INACTIVE),
    ("currency", "EUR", ObservationFailure.ACCOUNT_INVALID),
    ("trading_blocked", True, ObservationFailure.ACCOUNT_BLOCKED),
    ("account_blocked", True, ObservationFailure.ACCOUNT_BLOCKED),
    ("trade_suspended_by_user", True, ObservationFailure.ACCOUNT_BLOCKED),
    ("trading_blocked", None, ObservationFailure.ACCOUNT_INVALID),
    ("account_blocked", 0, ObservationFailure.ACCOUNT_INVALID),
    ("trade_suspended_by_user", "false", ObservationFailure.ACCOUNT_INVALID),
    ("transfers_blocked", "false", ObservationFailure.ACCOUNT_INVALID),
    ("cash", True, ObservationFailure.ACCOUNT_INVALID), ("equity", 10.2, ObservationFailure.ACCOUNT_INVALID),
    ("buying_power", "Infinity", ObservationFailure.ACCOUNT_INVALID),
])
def test_account_identity_restrictions_and_numbers_fail_closed(field, value, reason):
    fake = FakeTransport()
    fake.account[field] = value
    observer = PaperObserver(config(), fake, clock=Clock())
    health = observer.refresh()
    assert health["ready"] is False and health["account_verified"] is False
    assert health["blocked_reason"] == reason.value
    assert fake.calls == ["/v2/account"]
    assert health["position_count"] is None


@pytest.mark.parametrize("positions", [
    None, {}, [position(), position()], [position(asset_id="bad")], [position(asset_class="crypto")],
    [position(side="invalid")], [position(qty="0")], [position(qty=True)], [position(avg_entry_price=23.45)],
    [position(cost_basis="NaN")], [position(market_value="Infinity")], [position(current_price="-1")],
])
def test_positions_are_validated_before_reporting_count(positions):
    fake = FakeTransport()
    fake.positions = positions
    health = PaperObserver(config(), fake, clock=Clock()).refresh()
    assert health["ready"] is False and health["position_count"] is None
    assert health["blocked_reason"] == "positions_invalid"


def test_empty_and_signed_positions_are_observations_not_reconciliation():
    assert validate_positions([]) == 0
    assert validate_positions([position(side="short", qty="-2", market_value="-46.78")]) == 1
    fake = FakeTransport()
    fake.positions = []
    health = PaperObserver(config(), fake, clock=Clock()).refresh()
    assert health["ready"] is True and health["position_count"] == 0
    assert "matched" not in json.dumps(health) and "reconciliation" not in health


def test_freshness_failure_restart_and_backward_clock_never_report_ready():
    clock, fake = Clock(), FakeTransport()
    observer = PaperObserver(config(), fake, clock=clock)
    assert observer.health()["blocked_reason"] == "not_observed"
    initial = observer.refresh()
    assert initial["ready"] is True and initial["observed_at"] == "2026-09-03T14:00:00Z"
    assert initial["order_submission_enabled"] is False
    assert initial["deployment_ready"] is False
    assert initial["account_authorization_status"] == "external_attestation_reference_unverified"
    assert not {"cash", "equity", "buying_power", "account_id"} & initial.keys()
    clock.now += timedelta(seconds=61)
    assert observer.health()["blocked_reason"] == "observation_stale"
    assert observer.health()["ready"] is False
    clock.now = NOW - timedelta(seconds=1)
    assert observer.health()["ready"] is False
    clock.now = NOW
    fake.error = PaperReadError(ReadFailure.GATEWAY_DENIED)
    failed = observer.refresh()
    assert failed["ready"] is False and failed["gateway_status"] == "denied"
    assert failed["position_count"] is None and failed["observed_at"] == initial["observed_at"]
    assert PaperObserver(config(), FakeTransport(), clock=clock).health()["ready"] is False


def test_slow_positions_read_does_not_refresh_old_account_observation_time():
    clock = Clock()
    fake = FakeTransport()
    original = fake.get
    def slow(path):
        if path == "/v2/positions":
            clock.now += timedelta(seconds=61)
        return original(path)
    fake.get = slow
    health = PaperObserver(config(), fake, clock=clock).refresh()
    assert health["ready"] is False and health["blocked_reason"] == "observation_stale"
    assert health["observed_at"] == "2026-09-03T14:00:00Z"


def test_untrusted_transport_error_is_not_reflected_in_health_or_logs(capsys, caplog):
    fake = FakeTransport()
    fake.error = RuntimeError(UNTRUSTED)
    result = PaperObserver(config(), fake, clock=Clock()).refresh()
    assert result["blocked_reason"] == "observation_failed"
    assert UNTRUSTED not in json.dumps(result) + caplog.text + capsys.readouterr().out


def test_private_health_server_exposes_only_status_and_never_invokes_transport():
    fake, clock = FakeTransport(), Clock()
    observer = PaperObserver(config(), fake, clock=clock)
    server = health_server(observer, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        assert check_health(server.server_port) == 1
        observer.refresh()
        assert check_health(server.server_port) == 0
        for method, path, expected in [("GET", "/healthz", 200), ("GET", "/v2/orders", 404), ("POST", "/healthz", 405), ("DELETE", "/v2/positions", 405)]:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request(method, path)
            response = connection.getresponse()
            body = json.loads(response.read())
            assert response.status == expected
            assert ACCOUNT not in json.dumps(body) and "10000.125" not in json.dumps(body)
            connection.close()
        assert fake.calls == ["/v2/account", "/v2/positions"]
        clock.now += timedelta(seconds=61)
        assert check_health(server.server_port) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_serve_honors_stop_event_without_another_refresh():
    fake = FakeTransport()
    observer = PaperObserver(config(), fake, clock=Clock())
    stop = Event()
    stop.set()
    serve(observer, stop, port=0)
    assert observer.health()["blocked_reason"] == "observer_stopped"
    assert fake.calls == []


def test_cli_observe_outputs_only_fixed_health_fields_and_sanitizes_bad_arguments(tmp_path, monkeypatch, capsys):
    path = tmp_path / "worker.json"
    path.write_text(json.dumps(vars(config())))
    fake = FakeTransport()
    monkeypatch.setattr("execution.paper_worker.PaperReadTransport", lambda **_: fake)
    assert main(["observe", "--config", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ready"] is True and output["order_submission_enabled"] is False
    assert fake.closed is True and ACCOUNT not in json.dumps(output)
    with pytest.raises(SystemExit) as caught:
        main(["--api-secret", UNTRUSTED])
    assert caught.value.code == 2
    assert UNTRUSTED not in capsys.readouterr().err


def test_cli_signal_handler_stops_server_and_restores_previous_handlers(tmp_path, monkeypatch):
    path = tmp_path / "worker.json"
    path.write_text(json.dumps(vars(config())))
    fake, handlers = FakeTransport(), {}
    monkeypatch.setattr("execution.paper_worker.PaperReadTransport", lambda **_: fake)
    def install(signum, handler):
        previous = handlers.get(signum, "previous")
        handlers[signum] = handler
        return previous
    monkeypatch.setattr(signal, "signal", install)
    def running(_observer, stop, **_):
        assert not stop.is_set()
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        assert stop.is_set()
    monkeypatch.setattr("execution.paper_worker.serve", running)
    assert main(["serve", "--config", str(path)]) == 0
    assert fake.closed and handlers == {signal.SIGINT: "previous", signal.SIGTERM: "previous"}


def test_container_has_an_explicit_minimal_read_only_boundary():
    root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((root / "deployment/paper/compose.yaml").read_text())
    service = compose["services"]["paper-observer"]
    assert service["user"] == "10002:10002" and service["read_only"] is True
    assert service["cap_drop"] == ["ALL"] and service["security_opt"] == ["no-new-privileges:true"]
    assert service["ports"] == ["127.0.0.1:8051:8051"]
    assert service["networks"] == ["paper-read"]
    assert compose["networks"]["paper-read"] == {"external": True, "name": "quant-factory-paper-read"}
    assert all(mount["read_only"] and mount["bind"]["create_host_path"] is False for mount in service["volumes"])
    assert {mount["target"] for mount in service["volumes"]} == {"/run/paper/config.json", "/run/paper/identity", "/run/paper/gateway-ca.pem"}
    dockerfile = (root / "deployment/paper/Dockerfile").read_text()
    assert "COPY execution/ /app/execution/" in dockerfile and "COPY ." not in dockerfile
    assert "vectorbt" not in dockerfile.lower() and "docker.sock" not in json.dumps(compose)
    ignore = (root / "deployment/paper/Dockerfile.dockerignore").read_text().splitlines()
    assert ignore[0] == "**" and "!execution/*.py" in ignore
    requirements = (root / "deployment/paper/requirements.txt").read_text().splitlines()
    assert all("==" in requirement for requirement in requirements)
