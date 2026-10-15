"""Recorded scores on the Ideas, Results and Dashboard pages."""

from __future__ import annotations

import sqlite3

from dashboard import score_projection
from dashboard.ui.scores import SHORTLIST_COLUMNS, score_cards


def _texts(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, (list, tuple)):
        return [text for child in node for text in _texts(child)]
    return _texts(getattr(node, "children", None)) if node is not None else []


def test_scores_read_from_rolling_and_stress_evidence(monkeypatch):
    rolling = {
        "folds": [
            {"test_metrics": {"total_return": 0.02, "sharpe_ratio": 1.0}},
            {"test_metrics": {"total_return": -0.01, "sharpe_ratio": -0.5}},
            {"test_metrics": {}},
            {"test_metrics": {"total_return": 0.03, "sharpe_ratio": 1.5}},
        ],
        "normalized_evidence": {"status": "failed"},
        "idea_overfitting": {"deflated_sharpe_probability": 0.91, "pbo": 0.4},
    }
    docs = {"walk_forward": rolling, "robustness": {"normalized_evidence": {"status": "passed"}},
            "monte_carlo": {"normalized_evidence": {"status": "failed"}}}
    monkeypatch.setattr(score_projection, "_evidence", lambda db, conn, cfg, stage: docs[stage])
    scores = score_projection._scores(None, sqlite3.connect(":memory:"), "cfg")
    assert scores["folds_profitable"] == 2 and scores["folds_total"] == 4 and scores["folds_share"] == 0.5
    assert round(scores["fold_sharpe"], 3) == 0.667
    assert scores["stress_status"] == "failed" and scores["rolling_status"] == "failed"
    assert scores["luck"] == 0.91 and scores["overfitting"] == 0.4


def test_missing_scores_are_dashes_and_failed_scores_are_amber():
    assert _texts(score_cards(None)).count("—") >= 4
    cards = score_cards({**score_projection.EMPTY_SCORES, "folds_profitable": 1, "folds_total": 4, "folds_share": .25,
                         "fold_sharpe": -.2, "rolling_status": "failed", "stress_status": "failed"})
    assert {"1 of 4", "25%", "Weak"} <= set(_texts(cards))
    assert "yellow.5" in repr(cards[0]) and "red" not in repr(cards)


def test_shortlist_columns_have_plain_headers_and_tooltips():
    scored = [c for c in SHORTLIST_COLUMNS if c["field"] in {"sharpe", "folds_share", "fold_sharpe", "stress_status", "luck", "overfitting"}]
    assert len(scored) == 6 and all(c["headerTooltip"] and c["headerName"] for c in scored)
    assert next(c for c in SHORTLIST_COLUMNS if c["field"] == "sharpe")["sort"] == "desc"


def test_shortlist_idea_name_wraps_instead_of_truncating():
    title = next(c for c in SHORTLIST_COLUMNS if c["field"] == "title")
    assert title["wrapText"] and title["autoHeight"] and title["cellStyle"]["whiteSpace"] == "normal"


def test_waiting_banner_text():
    assert score_projection.waiting_banner_text({"review": 0, "decision": 0}) is None
    assert score_projection.waiting_banner_text({"review": 2, "decision": 1}) == (
        "Waiting for you: 2 ideas passed every test and need your review; 1 idea on hold for your decision")
    assert "1 idea passed every test and needs your review" in score_projection.waiting_banner_text({"review": 1})
