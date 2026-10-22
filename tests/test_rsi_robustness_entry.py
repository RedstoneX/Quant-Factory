from pathlib import Path

import backtesting.run_rsi_robustness as entry
from backtesting.robustness import read_robustness_report, write_robustness_report


def test_missing_candidate_artifacts_report_insufficient(monkeypatch, tmp_path):
    monkeypatch.setattr(
        entry,
        "ARTIFACTS",
        (tmp_path / "missing-oos.json", tmp_path / "missing-walk.json"),
    )
    result = entry.run()
    assert result.status == "insufficient_evidence"
    assert any("missing" in reason for reason in result.reasons)


def test_current_rsi_artifacts_report_insufficient_and_round_trip(tmp_path):
    result = entry.run()
    assert result.status == "insufficient_evidence"
    assert result.locked_parameters == {}
    assert any("rsi_spy_oos.json" in reason for reason in result.reasons)
    path = tmp_path / "robustness.json"
    write_robustness_report(path, result.to_dict())
    payload = read_robustness_report(path)
    assert payload["status"] == "insufficient_evidence"
    text = path.read_text()
    assert "NaN" not in text and "Infinity" not in text
