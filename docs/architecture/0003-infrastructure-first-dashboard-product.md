# ADR 0003: Infrastructure-first dashboard product

- Status: Accepted
- Date: 2026-07-09
- Superseded in part: ADR 0009 replaces the Codex-first work-allocation
  consequence.
- Superseded in part: Decision 287 replaces dashboard-first active sequencing
  and the blanket prohibition on controlled pre-Milestone-23 research. The
  dashboard/product architecture and all paper/live gates remain accepted.

## Context

Quant Factory completed substantial reusable research components and then moved into strategy-candidate discovery before the experiment database and complete dashboard existed. This caused strategy-specific validation work to advance while the owner still lacked the intended primary interface for viewing and operating the system.

The owner does not intend to operate Quant Factory by editing Python, reading raw CSV/JSON artifacts, inspecting backend logs, or repeatedly requesting terminal interpretation. The dashboard is the product interface.

## Decision

1. Quant Factory is infrastructure first until the end-to-end equity research factory passes acceptance.
2. Plotly Dash is the primary operator interface. VectorBT Pro remains the portfolio analytics and Plotly-compatible chart engine.
3. Existing RSI, MES ORB, and SPY Donchian implementations are reclassified as deterministic infrastructure fixtures and historical evidence, not active profitability candidates.
4. Decision 287 authorizes controlled, bounded, source-attributed candidate
   intake, discovery and research/backtesting before Milestone 23 passes;
   open-ended optimization or data mining, protected-test evaluation, automatic
   promotion, paper orders and live work remain blocked.
5. The infrastructure dependency order remains persistence/registry,
   orchestration/logging, schemas/lineage/reproducibility, full dashboard,
   operational equity fixture, unified evidence integration, and end-to-end
   acceptance. Decision 287 supersedes that order only as the active work
   sequence; it does not replace the architecture.
6. Futures, crypto, and FX operational work follows the accepted equity factory.
7. Infrastructure acceptance uses fixtures and known artifacts; it does not require a profitable strategy.
8. No strategy-specific result may create a new infrastructure subsystem or policy without a separate general architecture decision.

## Dashboard consequence

The completed dashboard must support experiment launch, persistent history, status/errors, metrics, VectorBT charts, completed trades, data provenance, execution assumptions, screening and validation evidence, run comparison, durable human review, reproducibility, lineage, artifacts, and system health without requiring normal use of Python, terminal, CSV, or JSON.

Detailed requirements are authoritative in `docs/dashboard-product-requirements.md`.

## Initial fixture consequence

Milestone 21E selected SCHX as the future whole-share paper and micro-live
fixture. SPYM is the completed Databento ingestion fixture and SPY remains the
benchmark. See [MILESTONES](../MILESTONES.md) for current status.

The future execution design uses patient limit entries at bid or midpoint, a defined timeout, optional escalation toward a marketable limit while the signal remains valid, and marketable-limit exits when execution is required. Historical testing must not assume passive bid/ask fills without suitable quote data and a defensible model.

## Work-allocation consequence

ADR 0009 and Decision 237 supersede this section's Codex fallback wording.
Claude Code is the primary implementation agent under the current agent
policy; orchestration follows its bounded worker rules. ChatGPT retains
architecture, research, documentation, source-of-truth maintenance, direct
repository work, and independent review.

## Superseded direction

Any prior roadmap language identifying candidate discovery, Donchian validation, robustness, Monte Carlo, or strategy promotion as the current next project work is superseded by this decision.
