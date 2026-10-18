from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading

import pandas as pd
import pytest

from agent_gateway import cli
from agent_gateway.contracts import GatewayIdentity, GatewayRequest
from agent_gateway.service import AgentResearchGateway
from agent_gateway.socket_server import GatewayUnixServer, IdentityRegistration, PeerPolicy
from agent_gateway.ssh_command import allowed_arguments
from market_data.catalog import DataLocations

DATASET = "equities_SPY_1m_alpaca_sip"
TOKEN = "codex-test-token-0000000000000000"
READER = GatewayIdentity("grok-remote", "xai", "grok", "ssh", 0, 2222)


def _store(tmp_path: Path) -> DataLocations:
    root = tmp_path / "market-data"
    slot = root / "equities" / "SPY" / "1m" / "SPY_1m_alpaca_sip.b.parquet"
    slot.parent.mkdir(parents=True)
    stamps = pd.date_range("2026-10-16 13:30", periods=5, freq="1min", tz="UTC")
    pd.DataFrame({"timestamp": stamps, "close": [1.0, 2.0, 3.0, 4.0, 5.0]}).to_parquet(slot)
    (root / "equities" / "SPY" / "1m" / "SPY_1m_alpaca_sip.a.parquet").write_bytes(b"being written")
    relative = slot.relative_to(root).as_posix()
    manifest = {
        "dataset_id": DATASET,
        "status": "validated",
        "asset_class": "equity",
        "symbol": "SPY",
        "provider": "alpaca",
        "timeframe": "1m",
        "format": "parquet",
        "canonical_relative_path": relative,
        "local_canonical_path": relative,
        "sha256": hashlib.sha256(slot.read_bytes()).hexdigest(),
        "size_bytes": slot.stat().st_size,
        "row_count": 5,
        "full_stored_coverage": {"first_timestamp": stamps[0].isoformat(), "last_timestamp": stamps[-1].isoformat(), "row_count": 5},
    }
    (root / "manifests").mkdir()
    (root / "manifests" / f"{DATASET}.json").write_text(json.dumps(manifest))
    return DataLocations(root, root / "manifests", root / "quarantine", None, None, True)


def _gateway(tmp_path: Path) -> AgentResearchGateway:
    return AgentResearchGateway(
        database=tmp_path / "qf.sqlite3",
        gateway_database=tmp_path / "gateway.sqlite3",
        artifact_root=tmp_path / "artifacts",
        data_locations=_store(tmp_path),
    )


def _request(operation: str, arguments: dict | None = None) -> GatewayRequest:
    return GatewayRequest("req_data_0000000001", operation, arguments or {}, None)


def test_data_files_lists_committed_slot_from_manifest(tmp_path):
    response = _gateway(tmp_path).handle(_request("data.files"), READER)
    assert response.ok is True
    (entry,) = response.result["datasets"]
    slot = tmp_path / "market-data" / "equities" / "SPY" / "1m" / "SPY_1m_alpaca_sip.b.parquet"
    assert entry["dataset_id"] == DATASET and entry["symbol"] == "SPY" and entry["timeframe"] == "1m"
    assert entry["row_count"] == 5 and entry["size_bytes"] == slot.stat().st_size
    assert entry["sha256"] == hashlib.sha256(slot.read_bytes()).hexdigest()
    assert entry["first_bar"].startswith("2026-10-16T13:30") and "path" not in json.dumps(entry)


@pytest.mark.parametrize("dataset_id", ["equities_XYZ_1m_alpaca_sip", "../x", "../market-data/manifests/" + DATASET, None])
def test_data_download_refuses_unknown_and_path_like_ids(tmp_path, dataset_id):
    response = _gateway(tmp_path).handle(_request("data.download", {"dataset_id": dataset_id}), READER)
    assert response.ok is False and response.attachment is None
    assert response.error["code"] == "unknown_dataset"


def test_ssh_forced_command_accepts_data_commands():
    assert allowed_arguments("qf-agent data files") == ["data", "files"]
    assert allowed_arguments(f"qf-agent data download {DATASET}") == ["data", "download", DATASET]
    with pytest.raises(ValueError):
        allowed_arguments(f"qf-agent data download {DATASET} extra")


def test_data_download_streams_bytes_matching_listed_sha256(tmp_path, capfdbinary):
    gateway = _gateway(tmp_path)
    listed = gateway.handle(_request("data.files"), READER).result["datasets"][0]
    socket_path = tmp_path / "agent-gateway.sock"
    policy = PeerPolicy(
        local_uids={os.getuid()},
        remote_uid=99999,
        registrations=(
            IdentityRegistration(GatewayIdentity("codex-local", "openai", "codex", "local", 2), hashlib.sha256(TOKEN.encode()).hexdigest()),
            IdentityRegistration(GatewayIdentity("grok-remote", "xai", "grok", "ssh", 1)),
        ),
    )
    credential = tmp_path / "credential"
    credential.write_text(TOKEN)
    server = GatewayUnixServer(socket_path, gateway=gateway, peer_policy=policy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status = cli.main(["--socket", str(socket_path), "--credential-file", str(credential), "data", "download", DATASET])
        captured = capfdbinary.readouterr()
        refused = cli.main(["--socket", str(socket_path), "--credential-file", str(credential), "data", "download", "../x"])
        refusal = capfdbinary.readouterr()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert status == 0
    assert hashlib.sha256(captured.out).hexdigest() == listed["sha256"]
    assert len(captured.out) == listed["size_bytes"]
    assert json.loads(captured.err)["result"]["dataset"]["sha256"] == listed["sha256"]
    assert refused == 1 and refusal.out == b""
    assert json.loads(refusal.err)["error"]["code"] == "unknown_dataset"
