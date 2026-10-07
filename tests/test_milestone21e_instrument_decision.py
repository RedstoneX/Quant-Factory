"""Milestone 21E documentation consistency for the equity fixture decision."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _normalized(relative: str) -> str:
    text = " ".join(_read(relative).split())
    return re.sub(r"(?<=\w)-\s+(?=\w)", "-", text)


def test_milestone21e_selects_schx_without_promoting_profitability() -> None:
    milestones = _read("docs/MILESTONES.md")
    decisions = _normalized("docs/DECISIONS.md")
    adr = _read("docs/architecture/0005-execution-adapters-and-initial-venues.md")

    assert "No generic new-candidate campaign" in milestones
    assert "Fixtures and previously inspected data prove infrastructure, not an edge." in decisions
    assert "**Broad-market whole-share forward-test instrument:** SCHX" in adr
    assert "This selection is not profitability approval" in adr


def test_spym_remains_fixture_not_final_forward_test_instrument() -> None:
    milestones = _read("docs/MILESTONES.md")
    adr = _read("docs/architecture/0005-execution-adapters-and-initial-venues.md")

    stale = (
        "SPYM is the first paper-traded instrument and, after paper acceptance "
        "and risk-control completion, the first small-money forward-test instrument"
    )
    for text in (milestones, adr):
        assert stale not in text
        assert "SPYM" in text

    assert "SPYM momentum" in milestones
    assert "SPYM remains approved for proving Databento" in adr
    assert "Databento ingestion" in adr


def test_databento_schx_schb_evidence_is_recorded() -> None:
    data_sources = _read("docs/DATA_SOURCES.md")
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
    assert "SCHX is selected" in adr
    assert "SPYM remains a valid ingestion fixture" in adr


def test_historical_fixture_decision_is_retained_without_overriding_current_queue() -> None:
    milestones = _read("docs/MILESTONES.md")
    normalized_milestones = _normalized("docs/MILESTONES.md")

    assert "SPYM momentum, SPY Donchian, and RSI fixture work are scoped historical" in normalized_milestones
    assert "R13 remains accepted" in milestones
    assert "| R12 | 1 | in_progress |" in milestones
    assert "| R14 | 2 | blocked |" in milestones
    assert "No generic new-candidate campaign" in milestones
    assert "Fixtures and previously inspected data prove infrastructure, not an edge." in _normalized("docs/DECISIONS.md")
