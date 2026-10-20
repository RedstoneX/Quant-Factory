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


def _make_store(path: Path, states: list[tuple[str, str]]) -> Path:
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE campaign_events (event_id INTEGER PRIMARY KEY, candidate_id TEXT, state TEXT)")
    connection.executemany("INSERT INTO campaign_events(candidate_id, state) VALUES (?, ?)", states)
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def switched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    calls: list[str] = []
    monkeypatch.delenv("QF_DEPLOY_FORCE", raising=False)
    monkeypatch.setattr(qf_deploy, "read_state", lambda: {})
    monkeypatch.setattr(qf_deploy, "fetch_main", lambda: SHA_B)
    monkeypatch.setattr(qf_deploy, "export_release", lambda revision: tmp_path)
    monkeypatch.setattr(qf_deploy, "infra_drift", lambda release, installed: [])
    monkeypatch.setattr(qf_deploy, "_switch", lambda target, *args, **kwargs: calls.append(target) or 0)
    return calls


def _deploy() -> int:
    return qf_deploy.deploy(None, admin=False, force=False, unpin=False)


def test_deploy_defers_while_an_auto_test_is_running(
    switched: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _make_store(tmp_path / "g.sqlite3", [("a", "queued"), ("a", "running"), ("b", "running"), ("b", "passed")])
    monkeypatch.setattr(qf_deploy, "GATEWAY_DB", store)
    assert _deploy() == 0
    assert switched == []
    assert "deploy deferred: 1 auto-tests running" in capsys.readouterr().out


def test_deploy_proceeds_when_only_queued_or_finished(switched: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = _make_store(tmp_path / "g.sqlite3", [("a", "queued"), ("b", "running"), ("b", "passed")])
    monkeypatch.setattr(qf_deploy, "GATEWAY_DB", store)
    assert _deploy() == 0
    assert switched == [SHA_B]


def test_deploy_proceeds_with_a_warning_when_the_store_is_unreadable(
    switched: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(qf_deploy, "GATEWAY_DB", tmp_path / "missing.sqlite3")
    assert _deploy() == 0
    assert switched == [SHA_B]
    assert "WARNING: cannot read the auto-test store" in capsys.readouterr().out


def test_force_env_deploys_despite_a_running_test(switched: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(qf_deploy, "GATEWAY_DB", _make_store(tmp_path / "g.sqlite3", [("a", "running")]))
    monkeypatch.setenv("QF_DEPLOY_FORCE", "1")
    assert _deploy() == 0
    assert switched == [SHA_B]


def test_licensed_lane_runs_in_a_networkless_throwaway_container_of_the_new_image(tmp_path: Path) -> None:
    command = qf_deploy.licensed_lane_command(tmp_path, SHA_A)

    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--name") + 1] == qf_deploy.licensed_container_name(SHA_A) == f"qf-licensed-{SHA_A[:12]}"
    assert command[command.index("--network") + 1] == "none"
    assert f"{qf_deploy.IMAGE}:{SHA_A}" in command
    assert f"{tmp_path / qf_deploy.TEST_DEPS}:/opt/qf-pytest:ro" in command
    # The image leaves tests out, so the gate mounts the release export's tests.
    assert f"{tmp_path / 'tests'}:/app/tests:ro" in command
    assert command[-2:] == ["-c", qf_deploy.LICENSED_LANE]
    assert "licensed_vectorbt" in qf_deploy.LICENSED_LANE
    assert "'-rfE'" in qf_deploy.LICENSED_LANE  # the short summary names the failing node ids


def test_failed_node_ids_reads_the_short_summary_capped_at_twenty() -> None:
    summary = "\n".join(f"FAILED tests/test_x.py::test_{i} - AssertionError" for i in range(25))
    output = f"F.\n=== short test summary info ===\n{summary}\nERROR tests/test_y.py::test_e\n1 failed in 1.0s\n"

    found = qf_deploy.failed_node_ids(output)

    assert len(found) == 20 and found[0] == "FAILED tests/test_x.py::test_0 - AssertionError"
    assert qf_deploy.failed_node_ids(output, limit=30)[-1] == "ERROR tests/test_y.py::test_e"
    assert qf_deploy.failed_node_ids("...\n3 passed in 1.0s\n") == []


@pytest.mark.parametrize(
    ("output", "failing"),
    [
        ("....\n2 failed, 166 passed, 13 warnings in 264.21s (0:04:24)\n", 2),
        ("E\n1 failed, 80 passed, 3 errors in 9.00s\n", 4),
        ("...\n87 passed in 120.00s\n", 0),
        ("", 0),
    ],
)
def test_failing_count_reads_pytest_summary_line(output: str, failing: int) -> None:
    assert qf_deploy.failing_count(output) == failing


def test_a_failed_licensed_lane_refuses_the_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    subprocess_calls: list[list[str]] = []
    logged: list[str] = []
    monkeypatch.setattr(qf_deploy, "run", lambda *args, **_: calls.append(args) or "")
    monkeypatch.setattr(qf_deploy, "log", logged.append)
    monkeypatch.setattr(
        qf_deploy.subprocess,
        "run",
        lambda args, **__: subprocess_calls.append(list(args)) or qf_deploy.subprocess.CompletedProcess(
            args, 1, stdout="F\nFAILED tests/test_x.py::test_a - AssertionError\n1 failed, 5 passed in 1.00s\n"),
    )

    with pytest.raises(qf_deploy.DeployError, match=rf"licensed tests failed on {SHA_A[:12]}: 1 failing"):
        qf_deploy.verify_image(tmp_path, SHA_A, tmp_path / "venv")
    assert "--target" in calls[0] and "pytest" in calls[0]
    # A leftover container from a timed-out run is removed before the lane starts.
    assert subprocess_calls[0] == ["docker", "rm", "-f", f"qf-licensed-{SHA_A[:12]}"]
    assert subprocess_calls[1][:2] == ["docker", "run"]
    assert "FAILED tests/test_x.py::test_a - AssertionError" in logged
