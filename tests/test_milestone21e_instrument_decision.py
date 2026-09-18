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

    assert (
        "Fixtures validate infrastructure and are not active profitability candidates."
        in milestones
    )
    assert "SCHX is the broad-\n    market whole-share execution fixture" in decisions
    assert "**Broad-market whole-share forward-test instrument:** SCHX" in adr
    assert "Milestone 21E selected SCHX" in readme
    for text in (adr, readme):
        assert "not profitability" in text


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

    assert "SPYM remains an ingestion and\n    deterministic research fixture" in decisions
    assert "SPYM remains" in adr
    assert "Databento ingestion" in adr
    assert "SPYM remains the completed Databento ingestion" in readme


def test_databento_schx_schb_evidence_is_recorded() -> None:
    data_sources = _read("docs/DATA_SOURCES.md")
    decisions = _read("docs/DECISIONS.md")
    adr = _read("docs/architecture/0005-execution-adapters-and-initial-venues.md")

    for expected in (
        "`EQUS.MINI`",
        "`ohlcv-1m`",
        "14318",
        "14296",
        "USD $0.100031912327",
        "USD $0.082242786884",
        "3-for-1",
        "split",
    ):
        assert expected in data_sources
    assert "Databento `EQUS.MINI`" in adr
    assert "one-minute historical-data cost" in adr
    assert "This selection is not profitability approval" in adr
    assert "SCHX is the broad-\n    market whole-share execution fixture" in decisions
    assert "SPYM remains an ingestion and\n    deterministic research fixture" in decisions


def test_milestone21_and_22_are_complete_and_milestone23_is_active() -> None:
    milestones = _read("docs/MILESTONES.md")

    assert "Milestones 1–22 are complete." in milestones
    assert (
        "| 16–22 | Infrastructure, persistence, orchestration, lineage, "
        "dashboard foundation, equity fixture, and unified validation"
        in milestones
    )
    assert "| Complete |" in milestones
    assert "- **23A — Scenarios and fixtures:** frozen. **Complete.**" in milestones
    assert (
        "- **23B — Automated full-system acceptance:** supporting evidence implemented;"
        in milestones
    )
    assert "| 23 | End-to-End Equity Research Factory Acceptance" in milestones
    assert "| R05 | 1 | in_progress |" in milestones
    assert "milestone is **23 — End-to-End Equity Research Factory Acceptance**." in milestones
