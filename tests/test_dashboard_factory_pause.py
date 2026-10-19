"""Pause / Resume testing on the Factory page: state text, log rows, missing-table fallback, and the button callbacks."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dashboard.factory_history import control_log_rows, log_rows
from dashboard.factory_overview import header_pill, headline_for, read_campaign_control
from dashboard.ui import factory_oversight as page

NOW = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)


def _data(**over) -> dict:
    base = {"available": True, "paused": None, "running": [], "last_test": None, "headline": "x", "headline_tone": "text", "pill": header_pill(running=0, draining=False, last_finished_crashed=False)}
    return {**base, **over}


def _control_db(path: Path, rows: list[tuple[int, str]]) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE campaign_control (event_id INTEGER PRIMARY KEY AUTOINCREMENT, paused INTEGER NOT NULL, actor TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL)")
    con.executemany("INSERT INTO campaign_control(paused, actor, reason, created_at) VALUES (?, 'dashboard', 'from dashboard', ?)", rows)
    return con


def test_pill_and_headline_when_paused_from_dashboard() -> None:
    assert header_pill(running=0, draining=False, last_finished_crashed=False, paused=True) == {"label": "Paused", "tone": "amber"}
    assert header_pill(running=1, draining=True, last_finished_crashed=False, paused=True)["label"] == "Paused"  # both: dashboard wins
    assert header_pill(running=1, draining=True, last_finished_crashed=False)["label"] == "Paused for update"  # drain stays distinct
    assert headline_for(running=1, waiting=3, looks=2, warnings=1, paused_since="14:05") == ("Paused from dashboard since 14:05. 3 waiting.", "amber")


def test_running_card_text_when_idle_and_paused_and_when_a_test_is_finishing() -> None:
    idle = page.running_cards(_data(paused={"since": "14:05"}))
    assert idle[0].children == "Paused — the line is held, nothing lost."
    assert "Idle" in str(page.running_cards(_data())[0].children)
    card = {"name": "Idea", "candidate_id": None, "elapsed": "3m 00s", "slow": False, "steps": ["done", "current", "todo", "todo", "todo"], "where": "Step 2 of 5 · Test", "note": "finishing; nothing new will start"}
    finishing = page.running_cards(_data(paused={"since": "14:05"}, running=[card]))
    assert "finishing; nothing new will start" in str(finishing)


def test_button_is_outlined_pause_until_paused_then_filled_resume() -> None:
    assert page.pause_button_props(_data()) == ("Pause testing", "outline", "gray")
    assert page.pause_button_props(_data(paused={"since": "14:05"})) == ("Resume testing", "filled", "indigo")


def test_log_rows_come_from_campaign_control_with_grey_dots(tmp_path: Path) -> None:
    con = _control_db(tmp_path / "g.sqlite3", [(1, "2026-10-19T18:05:00+00:00"), (0, "2026-10-19T19:00:00+00:00")])
    rows = read_campaign_control(con, NOW, {"campaign_control"})
    assert [r["paused"] for r in rows] == [0, 1]  # newest first
    log = log_rows([], {}, {}, [], NOW, rows)
    assert [(r["text"], r["tone"]) for r in log] == [("Testing resumed from dashboard", "grey"), ("Testing paused from dashboard", "grey")]
    assert log[1]["t"] == "14:05"  # Eastern
    assert control_log_rows([]) == []


def test_missing_campaign_control_table_means_not_paused(tmp_path: Path) -> None:
    con = sqlite3.connect(tmp_path / "old.sqlite3")
    con.row_factory = sqlite3.Row
    assert read_campaign_control(con, NOW, set()) == []


def test_press_when_running_opens_the_confirm_without_calling_the_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page.gateway_client, "pause_campaign", lambda reason: pytest.fail("must wait for the confirm"))
    assert page.handle_pause_action("fo-pause-btn", False)[0] is True
    assert page.handle_pause_action("fo-pause-cancel", False)[0] is False


def test_confirm_pauses_and_resume_needs_no_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(page.gateway_client, "pause_campaign", lambda reason: calls.append(("pause", reason)) or {"ok": True})
    monkeypatch.setattr(page.gateway_client, "resume_campaign", lambda: calls.append(("resume",)) or {"ok": True})
    opened, stamp, notice = page.handle_pause_action("fo-pause-confirm", False)
    assert (opened, notice) == (False, []) and isinstance(stamp, float)
    page.handle_pause_action("fo-pause-btn", True)
    assert calls == [("pause", "from dashboard"), ("resume",)]


def test_gateway_failure_shows_plain_words_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    down = {"ok": False, "error": {"code": "gateway_unavailable", "message": "socket closed"}}
    monkeypatch.setattr(page.gateway_client, "pause_campaign", lambda reason: down)
    monkeypatch.setattr(page.gateway_client, "resume_campaign", lambda: down)
    for trigger, paused in (("fo-pause-confirm", False), ("fo-pause-btn", True)):
        opened, stamp, notice = page.handle_pause_action(trigger, paused)
        assert opened is False and stamp is page.no_update
        assert "nothing was changed" in str(notice)
