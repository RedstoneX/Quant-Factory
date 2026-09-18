from __future__ import annotations

import importlib
import sqlite3
import subprocess
from pathlib import Path

import pytest
from flask import Flask


ROOT = Path(__file__).parents[1]


def test_runtime_requirements_are_exact_direct_pins():
    requirements = (ROOT / "requirements-runtime.txt").read_text().splitlines()
    pins = [line for line in requirements if line and not line.startswith("#")]
    assert pins
    assert all("==" in requirement for requirement in pins)
    assert "gunicorn==26.2.0" in pins
    assert not any("vectorbtpro" in requirement.lower() for requirement in pins)


def test_compose_binds_dashboard_only_to_loopback_and_uses_external_root():
    compose = (ROOT / "compose.yaml").read_text()
    assert '"127.0.0.1:8050:8050"' in compose
    assert "${QF_DEPLOY_ROOT:?set QF_DEPLOY_ROOT}" in compose
    assert "vectorbt_private:" in compose
    assert "internal: true" in compose
    assert "cap_drop: [ALL]" in compose
    assert "no-new-privileges:true" in compose
    assert "PREFECT_API_URL: http://prefect:4200/api" in compose
    assert "/runtime:/var/lib/quant-factory" in compose
    assert "entrypoint: [prefect]" in compose
    assert "PREFECT_SERVER_ANALYTICS_ENABLED: \"false\"" in compose


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


def test_build_dashboard_app_propagates_explicit_external_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANT_FACTORY_DB_PATH", str(tmp_path / "state" / "qf.sqlite3"))
    monkeypatch.setenv("QUANT_FACTORY_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    wsgi = importlib.import_module("deployment.research_wsgi")
    captured = {}

    class Adapter:
        def __init__(self, **kwargs):
            captured["adapter"] = kwargs

    def fake_create_app(**kwargs):
        captured["create_app"] = kwargs
        return object()

    monkeypatch.setattr(wsgi, "RunDetailDashboardAdapter", Adapter)
    monkeypatch.setattr(wsgi, "create_app", fake_create_app)

    wsgi.build_dashboard_app()

    expected_database = tmp_path / "state" / "qf.sqlite3"
    assert captured["create_app"]["review_database"] == expected_database
    assert captured["adapter"] == {
        "database": expected_database,
        "artifact_root": tmp_path / "artifacts",
    }


@pytest.mark.parametrize("value", [None, "relative.sqlite3"])
def test_build_dashboard_app_fails_closed_for_missing_or_relative_database(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("QUANT_FACTORY_DB_PATH", raising=False)
    else:
        monkeypatch.setenv("QUANT_FACTORY_DB_PATH", value)
    monkeypatch.setenv("QUANT_FACTORY_ARTIFACT_ROOT", "/var/lib/quant-factory/artifacts")
    wsgi = importlib.import_module("deployment.research_wsgi")
    with pytest.raises(RuntimeError, match="QUANT_FACTORY_DB_PATH"):
        wsgi.build_dashboard_app()


def test_health_is_unhealthy_when_database_is_missing(tmp_path):
    wsgi = importlib.import_module("deployment.research_wsgi")
    server = Flask(__name__)
    wsgi.register_health_endpoint(server, tmp_path / "missing.sqlite3")

    response = server.test_client().get("/healthz")

    assert response.status_code == 503
    assert response.json["status"] == "unhealthy"
    assert set(response.json) == {"status", "revision"}


def test_health_uses_read_only_database_check(tmp_path):
    wsgi = importlib.import_module("deployment.research_wsgi")
    database = tmp_path / "state.sqlite3"
    from persistence.database import initialize_database

    connection = initialize_database(database)
    connection.close()
    before = database.stat().st_mtime_ns
    server = Flask(__name__)
    wsgi.register_health_endpoint(server, database)

    response = server.test_client().get("/healthz")

    assert response.status_code == 200
    assert response.json["status"] == "healthy"
    assert database.stat().st_mtime_ns == before


def test_health_rejects_database_without_quant_factory_schema(tmp_path):
    wsgi = importlib.import_module("deployment.research_wsgi")
    database = tmp_path / "wrong-schema.sqlite3"
    sqlite3.connect(database).close()
    server = Flask(__name__)
    wsgi.register_health_endpoint(server, database)

    response = server.test_client().get("/healthz")

    assert response.status_code == 503
    assert response.json["status"] == "unhealthy"


def test_container_data_configuration_satisfies_catalog_contract():
    from market_data.catalog import load_data_locations
    locations = load_data_locations(ROOT / "deployment/config/data_locations.container.toml.example")
    assert locations.verify_sha256_before_use is True
    assert locations.manifests == Path("/app/data/manifests")
    assert locations.quarantine == locations.root / "quarantine"
