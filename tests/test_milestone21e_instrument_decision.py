"""Milestone 21E documentation consistency for the equity fixture decision."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_milestone21e_selects_schx_without_promoting_profitability() -> None:
    milestones = _read("docs/MILESTONES.md")
    decisions = _read("docs/DECISIONS.md")
    adr = _read("docs/architecture/0005-execution-adapters-and-initial-venues.md")
    readme = _read("README.md")

    for text in (milestones, decisions, adr, readme):
        assert "SCHX" in text
        assert "not profitability" in text or "not strategy-profitability" in text

    assert "**Broad-market whole-share forward-test instrument:** SCHX" in milestones
    assert "SCHX is selected as the future broad-market whole-share paper" in decisions
    assert "**Broad-market whole-share forward-test instrument:** SCHX" in adr
    assert "Milestone 21E selected SCHX" in readme


def test_spym_remains_fixture_not_final_forward_test_instrument() -> None:
    decisions = _read("docs/DECISIONS.md")
    adr = _read("docs/architecture/0005-execution-adapters-and-initial-venues.md")
    readme = _read("README.md")

    stale = (
        "SPYM is the first paper-traded instrument and, after paper acceptance "
        "and risk-control completion, the first small-money forward-test instrument"
    )
    for text in (decisions, adr, readme):
        assert stale not in text
        assert "SPYM" in text

    assert "SPYM is retained as the completed Databento" in decisions
    assert "SPYM remains" in adr
    assert "Databento ingestion" in adr
    assert "SPYM remains the completed Databento ingestion" in readme


def test_databento_schx_schb_evidence_is_recorded() -> None:
    data_sources = _read("docs/DATA_SOURCES.md")
    decisions = _read("docs/DECISIONS.md")

    for text in (data_sources, decisions):
        assert "`EQUS.MINI`" in text
        assert "`ohlcv-1m`" in text
        assert "14318" in text
        assert "14296" in text
        assert "USD $0.100031912327" in text
        assert "USD $0.082242786884" in text
        assert "3-for-1" in text
        assert "split" in text


def test_milestone21_and_22_are_complete_and_milestone23_is_active() -> None:
    milestones = _read("docs/MILESTONES.md")

    assert "| 21 | Operational Equity Data and Execution Fixture" in milestones
    assert "| 21 |" in milestones and "| **Complete** |" in milestones
    assert "Milestone 22 is complete" in milestones
    assert "22A complete" in milestones
    assert "22E complete" in milestones
    assert "23A complete" in milestones
    assert "| 22 | Unified Validation and Evidence Integration" in milestones
    assert "| 23 | End-to-End Equity Research Factory Acceptance" in milestones
    assert "The current bounded milestone is **23" in milestones
