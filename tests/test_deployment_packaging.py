from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_runtime_requirements_are_exact_direct_pins():
    requirements = (ROOT / "requirements-runtime.txt").read_text().splitlines()
    pins = [line for line in requirements if line and not line.startswith("#")]
    assert pins
    assert all("==" in requirement for requirement in pins)
    assert "gunicorn==26.2.0" in pins
    assert not any("vectorbtpro" in requirement.lower() for requirement in pins)


def test_container_context_includes_candidate_intake_package():
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()

    assert "!research_intake/" in dockerignore
    assert "!research_intake/**" in dockerignore
    assert "!agent_gateway/" in dockerignore
    assert "!agent_gateway/**" in dockerignore
    assert "!docs/AGENT_RESEARCH_OPERATING_CONTEXT.md" in dockerignore


def test_compose_does_not_package_rejected_dashboard_and_keeps_research_private():
    compose = (ROOT / "compose.yaml").read_text()
    assert "dashboard:" not in compose
    assert "deployment.research_wsgi" not in compose
    assert '"127.0.0.1:8050:8050"' not in compose
    assert "${QF_DEPLOY_ROOT:?set QF_DEPLOY_ROOT}" in compose
    assert "internal: true" in compose
    assert "cap_drop: [ALL]" in compose
    assert "no-new-privileges:true" in compose
    assert "PREFECT_API_URL: http://prefect:4200/api" in compose
    assert "/runtime:/var/lib/quant-factory" in compose
    assert "entrypoint: [prefect]" in compose
    assert "PREFECT_SERVER_ANALYTICS_ENABLED: \"false\"" in compose
    assert "QF_GATEWAY_SOCKET_PATH: /run/quant-factory/agent-gateway.sock" in compose
    assert "QF_GATEWAY_IDENTITY_REGISTRY: /run/secrets/qf-agent-identities.json" in compose
    assert "QF_GATEWAY_AUTHORITIES" not in compose
    assert "HOME: /tmp" in compose
    assert "PREFECT_HOME: /tmp/qf-prefect" in compose
    assert "agent-gateway:" in compose
    assert "ports:" not in compose


def test_gateway_identity_registry_is_provider_neutral_and_configuration_driven(tmp_path):
    server = importlib.import_module("deployment.agent_gateway_server")
    registry = tmp_path / "identities.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "qf_agent_identity_registry_v1",
                "identities": [
                    {
                        "agent_id": "future-local",
                        "provider": "future-provider",
                        "client": "future-client",
                        "transport": "local",
                        "authority_level": 1,
                        "credential_sha256": "a" * 64,
                    },
                    {
                        "agent_id": "remote-agent",
                        "provider": "remote-provider",
                        "client": "remote-client",
                        "transport": "ssh",
                        "authority_level": 0,
                    },
                ],
            }
        )
    )

    registrations = server._identity_registry(registry)

    assert [item.identity.agent_id for item in registrations] == ["future-local", "remote-agent"]
    assert registrations[0].identity.provider == "future-provider"


def test_entrypoint_fails_closed_when_required_mount_configuration_is_missing():
    result = subprocess.run(
        ["sh", str(ROOT / "deployment" / "entrypoint.sh"), "true"],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )

    assert result.returncode != 0
    assert "QUANT_FACTORY_DB_PATH is required" in result.stderr


def test_entrypoint_rejects_database_path_that_escapes_runtime_root(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "state").mkdir(parents=True)
    (runtime / "market-data").mkdir()
    config = tmp_path / "data_locations.local.toml"
    config.write_text("[data]\n")
    result = subprocess.run(
        ["sh", str(ROOT / "deployment" / "entrypoint.sh"), "true"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "QF_RUNTIME_ROOT": str(runtime),
            "QUANT_FACTORY_DB_PATH": str(runtime / "state" / ".." / ".." / "escaped.sqlite3"),
            "QUANT_FACTORY_ARTIFACT_ROOT": str(runtime),
            "QUANT_FACTORY_DATA_LOCATIONS": str(config),
        },
    )

    assert result.returncode != 0
    assert "QUANT_FACTORY_DB_PATH must be an absolute path below" in result.stderr


def test_container_data_configuration_satisfies_catalog_contract():
    from market_data.catalog import load_data_locations
    locations = load_data_locations(ROOT / "deployment/config/data_locations.container.toml.example")
    assert locations.verify_sha256_before_use is True
    assert locations.manifests == Path("/app/data/manifests")
    assert locations.quarantine == locations.root / "quarantine"
