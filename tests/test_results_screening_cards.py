"""Screening-only runs show their real aggregate metrics without a trade ledger."""

from types import SimpleNamespace

from dashboard.application import _evidence_outcome_value, _primary_metric_cards
from dashboard.run_detail_adapter import DetailField


def test_screening_cards_label_database_metrics_when_trade_artifact_is_absent():
    detail = SimpleNamespace(evidence=SimpleNamespace(
        metrics=(
            DetailField("Total Return", "4.59%"),
            DetailField("Maximum Drawdown", "-3.16%"),
            DetailField("Sharpe Ratio", "0.472"),
            DetailField("Number Of Trades", "1645"),
        ),
        trades=(),
    ))
    cards = _primary_metric_cards(detail)
    text = " ".join(str(child.children) for article in cards.children for child in article.children)
    assert "Sharpe ratio" in text and "0.472" in text
    assert "Screened trades" in text and "1645" in text
    assert "trade ledger unavailable" in text


def test_fixed_screening_result_is_reported_as_screened_out_without_artifacts():
    detail = SimpleNamespace(
        evidence=SimpleNamespace(validation_outcome=(), validation=()),
        result_summary=SimpleNamespace(table_rows=({"screening_status": "screened_out"},)),
    )
    assert _evidence_outcome_value(detail) == "Screened out"
