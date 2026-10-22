"""Page-level wording and component rules for the Dashboard pages."""

from __future__ import annotations

from dashboard.plain_labels import FAILED_TESTING, LIFECYCLE_LABELS
from dashboard.ui.factory import _stage_word
from dashboard.ui import results as results_page


def test_screened_out_ideas_are_not_called_failed() -> None:
    assert FAILED_TESTING == "Screened out"
    assert "Failed testing" not in LIFECYCLE_LABELS.values()


def test_stat_card_colour_is_never_null(monkeypatch) -> None:
    monkeypatch.setattr(results_page, "load_results_record", lambda run_id: {"metrics": [{"label": "Total Return", "value": "-2.00%"}]})
    monkeypatch.setattr(results_page, "load_trade_view", lambda idea, stage: {"trades": [], "trade_count": 0})
    cards = results_page.top_line({"runs": {"oos": {"run_id": "r"}}})
    assert all(card.children.children[1].c for card in cards)
    assert results_page._signed(3.0) == "teal.4" and results_page._signed(-2.0) == "red.4" and results_page._signed(None) is None


def test_stage_names_use_plain_words() -> None:
    assert _stage_word("oos") == "Unseen data"
    assert _stage_word("walk_forward") == "Holds over time"
    assert _stage_word("custom_stage") == "Custom Stage"


def test_old_idea_links_redirect_to_the_report() -> None:
    import pytest
    app = pytest.importorskip("dashboard.ui.app")
    assert app.legacy_redirect("/candidates", "?candidate_id=qfc 1") == "/report?candidate_id=qfc%201"
    assert app.legacy_redirect("/results", "?run_id=run_7&test=oos") == "/report?run_id=run_7"
    assert app.legacy_redirect("/results", "") is None and app.legacy_redirect("/candidates", None) is None
    assert app.legacy_redirect("/report", "?candidate_id=x") is None and app.legacy_redirect("/factory", "") is None
