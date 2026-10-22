"""Focused configuration-level Results projection proof."""

from pathlib import Path

from dashboard.results_projection import load_screening_configuration_evidence
from persistence import ArtifactType, canonical_json
from tests.test_artifact_contracts import _service_with_run


def _register_document(service, root: Path, *, name: str, artifact_type: ArtifactType, document: dict) -> None:
    content = (canonical_json(document) + "\n").encode("utf-8")
    location = f"state/artifacts/artifact-run/{name}.json"
    path = root / location
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    service.register_artifact(
        run_id="artifact-run", artifact_type=artifact_type, logical_name=name,
        media_type="application/json", format="json", location=location, content=content,
    )


def test_selected_screening_configuration_loads_exact_chart_and_trade_evidence(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    row_id = "parameter-row-2"
    namespace = f"screening_configuration/{row_id}"
    try:
        _register_document(service, tmp_path, name=f"{namespace}/trades_and_orders", artifact_type=ArtifactType.TRADES_OR_ORDERS, document={
            "trades": [{
                "Exit Trade Id": 7, "Status": "Closed", "Direction": "Short",
                "Entry Index": "2026-01-02T14:35:00+00:00", "Avg Entry Price": 6001,
                "Exit Index": "2026-01-02T14:40:00+00:00", "Avg Exit Price": 6003, "PnL": -10,
            }],
        })
        _register_document(service, tmp_path, name=f"{namespace}/equity_curve", artifact_type=ArtifactType.EQUITY_CURVE, document={
            "source_interval": "5m",
            "price_series": [
                {"timestamp": "2026-01-02T14:30:00+00:00", "open": 6000, "high": 6002, "low": 5999, "close": 6001},
                {"timestamp": "2026-01-02T14:35:00+00:00", "open": 6001, "high": 6004, "low": 6000, "close": 6003},
                {"timestamp": "2026-01-02T14:40:00+00:00", "open": 6003, "high": 6005, "low": 6002, "close": 6004},
            ],
            "equity_curve": [
                {"timestamp": "2026-01-02T14:30:00+00:00", "value": 100_000},
                {"timestamp": "2026-01-02T14:40:00+00:00", "value": 99_990},
            ],
        })
        _register_document(service, tmp_path, name=f"{namespace}/metrics", artifact_type=ArtifactType.METRICS, document={
            "metrics": {"total_return": -0.0001, "number_of_trades": 1},
        })
    finally:
        service.close()

    evidence = load_screening_configuration_evidence(
        "artifact-run", row_id, interval="15m", database=tmp_path / "state" / "artifacts.sqlite3",
    )

    assert evidence["available"] is True
    assert evidence["parameter_row_id"] == row_id
    assert len(evidence["price"]) == 1
    assert evidence["price"][0]["source_count"] == 3
    assert evidence["trade_count"] == 1
    assert evidence["trades"][0]["trade_id"] == "7"
    assert evidence["trades"][0]["entry_timestamp"] == "2026-01-02T09:35:00"
    assert evidence["trades"][0]["entry_display"] == "Jan 2, 2026 · 9:35 AM ET"
    assert evidence["sessions"] == ["2026-01-02"]
    assert evidence["metrics"]["number_of_trades"] == 1
