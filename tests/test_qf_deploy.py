from __future__ import annotations

from pathlib import Path

import pytest

from deployment.release import qf_deploy

SHA_A = "a" * 40
SHA_B = "b" * 40


def test_set_env_revision_replaces_only_the_revision_line() -> None:
    text = "QF_DEPLOY_ROOT=/opt/x\nQF_REVISION=" + SHA_A + "\nOTHER=1\n"

    updated = qf_deploy.set_env_revision(text, SHA_B)

    assert updated == "QF_DEPLOY_ROOT=/opt/x\nQF_REVISION=" + SHA_B + "\nOTHER=1\n"
    assert qf_deploy.env_revision(updated) == SHA_B


@pytest.mark.parametrize("text", ["OTHER=1\n", f"QF_REVISION={SHA_A}\nQF_REVISION={SHA_B}\n"])
def test_set_env_revision_refuses_missing_or_ambiguous_revision(text: str) -> None:
    with pytest.raises(qf_deploy.DeployError, match="exactly one QF_REVISION"):
        qf_deploy.set_env_revision(text, SHA_B)


def test_set_env_revision_refuses_anything_but_a_full_sha() -> None:
    with pytest.raises(qf_deploy.DeployError, match="full commit sha"):
        qf_deploy.set_env_revision(f"QF_REVISION={SHA_A}\n", "main")


def test_env_revision_ignores_a_malformed_value() -> None:
    assert qf_deploy.env_revision("QF_REVISION=latest\n") is None


def test_infra_drift_reports_only_changed_privileged_files(tmp_path: Path) -> None:
    release, installed = tmp_path / "release", tmp_path / "installed"
    (release / "unit").mkdir(parents=True)
    installed.mkdir()
    (release / "compose.yaml").write_text("same\n")
    (release / "unit" / "a.service").write_text("new\n")
    (installed / "compose.yaml").write_text("same\n")
    (installed / "a.service").write_text("old\n")

    drift = qf_deploy.infra_drift(
        release, {"compose.yaml": installed / "compose.yaml", "unit/a.service": installed / "a.service"}
    )

    assert drift == ["unit/a.service"]


def test_infra_drift_refuses_a_symlinked_source(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    (release / "compose.yaml").symlink_to("/etc/hostname")

    with pytest.raises(qf_deploy.DeployError, match="regular tracked file"):
        qf_deploy.infra_drift(release, {"compose.yaml": tmp_path / "compose.yaml"})


def test_requirements_key_changes_with_requirements(tmp_path: Path) -> None:
    for name in qf_deploy.REQUIREMENTS:
        (tmp_path / name).write_text("dash==4.3.0\n")
    before = qf_deploy.requirements_key(tmp_path)
    (tmp_path / qf_deploy.REQUIREMENTS[1]).write_text("dash==4.3.1\n")

    assert qf_deploy.requirements_key(tmp_path) != before


def test_installed_dashboard_unit_runs_the_deployed_release() -> None:
    unit = Path(__file__).resolve().parents[1] / "deployment" / "dashboard" / qf_deploy.UNIT_NAME
    text = unit.read_text()

    assert "WorkingDirectory=/opt/quant-factory-dashboard/current\n" in text
    assert "ExecStart=/opt/quant-factory-dashboard/current/.venv/bin/gunicorn " in text
    assert "/home/" not in text


def _stub_deploy(monkeypatch: pytest.MonkeyPatch, busy: int) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(qf_deploy, "read_state", lambda: {})
    monkeypatch.setattr(qf_deploy, "fetch_main", lambda: SHA_B)
    monkeypatch.setattr(qf_deploy, "export_release", lambda revision: Path("/nonexistent"))
    monkeypatch.setattr(qf_deploy, "infra_drift", lambda release, installed: [])
    monkeypatch.setattr(qf_deploy, "active_flow_runs", lambda: busy)
    monkeypatch.setattr(qf_deploy, "_switch", lambda *args, **kwargs: calls.append("switch") or 0)
    monkeypatch.setattr(qf_deploy, "write_state", lambda **changes: calls.append("write_state"))
    return calls


def test_deploy_defers_while_tests_are_running(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_deploy(monkeypatch, busy=3)

    assert qf_deploy.deploy(None, admin=False, force=False, unpin=False) == 0
    assert calls == []


def test_deploy_proceeds_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_deploy(monkeypatch, busy=0)

    assert qf_deploy.deploy(None, admin=False, force=False, unpin=False) == 0
    assert calls == ["switch"]


def test_active_flow_runs_counts_the_prefect_cli_json(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(qf_deploy, "compose", lambda *args, capture=False: seen.append(args) or '[{"id": "1"}, {"id": "2"}]')

    assert qf_deploy.active_flow_runs() == 2
    assert "RUNNING" in seen[0] and "PENDING" in seen[0]
