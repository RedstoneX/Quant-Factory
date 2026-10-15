from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_gateway import auto_campaign
from deployment.release import qf_deploy
from tests.test_auto_campaign import Harness
from tests.test_qf_deploy import SHA_B, _deploy, _make_store, switched  # noqa: F401  (switched is a fixture)


@pytest.fixture
def marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "deploy-drain"
    monkeypatch.setattr(qf_deploy, "DRAIN_MARKER", path)
    monkeypatch.setattr(auto_campaign, "DRAIN_MARKER", path)
    return path


def test_marker_set_when_deploy_is_deferred(switched, monkeypatch, tmp_path, marker) -> None:  # noqa: F811
    monkeypatch.setattr(qf_deploy, "GATEWAY_DB", _make_store(tmp_path / "g.sqlite3", [("a", "running")]))
    assert _deploy() == 0
    assert switched == [] and marker.exists()


def test_marker_cleared_when_deploy_proceeds(switched, monkeypatch, tmp_path, marker) -> None:  # noqa: F811
    marker.write_text("x")
    monkeypatch.setattr(qf_deploy, "GATEWAY_DB", _make_store(tmp_path / "g.sqlite3", [("a", "passed")]))
    assert _deploy() == 0
    assert switched == [SHA_B] and not marker.exists()


def test_force_env_still_deploys_and_clears_marker(switched, monkeypatch, tmp_path, marker) -> None:  # noqa: F811
    marker.write_text("x")
    monkeypatch.setattr(qf_deploy, "GATEWAY_DB", _make_store(tmp_path / "g.sqlite3", [("a", "running")]))
    monkeypatch.setenv("QF_DEPLOY_FORCE", "1")
    assert _deploy() == 0
    assert switched == [SHA_B] and not marker.exists()


def test_campaign_starts_nothing_while_marker_present(tmp_path, marker) -> None:
    marker.write_text("x")
    harness = Harness(tmp_path)
    harness.draft("idea_drain001")
    harness.campaign().run_once()
    assert harness.launches == []
    marker.unlink()
    harness.campaign().run_once()
    assert len(harness.launches) == 1


def test_running_test_finishes_but_next_one_waits(tmp_path, marker) -> None:
    harness = Harness(tmp_path)
    harness.draft("idea_drain002")
    harness.draft("idea_drain003", symbol="MNQ")

    def executor(request):
        marker.write_text("x")  # the deploy defers while this test runs
        return harness.executor(request)

    harness.campaign(executor).run_once()
    assert len(harness.launches) == 1  # the running test completed; the second did not start


def test_stale_marker_is_ignored(tmp_path, marker, capsys) -> None:
    marker.write_text("x")
    old = marker.stat().st_mtime - auto_campaign.DRAIN_STALE_SECONDS - 60
    os.utime(marker, (old, old))
    assert auto_campaign.drain_requested() is False
    assert "ignoring it" in capsys.readouterr().err
    harness = Harness(tmp_path)
    harness.draft("idea_drain004")
    harness.campaign().run_once()
    assert len(harness.launches) == 1
