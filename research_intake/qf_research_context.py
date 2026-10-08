"""Portable Quant Factory context for external strategy research.

The context is a supporting snapshot, not Tier-1 authority. It gives external
researchers enough QF history and constraints to avoid obvious duplicate or
out-of-mandate proposals before QF performs its own authoritative checks.
"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

import yaml

QF_RESEARCH_CONTEXT_SCHEMA = "qf_research_context_v1"

_CONTEXT: dict[str, Any] = {
    "schema": QF_RESEARCH_CONTEXT_SCHEMA,
    "snapshot_date": "2026-10-08",
    "purpose": (
        "Portable context for external LLM/human strategy research before "
        "QF Candidate v1 intake."
    ),
    "authority": {
        "tier1": ["AGENTS.md", "docs/MILESTONES.md", "docs/DECISIONS.md"],
        "candidate_contract": "docs/qf-candidate-v1.md",
        "data_catalog": "docs/DATA_CATALOG.md",
        "notice": (
            "This file is a convenience snapshot. Quant Factory re-checks current "
            "Tier-1 authority, prior work, data, and Candidate validity before research."
        ),
    },
    "mandate": {
        "research_style": "same_session_intraday",
        "holding_period": "minutes_to_hours",
        "overnight_positions": False,
        "primary_behavior": ["S&P 500", "Nasdaq-100"],
        "first_stage_instruments": ["MES", "MNQ"],
        "later_transfer_targets": ["SPY", "QQQ", "index products"],
        "options_role": (
            "Options/0DTE are possible later execution vehicles, not the source "
            "of the trading edge."
        ),
        "current_research_state": "paused_during_operator_interface_design_and_campaign_policy_gate",
    },
    "research_rules": [
        "Treat a symbol, wrapper, source repository, or parameter change as insufficient by itself to create a new hypothesis.",
        "Compare against prior Quant Factory work, but reject only exact or economically equivalent hypotheses; never infer that an entire strategy family is exhausted unless Tier-1 explicitly says so.",
        "Separate structural strategy variants from bounded variables VectorBT may sweep.",
        "Do not invent missing source rules silently; preserve them as open_questions.",
        "Do not run backtests, optimize parameters, claim profitability, or implement QF strategy code unless separately authorized.",
        "Do not inspect protected evidence, buy data, submit orders, or infer paper/live authority.",
        "Candidate work must remain same-session intraday unless the owner explicitly changes the mandate.",
    ],
    "prior_work": [
        {
            "family": "opening_range_breakout",
            "instrument": "MES",
            "family_status": "open_for_new_hypotheses",
            "tested_hypothesis_status": "screened_out",
            "tested_scope": (
                "Shallow baseline only: 5/15/30/45/60-minute opening range x "
                "0/1/2-tick breakout offset x long/short; next-bar-open entry; "
                "session-close exit; no stop, target, trailing stop, retest, "
                "volume filter, volatility filter, or other confirmation."
            ),
            "disposition": (
                "Do not repeat the same baseline matrix, but actively allow materially "
                "different ORB hypotheses and structural variants."
            ),
            "family_exhausted": False,
            "reference": "docs/strategies/mes-opening-range-breakout.md",
        },
        {
            "family": "overnight_gap_reversal",
            "instrument": "MES",
            "family_status": "open_for_new_hypotheses",
            "tested_hypothesis_status": "rejected",
            "tested_scope": (
                "One exact rule only: prior 15:55 close to current 09:30 open gap, "
                "opposite-gap entry at 09:35, exit at 10:00, no threshold/filter/stop/target."
            ),
            "disposition": (
                "Do not tune or rerun that exact rule; materially different gap-reversal "
                "hypotheses remain eligible for research."
            ),
            "family_exhausted": False,
            "reference": "docs/strategies/mes-overnight-gap-reversal.md",
        },
        {
            "family": "opening_range_breakout",
            "instrument": "MSFT",
            "family_status": "open_for_new_hypotheses",
            "tested_hypothesis_status": "withdrawn",
            "tested_scope": "One five-minute ORB transfer effort; not evidence against the ORB family.",
            "disposition": "Use as overlap history only.",
            "family_exhausted": False,
            "reference": "docs/strategies/msft-five-minute-orb-transfer.md",
        },
        {
            "family": "intraday_momentum",
            "instrument": "SPYM",
            "family_status": "open_for_new_hypotheses",
            "tested_hypothesis_status": "historical_screen",
            "tested_scope": (
                "One fixed transfer rule from prior-session 15:59/current 09:59 "
                "direction to a 15:30-15:59 trade; no parameter exploration."
            ),
            "disposition": "Do not equate this one transfer rule with the intraday-momentum family.",
            "family_exhausted": False,
            "reference": "docs/strategies/spym-intraday-momentum.md",
        },
        {
            "family": "channel_breakout",
            "instrument": "SPY",
            "family_status": "open_for_intraday_hypotheses",
            "tested_hypothesis_status": "historical_daily_work",
            "tested_scope": "Daily Donchian close breakout with daily-channel exits.",
            "disposition": (
                "Current mandate excludes the daily holding formulation, but intraday "
                "channel-breakout hypotheses remain open."
            ),
            "family_exhausted": False,
            "reference": "docs/strategies/spy-donchian-trend-breakout.md",
        },
        {
            "family": "mean_reversion",
            "instrument": "SPYM",
            "family_status": "open_for_new_hypotheses",
            "tested_hypothesis_status": "infrastructure_fixture",
            "tested_scope": "RSI mean-reversion fixture used for infrastructure/evidence-path testing.",
            "disposition": "Not evidence that RSI or mean-reversion families lack an edge.",
            "family_exhausted": False,
            "reference": "strategies/spym_rsi_mean_reversion_fixture.py",
        },
        {
            "family": "turn_of_month",
            "instrument": "SPY",
            "family_status": "out_of_current_mandate",
            "tested_hypothesis_status": "not_currently_eligible",
            "disposition": "retain_for_possible_future swing research",
            "reason": "multi-day holding conflicts with current intraday mandate",
            "family_exhausted": False,
            "reference": "docs/strategies/spy-turn-of-month.md",
        },
    ],
    "relevant_data_snapshot": [
        {
            "dataset": "futures_MES_5m_databento",
            "instrument": "MES",
            "timeframe": "5m",
            "provider": "Databento",
            "status": "validated",
            "coverage": "2019-05-05 22:00 UTC through 2026-02-13 21:55 UTC",
            "restriction": "explicit session and roll-method review required",
        },
        {
            "dataset": "futures_MNQ_5m_databento",
            "instrument": "MNQ",
            "timeframe": "5m",
            "provider": "Databento",
            "status": "validated",
            "coverage": "2019-05-05 22:00 UTC through 2026-02-13 21:55 UTC",
            "restriction": "explicit session and roll-method review required",
        },
        {
            "dataset": "futures_M2K_5m_databento",
            "instrument": "M2K",
            "timeframe": "5m",
            "provider": "Databento",
            "status": "validated",
            "coverage": "2019-05-05 22:00 UTC through 2026-02-13 21:55 UTC",
            "restriction": "not a primary current discovery instrument",
        },
        {
            "dataset": "equities_MSFT_5m_databento",
            "instrument": "MSFT",
            "timeframe": "5m",
            "provider": "Databento",
            "status": "validated",
            "coverage": "2019-05-01 08:35 UTC through 2026-02-13 23:55 UTC",
            "restriction": "extended hours present; adjusted-price status unresolved",
        },
        {
            "dataset": "equities_SPYM_1m_databento_equs_mini",
            "instrument": "SPYM",
            "timeframe": "1m",
            "provider": "Databento EQUS.MINI",
            "status": "validated",
            "coverage": "2025-10-31 through 2026-07-13 completed NYSE regular sessions",
            "restriction": "bounded historical fixture/reference uses only",
        },
        {
            "dataset": "equities_SPY_1m_alpaca_iex",
            "instrument": "SPY",
            "timeframe": "1m",
            "provider": "Alpaca IEX",
            "status": "validated_limited",
            "coverage": "five completed NYSE sessions: 2026-07-01 through 2026-07-08",
            "restriction": "IEX only; do not treat as SIP consolidated history",
        },
    ],
    "data_caveat": (
        "This snapshot describes catalogued datasets, not guaranteed runtime "
        "availability. Quant Factory must verify local manifests/checksums before use."
    ),
    "candidate_output_contract": {
        "schema": "qf_candidate_v1",
        "required_core": [
            "candidate.title",
            "hypothesis.behavior",
            "market.holding_style=intraday",
            "market.overnight_positions=false",
            "rules",
            "sources or owner_observation attribution",
        ],
        "strongly_expected": [
            "hypothesis.failure_theory",
            "source_rules",
            "qf_interpretation",
            "fixed",
            "variables",
            "variants",
            "open_questions",
            "data_needs",
            "exclusions",
            "prior_work",
            "evaluation.use_qf_standard_screen=true",
        ],
        "variable_rule": (
            "variables are justified bounded values VectorBT may enumerate; "
            "do not enumerate every combination yourself"
        ),
        "variant_rule": (
            "variants are genuinely different logic paths; do not disguise "
            "parameter changes or prior-work duplicates as new variants"
        ),
        "import_authority": (
            "External packets may describe research intent and bounded variants, "
            "but they cannot assert owner approval, eligibility, execution, promotion, or trading "
            "authority. Quant Factory derives eligibility deterministically under "
            "the active campaign policy."
        ),
    },
    "external_research_instruction": (
        "Use this context before researching. Survey the requested sources or "
        "strategy universe and compare against prior_work at the exact-hypothesis level. "
        "Do not discard a family merely because QF tested one shallow or different "
        "variant. Exclude only exact/economically equivalent repeats or current mandate "
        "conflicts. Return QF Candidate v1 packets for genuinely distinct hypotheses, "
        "including materially different variants within previously touched families. "
        "Preserve uncertainties. Do not backtest, optimize, implement, or rank a winner. "
        "Return Candidate packets to Quant Factory, which owns deterministic validation, "
        "bounded repair, deduplication, study construction, execution eligibility, and evidence."
    ),
}


def build_research_context() -> dict[str, Any]:
    """Return an isolated portable research-context snapshot."""

    return deepcopy(_CONTEXT)


def export_research_context(*, format: str = "yaml") -> str:
    """Serialize QF Research Context v1 for an external researcher/LLM."""

    document = build_research_context()
    if format == "json":
        return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if format in {"yaml", "yml"}:
        return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    raise ValueError(f"unsupported research context export format {format!r}")
