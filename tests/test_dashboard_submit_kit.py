from __future__ import annotations

import json

from dashboard.ui import submit
from research_intake.starter_kit import starter_kit


def test_starter_kit_download_is_one_json_file_with_schema_example_and_guide():
    document = json.loads(submit.starter_kit_json())
    assert set(document) == {"schema", "example", "guide", "indicators"}
    assert document == json.loads(json.dumps(starter_kit()))
    assert document["guide"]


def test_starter_kit_example_is_itself_valid():
    example = json.loads(submit.starter_kit_json())["example"]
    row = submit.validate_candidate_text(json.dumps(example), filename="example.json")
    assert row["valid"] is True


def test_submit_page_offers_starter_kit_not_schema_button():
    page = str(submit.submit_layout())
    assert "Download starter kit" in page
    assert "Download schema" not in page


def test_download_callback_serves_the_kit(monkeypatch):
    sent = {}
    monkeypatch.setattr(submit.dcc, "send_string", lambda content, name: sent.update(content=content, name=name) or {"ok": 1})
    from dash import Dash

    app = Dash(__name__)
    submit.register_submit_callbacks(app)
    fn = next(v["callback"] for k, v in app.callback_map.items() if k.startswith("submit-download-file"))
    fn = getattr(fn, "__wrapped__", fn)
    fn(1)
    assert sent["name"].endswith(".json")
    assert json.loads(sent["content"]).keys() == {"schema", "example", "guide", "indicators"}


def test_after_submit_shows_status_and_link():
    notice = submit.submitted_notice({"candidate_id": "qfc_abc"}, status=("Testing", "Waiting for its turn to be tested"))
    text = str(notice)
    assert "Submitted · Testing" in text
    assert "Waiting for its turn to be tested" in text
    assert "/candidates?candidate_id=qfc_abc" in text


def test_valid_but_not_submittable_says_why_in_plain_words():
    row = {"valid": True, "review_ready": False, "canonical_json": "{}", "issues": [{"severity": "warning", "path": "$.x", "message": "no rules given"}]}
    reason = submit.not_submittable_reason(row)
    assert "not ready to submit" in reason
    assert "no rules given" in reason
    assert submit.not_submittable_reason({"valid": True, "review_ready": True, "canonical_json": "{}"}) == ""
    assert "errors" in submit.not_submittable_reason({"valid": False, "review_ready": False, "issues": []})
