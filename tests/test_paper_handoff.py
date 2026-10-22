"""Focused proof for the dormant research-to-paper handoff seam."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import json

import pytest

from execution import PaperHandoffError, PaperHandoffPackage, paper_handoff_manifest


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _package(**changes: object) -> PaperHandoffPackage:
    values: dict[str, object] = {
        "handoff_id": "handoff-001",
        "candidate_id": "candidate-001",
        "strategy_id": "opening-range-breakout",
        "strategy_version": "1.0.0",
        "source_run_id": "run-001",
        "evidence_bundle_ref": "artifact:evidence/run-001",
        "evidence_bundle_sha256": "a" * 64,
        "strategy_package_ref": "artifact:strategy/opening-range-breakout/1.0.0",
        "strategy_package_sha256": "b" * 64,
        "execution_vehicle_id": "alpaca-us-equity-whole-share-v1",
        "instrument_symbols": ("SPY",),
        "eligibility_decision_id": "eligibility-001",
        "eligibility_gate_ids": ("oos-pass", "walk-forward-pass", "robustness-pass"),
        "lane_policy_id": "paper-lane-policy-001",
        "paper_risk_policy_id": "paper-risk-policy-001",
        "source_revision": "1" * 40,
        "created_at": NOW,
    }
    values.update(changes)
    return PaperHandoffPackage(**values)  # type: ignore[arg-type]


def test_handoff_is_immutable_json_native_and_contains_no_runtime_authority() -> None:
    package = _package()
    manifest = paper_handoff_manifest(package)

    assert manifest["schema"] == "qf.paper-handoff.v1"
    assert manifest["created_at"] == "2026-10-08T12:00:00Z"
    assert manifest["instrument_symbols"] == ["SPY"]
    assert json.loads(json.dumps(manifest))["lane_policy_id"] == "paper-lane-policy-001"
    assert not {
        "account_id",
        "credentials",
        "endpoint",
        "order",
        "position",
        "pnl",
    } & manifest.keys()
    with pytest.raises(FrozenInstanceError):
        package.strategy_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("evidence_bundle_sha256", "not-a-digest"),
        ("strategy_package_sha256", "A" * 64),
        ("instrument_symbols", ()),
        ("instrument_symbols", ("ESZ6", "ESZ6")),
        ("instrument_symbols", ("not valid",)),
        ("eligibility_gate_ids", ()),
        ("eligibility_gate_ids", ("same", "same")),
        ("created_at", datetime(2026, 10, 8, 12, 0)),
    ),
)
def test_handoff_rejects_ambiguous_or_incomplete_identity(field: str, value: object) -> None:
    with pytest.raises(PaperHandoffError):
        _package(**{field: value})


def test_handoff_serializer_rejects_untyped_input() -> None:
    with pytest.raises(PaperHandoffError, match="PaperHandoffPackage"):
        paper_handoff_manifest({})  # type: ignore[arg-type]
