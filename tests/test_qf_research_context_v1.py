from __future__ import annotations

from pathlib import Path

import yaml

from research_intake import (
    QF_RESEARCH_CONTEXT_SCHEMA,
    build_research_context,
    export_research_context,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_research_context_carries_current_mandate_and_prior_work() -> None:
    context = build_research_context()

    assert context["schema"] == QF_RESEARCH_CONTEXT_SCHEMA == "qf_research_context_v1"
    assert context["mandate"]["research_style"] == "same_session_intraday"
    assert context["mandate"]["overnight_positions"] is False
    assert context["mandate"]["first_stage_instruments"] == ["MES", "MNQ"]
    assert context["candidate_output_contract"]["schema"] == "qf_candidate_v1"

    prior = {
        (item["family"], item["instrument"], item["status"])
        for item in context["prior_work"]
    }
    assert ("opening_range_breakout", "MES", "rejected") in prior
    assert ("overnight_gap_reversal", "MES", "rejected") in prior
    assert ("turn_of_month", "SPY", "out_of_scope") in prior


def test_research_context_references_existing_qf_evidence() -> None:
    context = build_research_context()

    for item in context["prior_work"]:
        assert (REPO_ROOT / item["reference"]).exists(), item["reference"]

    for path in context["authority"]["tier1"]:
        assert (REPO_ROOT / path).exists(), path
    assert (REPO_ROOT / context["authority"]["candidate_contract"]).exists()
    assert (REPO_ROOT / context["authority"]["data_catalog"]).exists()


def test_checked_in_context_snapshot_matches_export_contract() -> None:
    checked_in = yaml.safe_load(
        (REPO_ROOT / "docs/qf-research-context-v1.yaml").read_text(encoding="utf-8")
    )

    assert checked_in == build_research_context()
    assert yaml.safe_load(export_research_context(format="yaml")) == checked_in
    assert yaml.safe_load(export_research_context(format="json")) == checked_in


def test_external_research_context_has_no_execution_authority() -> None:
    context = build_research_context()
    instruction = context["external_research_instruction"].lower()

    assert "do not backtest" in instruction
    assert "do not" in instruction and "implement" in instruction
    assert "rank a winner" in instruction
    assert "owner approval" in context["candidate_output_contract"]["import_authority"].lower()
