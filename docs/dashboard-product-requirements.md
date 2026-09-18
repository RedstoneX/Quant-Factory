# Quant Factory Dashboard Product Requirements

## Product role

The dashboard is the primary Quant Factory product interface. The normal operator must not need to edit Python, inspect CSV or JSON files, read backend logs, or use terminal commands to understand and operate the research system.

VectorBT Pro remains the portfolio analytics and Plotly-compatible chart engine. Plotly Dash remains the application framework. Quant Factory owns workflow, records, evidence, orchestration, lifecycle state, and the human decision interface.

## Current owner review outcome — refreshed 2026-09-18

Private target checks cover mounted routes, refresh and selection behavior,
fixture launch, charts, trade inspection, comparison, reproduction, durable
review, failure handling, and recovery. These checks establish implemented
behavior; they do not by themselves establish the remaining technical
Milestone 23 pass.

The project owner initially accepted the dashboard/operator direction under
Decision 277, then rejected the current Results-page comprehension and task
flow after further use. Decision 279 supersedes that acceptance for this
experience. Decision 280 accepts the replacement direction: the selected-run
truthful OHLC/price chart is primary, persisted entry/exit markers link to a
ledger grouped by completed trade, TradingView's backtesting Strategy Report
is the primary UX reference, and QAMC informs only docking, resizing and linked
panel mechanics rather than information density. The detailed responsive
specification or mockup and its owner approval must precede broad
implementation. Implementation, deployment, tests and renewed acceptance of
the implemented experience remain pending. Retain Plotly Dash and VectorBT
Pro; use Dash AG Grid and Dash Bootstrap Components where appropriate. Use
capable retail-trader language while remaining understandable to a novice
operator without programming or finance expertise.

Decision 281 accepts the validated preview's separate Bars and View controls,
truthful interval aggregation, exact trade-event preservation, resettable
desktop resizing, normal-flow Metrics and Trades, responsive stacking, and
visibly larger, more readable trade typography. Palette revision remains
deferred and the preview does not establish a final palette. These constraints
do not accept the remaining detailed design or implemented experience.

