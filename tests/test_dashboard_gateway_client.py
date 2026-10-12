from __future__ import annotations

import hashlib

from dashboard.ui import gateway_client


def test_dashboard_submission_uses_authenticated_content_bound_gateway_request(tmp_path, monkeypatch):
    credential = tmp_path / "dashboard.token"
    credential.write_text("a" * 48)
    monkeypatch.setenv(gateway_client.CREDENTIAL_ENVIRONMENT_VARIABLE, str(credential))
    monkeypatch.setenv(gateway_client.SOCKET_ENVIRONMENT_VARIABLE, "/tmp/qf-test.sock")
    captured = {}

    def send(document, socket_path):
        captured.update(document)
        captured["socket_path"] = socket_path
        return {"ok": True, "result": {"candidate_id": "qfc_exact"}}

    monkeypatch.setattr(gateway_client, "_send", send)
    payload = '{"schema":"qf_candidate_v1"}'
    response = gateway_client.submit_candidate(payload)

    assert response["ok"] is True
    assert captured["credential"] == "a" * 48
    assert captured["operation"] == "candidate.submit"
    assert captured["payload"] == payload
    assert captured["request_id"] == f"qfui_{hashlib.sha256(payload.encode()).hexdigest()[:48]}"
    assert captured["socket_path"] == "/tmp/qf-test.sock"


def test_dashboard_submission_fails_closed_without_gateway_configuration(monkeypatch):
    monkeypatch.delenv(gateway_client.CREDENTIAL_ENVIRONMENT_VARIABLE, raising=False)
    response = gateway_client.submit_candidate("{}")
    assert response["ok"] is False
    assert response["error"]["code"] == "gateway_unavailable"
