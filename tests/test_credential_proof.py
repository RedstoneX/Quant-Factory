"""No Docker, credentials or network required for proof-harness acceptance logic."""
import base64
import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1] / "deployment/credential-proof"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("run_proof")
probe = load("probe")


def valid_report():
    actor = {name: {"denied": True} for name in (
        "wrong_path", "wrong_host", "wrong_identity", "missing_identity",
        "admin_proxy", "admin_loopback_proxy", "relay_admin_proxy", "missing_identity_admin")}
    actor.update(allowed={"status": 200, "injected": True, "proxy_auth_absent": True},
                 direct_blocked={name: True for name in (
                     "admin_dns", "admin_ip", "database_ip", "fixture_ip", "internet_tcp", "relay_admin")})
    return {"initial": copy.deepcopy(actor), "after_restart": copy.deepcopy(actor),
            "after_revoke": {"allowed": {"denied": True}},
            "audit": {"allow_seen": True, "deny_seen": True, "identity_time_present": True},
            "no_leak": {"logs": True, "process_arguments": True}}


def test_complete_http_scope_passes():
    assert runner.passes(valid_report())
    assert not runner.passes({})


@pytest.mark.parametrize("phase", ["initial", "after_restart"])
@pytest.mark.parametrize("case", ["wrong_path", "wrong_host", "wrong_identity", "missing_identity",
                                 "admin_proxy", "admin_loopback_proxy", "relay_admin_proxy", "missing_identity_admin"])
def test_any_non_denial_fails_even_without_injection(phase, case):
    report = valid_report()
    report[phase][case] = {"status": 200, "injected": False, "denied": False}
    assert not runner.passes(report)


@pytest.mark.parametrize("failure", ["direct", "leak", "audit", "revoke", "proxy_header", "injection"])
def test_material_failure_does_not_round_up_to_pass(failure):
    report = valid_report()
    if failure == "direct":
        report["initial"]["direct_blocked"]["admin"] = False
    elif failure == "leak":
        report["initial"]["allowed"]["response_leak"] = True
    elif failure == "audit":
        report["audit"]["deny_seen"] = False
    elif failure == "revoke":
        report["after_revoke"]["allowed"]["denied"] = False
    elif failure == "proxy_header":
        report["initial"]["allowed"]["proxy_auth_absent"] = False
    else:
        report["initial"]["allowed"]["injected"] = False
    assert not runner.passes(report)


def test_leak_checks_include_encoded_proxy_password():
    token = b"fresh-fake-actor-capability"
    canary = b"qf_canary_" + b"a" * 64
    for value in [token, canary, base64.b64encode(b"qf:" + token)]:
        assert probe.leaks(b"prefix " + value + b" suffix", token)
        assert not runner.safe_scan(value, canary, token)
    assert not probe.leaks(b'{"injected":true}', token)


def test_transport_failure_is_not_policy_denial(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("fake-private-error")
    monkeypatch.setattr(probe, "exchange", fail)
    result = probe.request_case("http://fixture.qf.test:8080/allowed", b"fake")
    assert result == {"status": None, "denied": False, "transport_error": True}


def test_reflected_canary_yields_only_detection_booleans(monkeypatch):
    canary = "qf_canary_" + "b" * 64
    def reflect(*args, **kwargs):
        assert kwargs["headers"]["X-QF-Proof-Reflect"] == "canary"
        return 200, ('{"fixture":"qf-owned-canary","injected":true,"reflected":"' + canary + '"}').encode()
    monkeypatch.setattr(probe, "exchange", reflect)
    result = probe.request_case("http://fixture.qf.test:8080/allowed", b"fake-capability", reflect=True)
    assert result["response_leak"] is True and result["injected"] is True
    assert canary not in str(result) and "fake-capability" not in str(result)


@pytest.mark.parametrize("body,matched", [
    (b'<html>generic success</html>', False),
    (b'{"error":"failed"}', False),
    (b'[{"id":"c470c6bf-f7cf-4624-9372-bd949c378006","name":"Fresh harmless proof canary"}]', True),
])
def test_admin_shape_distinguishes_listing_from_200_error(monkeypatch, body, matched):
    monkeypatch.setattr(probe, "exchange", lambda *a, **kw: (200, body))
    result = probe.request_case("http://127.0.0.1:10254/v1/secrets", b"fake")
    assert result["admin_listing_shape"] is matched


def test_container_boundaries():
    config = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert all(n["internal"] is True for n in config["networks"].values())
    services = config["services"]
    assert services["actor"]["networks"] == ["actor"]
    assert services["onecli"]["networks"] == ["backend"]
    assert services["db"]["networks"] == ["backend"]
    assert services["gateway-relay"]["networks"] == ["backend", "actor"]
    for service in services.values():
        assert "ports" not in service and "privileged" not in service
        assert "sha256:" in service["image"]
    actor_mounts = " ".join(services["actor"]["volumes"])
    assert "/fixture" not in actor_mounts and "/controller" not in actor_mounts
    assert "docker.sock" not in (ROOT / "compose.yaml").read_text()
    relay = (ROOT / "haproxy.cfg").read_text()
    assert "mode tcp" in relay and "bind :10255" in relay
    assert "10254" not in relay and "5432" not in relay