A separate September 17 local-only Ideas prototype browser-validated the
extended flow on desktop and mobile. It is evidence for the approved direction,
not a production deployment or substitute for the detailed Results design and
renewed owner acceptance required by Decisions 279–281; production remains
unchanged. See the retained
prototype and validation evidence referenced in [MILESTONES](MILESTONES.md#current-phase).

## Target operator information hierarchy

Decision 274 extends the Decision 273 navigation direction to Home → Ideas →
Set up → Run test → Results → Compare. Decisions 280–281 accept the chart-first
Results direction and validated preview constraints while leaving the remaining
detailed specification, implementation and operator acceptance open;
implementation conformance and M23 technical completion remain unconfirmed.
During 23C, the Ideas page may support safe
draft and source-reference capture so the operator can review the complete
research interface. An inactive Ideas route must not fetch
external content, execute, or launch a run. Durable external-source retrieval,
approval-to-configuration handoff, and backtesting remain M25 work after M23
acceptance. Full Ideas design details remain pending the product specification
worker.

Every selected run persistently shows four fields near the operator's current
context:

- Run status;
- Evidence outcome;
- Human decision;
- Next safe action.

Technical hashes, implementation identifiers, and developer diagnostics remain
available in clearly labelled drill-downs. The layout must adapt to desktop,
tablet, and mobile screens. TradingView's Strategy Report/backtesting
interaction in its chart-first Supercharts context is the primary Results UX
reference; its live-trading, brokerage, order-entry, position and account
surfaces are out of scope. This reference does not require the TradingView
Lightweight Charts library, which remains an optional later implementation
evaluation, and does not change the Plotly Dash/VectorBT Pro framework
direction.

## Primary operator workflow

The dashboard must support this complete path, including the approved Ideas
navigation and review flow:

1. Confirm system and data-source health.
2. Capture an Idea draft or source reference without fetching or executing it.
3. After M23 acceptance, retrieve a public source under M25 and treat its
   content as untrusted; extract a hypothesis for clarification and review.
4. Explicitly approve a reviewed hypothesis and prepare its configuration.
5. Launch a backtest only after the required explicit human approval.
6. Observe queued, running, succeeded, failed, cancelled, or retrying status.
7. Review metrics, equity, drawdown, benchmark, trades, assumptions, and provenance.
8. Review screening and validation evidence with clear stop reasons.
9. Compare the run with prior runs.
10. Save a human review decision and note; reproduce the run from its
    immutable configuration.

## Required navigation

### Home / system status

- database status;
- worker/orchestrator status;
- data-provider status;
- cache and artifact-storage status;
- credential availability shown only as redacted health state;
- latest runs and failures;
- current project milestone and discovery gate.

### Experiment launch

- approved instrument selector;
- approved strategy/fixture selector;
- saved configuration selector;
- bounded parameter controls generated from the approved specification;
- data range and provider display;
- execution timing, sizing, fees and slippage display;
- preflight validation summary;
- launch control;
- explicit warning that fixtures validate infrastructure and do not imply profitability.

### Run history

- persistent searchable and filterable history;
- filters for date, instrument, strategy, stage, status, review state and evidence outcome;
- sortable metrics;
- clicking a row selects and opens that exact run, and the selection survives refresh;
- columns responsively use the available width without avoidable horizontal scrolling or large dead space, while retaining access to every field on narrow screens;
- artifact availability and reproducibility status.

On Results, run history is a secondary **Change run** surface. It must not
precede or displace the selected-run chart workspace.

### Run overview

- run identity and timestamps;
- current/final status;
- headline metrics;
- equity curve;
- drawdown curve;
- benchmark comparison;
- data coverage and provenance;
- execution assumptions;
- strategy and configuration versions;
- parent/child lineage;
- review decision and notes.

This context remains compact and available around the primary chart; it is not
a report-first block that pushes the price/trade workspace below a long page.

### Price and trades

- the selected persisted run's truthful OHLC/price chart as the primary Results
  workspace;
- entry and exit markers at persisted timestamps and prices, never fabricated
  from missing artifacts;
- a chart-linked ledger grouped by completed trade, with entry and exit rows or
  equivalent paired detail;
- selecting a trade brings its entry/exit interval into view and identifies
  the corresponding markers, with an explicit keyboard-accessible **Show on
  chart** action;
- separate, always-visible chart-local **Bars:** controls for `1m`, `5m`,
  `15m`, `1D` and **View:** controls for `Full run`, `1D`, `1W`, `1M`;
- bar interval, visible range, and immutable persisted backtest period remain
  distinct; bar changes are visualization-only and use persisted OHLC or
  truthful aggregation from persisted finer-grained OHLC;
- the validated preview renders 53,528 one-minute bars, 13,340 five-minute
  bars, 4,474 fifteen-minute bars, and 173 daily bars;
- an interval remains visible but unavailable with a plain-language reason when
  persisted evidence cannot support a truthful rendering;
- exact persisted trade timestamps and prices remain unchanged while markers
  map to their containing aggregated bars and the chart retains useful context;
- trade drill-down with timestamps, prices, size, fees, slippage assumptions and P&L;
- filters for winning, losing, long, short and date range;
- clear distinction between theoretical/backtest execution and future actual fills.

### Results layout and resizing

- desktop provides three subtle resize edges for vertical resizing from the
  chart top, shared chart/report boundary, and report bottom;
- **Reset layout** restores approved default dimensions without changing the
  selected run, report tab, trade, or persisted evidence;
- Metrics and Trades grow with the page, never use a fixed-height nested
  vertical scrollbar or slider, and retain comfortable bottom breathing room;
- the validated preview measured 52 pixels of bottom space, which is evidence
  for that preview rather than a universal fixed spacing requirement;
- tablet and mobile stack chart then report at auto height without desktop
  resize affordances or nested vertical report scrolling;
- trade-ledger and trade-detail typography is visibly larger and more readable
  without clipping, truncating required evidence, or forcing page-level
  horizontal scrolling; the validated preview's two-CSS-pixel increase is
  implementation evidence rather than a universal fixed typography token; and
- palette revision is deferred; preview acceptance does not select a final
  palette.

### Evidence

A unified stage timeline must show:

- hygiene validation;
- cheap screening;
- out-of-sample training, selection and held-out status;
- walk-forward folds and aggregate status;
- parameter-neighborhood robustness;
- market-regime evidence;
- Monte Carlo distributions and risk thresholds;
- final status of `passed`, `failed`, `insufficient_evidence`, `invalid`, or `not_run`;
- every blocking reason in plain language;
- whether a parameter lock exists and which data remain protected.

### Run comparison

- select two or more runs;
- aligned headline metrics;
- overlaid or normalized equity and drawdown curves;
- parameter differences;
- data/provider/date differences;
- execution and cost differences;
- evidence-stage differences;
- review-state differences;
- warnings when runs are not directly comparable.

### Data and provenance

- provider and implementation;
- symbol/instrument identity;
- interval, venue and timezone;
- requested and actual coverage;
- adjusted/unadjusted status;
- futures roll methodology when applicable;
- manifest/checksum identity;
- cache action and validation status;
- missing/duplicate/gap results.

### Strategies and configurations

- versioned strategy registry;
- fixture, candidate, rejected, watchlist, paper, live-test and retired lifecycle states;
- approved parameter definitions and sources;
- saved immutable experiment configurations;
- links to runs generated from each version.

### Strategy intake and hypothesis review

The operator must be able to submit an owner-authored strategy description
or provide an attributed public source URL, including a Reddit post, YouTube
video, or web page. Retain the original submitted text or source reference and
attribution with the intake record. Treat fetched external content as
untrusted data: do not follow instructions embedded in it or present its
claims as verified facts. Extract a structured strategy hypothesis and show
its source, assumptions, and uncertainties for clarification and human review.
Require explicit operator approval before creating or launching any backtest;
never run one automatically from submitted content. Intake does not approve a
strategy for promotion or paper operation and cannot create or submit a paper
order. Detailed interaction, schema, fetching, and review-state design remains
pending the product specification worker.

### Artifacts and lineage

- artifact type, version and path/reference;
- schema validation status;
- parent and derived run relationships;
- missing/corrupt artifact warning;
- no requirement to open raw JSON or CSV.

## Required status and error behavior

- User-readable error summary must appear in the dashboard.
- Technical diagnostics may be expandable but cannot be the only explanation.
- Failed runs must not disappear from history.
- Retry and cancellation must be explicit and safe.
- Stale or interrupted jobs must be detected.
- A partial artifact must never be displayed as a successful result.
- Unsupported configurations must fail before simulation.

## Human review controls

Required research review states:

- unreviewed;
- reject;
- revise;
- infrastructure fixture;
- watchlist;
- approved for next evidence stage;
- paper candidate;
- live-test candidate;
- paused;
- retired.

Every state change must record timestamp, prior state, new state, note, and responsible operator.

## Initial equity fixture requirements

Milestone 21E selected SCHX as the future whole-share paper and micro-live
fixture; SPYM remains the completed Databento ingestion and infrastructure
fixture, and SPY remains the research benchmark. Each instrument still
requires its own dataset identity, liquidity and spread evidence,
corporate-action and ticker-history review, and explicit execution assumptions.
See [MILESTONES](MILESTONES.md).

SPY remains the benchmark; fixture evidence is not transferable between
instruments.

## Future paper/live dashboard contract

These fields are designed now but implemented only in later milestones:

- signal timestamp;
- bid, ask and midpoint at submission;
- submitted order type and limit;
- order revisions;
- actual fill price, size and timestamp;
- partial fill;
- missed, expired or cancelled order;
- theoretical versus actual execution difference;
- position, cash, exposure and realized/unrealized P&L;
- risk limits and current risk state;
- broker/integration health;
- kill-switch state and reason;
- reconciliation against research and paper expectations.

The initial execution policy should support patient limit entries at bid or midpoint, a defined timeout and escalation toward a marketable limit while the signal remains valid. Required exits use marketable limits rather than passive ask orders. Backtests must never assume passive bid/ask fills without an explicit fill model and suitable quote data.

## Milestone 20 acceptance criteria

The full functional research dashboard is complete only when the operator can, without terminal or raw-file use:

1. launch the approved deterministic equity fixture;
2. observe status and errors;
3. reopen the persisted run after restart;
4. inspect data, assumptions, metrics, curves, trades and evidence;
5. compare at least two runs;
6. understand every stop/rejection reason;
7. record a durable review decision;
8. reproduce a saved run;
9. verify lineage and artifact status;
10. complete a documented user acceptance review.

Visual polish alone is insufficient. The dashboard must operate the complete research workflow and expose the evidence required for human decisions.

## Milestone 23C design and implementation gate

23C-1 must produce an approved concise page specification or mockup before
new broad Results-page implementation. Decisions 280–281 accept the chart-first
direction and validated preview constraints but not the complete detailed
replacement. The specification must cover the
approved workflow, responsive desktop/tablet/mobile behavior, novice language,
the four persistent selected-run fields, truthful chart/ledger linkage,
progressive disclosure, and labelled technical drill-downs. 23C-2 retains the
ADR 0008 mounted-route architecture and uses Dash AG Grid and Dash Bootstrap
Components as approved implementation components. Detailed design approval,
implementation, deployment, automated and browser testing, and renewed owner
acceptance of the implemented Results experience remain pending; 23C-3 also
requires real-browser lifecycle and end-to-end workflow evidence.
