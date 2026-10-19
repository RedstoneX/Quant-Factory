"""New idea page: batch review, token sentence, line position and estimate, button state, post-submit text."""

from __future__ import annotations

import json
from pathlib import Path

from dashboard.new_idea_projection import BUDGET, bar_text, button, review_batch, rule_tokens, source_label, submitted_state, where_they_go
from dashboard.submit_projection import validate_candidate_text

INTAKE = Path(__file__).resolve().parents[1] / "research_intake"


def _row(name: str) -> dict:
    return validate_candidate_text((INTAKE / name).read_text(encoding="utf-8"), filename=name)


def _bad_row() -> dict:
    packet = json.loads((INTAKE / "mes_orb_parameter_grid_candidate.json").read_text(encoding="utf-8"))
    packet["candidate"]["title"] = "Broken idea"
    packet["variables"]["range_minutes"]["values"] = []
    return validate_candidate_text(json.dumps(packet), filename="broken.json")


def _batch() -> dict:
    return {"rows": [_row("mes_sma_10_30_candidate.json"), _row("mes_orb_parameter_grid_candidate.json"), _bad_row()]}


def _overview(running: int = 1, waiting: int = 2, typical: float | None = 7.0) -> dict:
    return {"running": [{"name": f"Run {i}"} for i in range(running)], "typical_minutes": typical,
            "queue": {"total": waiting, "next": [{"name": f"Wait {i}"} for i in range(waiting)][:4]}}


def test_counts_and_budget_bar():
    review = review_batch(_batch())
    assert (review["total"], review["ready"], review["left_out"]) == (3, 2, 1)
    assert review["combinations"] == 1 + 42  # an idea with nothing varied is one test; the grid is 7 x 3 x 2
    assert review["budget_text"] == f"43 of {BUDGET:,} allowed"
    assert 0 < review["budget_percent"] < 1 and not review["over_budget"]
    assert len(review["submit_rows"]) == 2


def test_needs_fixing_card_says_what_is_wrong_with_that_idea():
    card = review_batch(_batch())["cards"][2]
    assert (card["ready"], card["tokens"]) == (False, [])
    assert card["problem"] == "variable must define a non-empty bounded values list"
    assert "file" not in card["problem"]


def test_one_bad_idea_does_not_block_the_others():
    review = review_batch(_batch())
    assert [row["title"] for row in review["submit_rows"]] == ["MES intraday 10/30 SMA crossover", "MES opening-range breakout parameter grid"]


def test_source_only_when_the_file_records_it():
    cards = review_batch(_batch())["cards"]
    assert cards[0]["meta"].startswith("trend following") and "From" not in cards[0]["meta"]
    assert cards[1]["meta"].startswith("From Codex")
    assert source_label({"sources": [{"creator": "Terry"}]}) == ""
    assert source_label({"sources": [{"collected_by": "Grok (xAI)"}]}) == "From Grok"


def test_sentence_marks_fixed_and_ranges():
    document = json.loads(_row("mes_orb_parameter_grid_candidate.json")["canonical_json"])
    tokens = rule_tokens(document)
    assert {"kind": "fixed", "text": "MES"} in tokens and {"kind": "fixed", "text": "5m bars"} in tokens
    assert {"kind": "range", "text": "5–60"} in tokens  # range_minutes
    assert {"kind": "range", "text": "long / short"} in tokens  # words, not numbers
    assert all(t["kind"] != "range" or t["text"] != "5m" for t in tokens)


def test_line_places_and_estimates():
    rows = where_they_go(_overview(), ready=3)
    assert [(r["n"], r["kind"], r["when"]) for r in rows] == [("1", "running", "now"), ("2", "waiting", "~7 min"), ("3", "waiting", "~14 min"), ("4", "yours", "~21 min")]
    assert rows[-1]["name"] == "Your 3 ideas"
    assert where_they_go(_overview(0, 0), ready=1)[-1] == {"n": "1", "name": "Your 1 idea", "when": "now", "kind": "yours"}
    assert [r["kind"] for r in where_they_go(_overview(1, 6), ready=0)][-1] == "more"


def test_bar_text_and_button():
    review = review_batch(_batch())
    assert bar_text(review, _overview()) == "2 ready · 1 left out · first starts in about 21 min"
    assert bar_text(review, _overview(0, 0)).endswith("first starts right away")
    assert button(review, True) == ("Submit and test 2 ideas", False)
    assert button(review, False) == ("Submit and test 2 ideas", True)  # gateway not ready
    assert button(review_batch(None), True) == ("Submit and test ideas", True)  # nothing ready
    one = review_batch({"rows": [_row("mes_sma_10_30_candidate.json")]})
    assert button(one, True)[0] == "Submit and test 1 idea"


def test_after_submit_lists_each_idea():
    responses = [{"ok": True, "result": {"candidate_id": "a"}}, {"ok": True, "result": {"candidate_id": "b", "duplicate": True}}, {"ok": False, "error": {"message": "nope"}}]
    state = submitted_state(responses, _overview(), ["A", "B", "C"])
    assert state["text"] == "Queued · #4 in line · starts in ~21 min"
    assert [n["text"] for n in state["notes"]] == ["A — queued", "B — already tested — not queued again", "C — failed to submit: nope"]
    assert state["queued"] == 1
    assert submitted_state([{"ok": True, "result": {"duplicate": True}}], _overview())["text"] == "Nothing new was queued"
