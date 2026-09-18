# Quant Factory Dashboard Product Requirements

## Product role

The dashboard is the primary Quant Factory product interface. The normal operator must not need to edit Python, inspect CSV or JSON files, read backend logs, or use terminal commands to understand and operate the research system.

The product serves Terry as one private owner/operator seeking to find and
validate a trading edge and pursue consistent market income. It is not a
commercial, enterprise, SaaS, multitenant, billing, customer-onboarding, or
team dashboard. Capabilities needed only for hypothetical external users are
out of scope without separate owner approval.

VectorBT Pro remains the portfolio analytics and Plotly-compatible chart engine. Plotly Dash remains the application framework. Quant Factory owns workflow, records, evidence, orchestration, lifecycle state, and the human decision interface.

Apply Decision 285 before custom dashboard work: inventory and evaluate the
existing dashboard, VectorBT Pro and other licensed dependencies,
owner-approved prototypes, and mature maintained legally usable components.
Reuse or adapt suitable proven behavior; add custom code only for verified
Quant Factory gaps or when reuse is materially worse. The approved interactive
Results prototype and its working chart/page behavior must be preserved and
reused or adapted for the selected-run beta, but remain distinct from
integrated, tested, deployed, and renewed operator-accepted application
behavior.

Decision 286 limits the remaining selected-run beta to exactly three bounded
slices: reuse/integrate the approved page, make focused browser fixes, and
perform a backed-up validated OVH deployment. The remaining effort has a
six-development-hour planning ceiling that is measured and reported honestly,
not represented as a completion guarantee or fabricated precision. These
slices add no new framework, chart/grid/panel system or architecture, or paid
dependency, and do not replace approved behavior. Caching, scalable multi-run
design or Explorer work, aesthetic polish, and broad refactoring are excluded
unless evidence demonstrates that an item blocks the beta. If thin integration
expands, work stops for reuse and budget reassessment. Each slice has one
bounded implementer and one independent reviewer. Review covers the owned diff,
decisive evidence, and boundary compliance without reimplementation, broad
audit, discretionary redesign, or duplicate testing. The dashboard remains
essential for its single operator, but this beta MVP need not be perfect.

## Current owner review outcome — refreshed 2026-09-18

Private target checks cover mounted routes, refresh and selection behavior,
fixture launch, charts, trade inspection, comparison, reproduction, durable
review, failure handling, and recovery. These checks establish implemented
behavior; they do not by themselves establish the remaining technical
Milestone 23 pass.

The project owner initially accepted the dashboard/operator direction under
Decision 277, then rejected the former Results-page comprehension and task
flow after further use. Decision 279 supersedes that acceptance for the former
experience. Decision 280 accepts the replacement direction: the selected-run
truthful OHLC/price chart is primary, persisted entry/exit markers link to a
ledger grouped by completed trade, TradingView's backtesting Strategy Report
is the primary UX reference, and QAMC informs only docking, resizing and linked
panel mechanics rather than information density. After hands-on use of the
private interactive preview, Decision 282 approves the detailed selected-run
specification below as intuitive and authorizes implementation. Implementation,
deployment, tests, licensed-target proof and renewed acceptance of the eventual
implemented experience remain pending.
Retain Plotly Dash and VectorBT
Pro; use Dash AG Grid and Dash Bootstrap Components where appropriate. Use
capable retail-trader language while remaining understandable to a novice
operator without programming or finance expertise.

Decision 281 accepts the validated preview's separate Bars and View controls,
truthful interval aggregation, exact trade-event preservation, resettable
desktop resizing, normal-flow Metrics and Trades, responsive stacking, and
visibly larger, more readable trade typography. Palette revision remains
deferred and the preview does not establish a final palette. These constraints
did not by themselves accept the detailed design or implemented experience;
Decision 282 supplies the subsequent detailed selected-run design approval.

A separate September 17 local-only Ideas prototype browser-validated the
extended flow on desktop and mobile. It is evidence for the approved direction,
not a production deployment or substitute for Results implementation,
licensed-target proof and renewed acceptance required by Decision 282;
production remains
unchanged. See the retained
prototype and validation evidence referenced in [MILESTONES](MILESTONES.md#current-phase).

## Target operator information hierarchy

Decision 274 extends the Decision 273 navigation direction to Home → Ideas →
Set up → Run test → Results → Compare. Decisions 280–282 accept the chart-first
Results direction, validated preview constraints and detailed selected-run
specification while leaving implementation and eventual operator acceptance
open; implementation conformance and M23 technical completion remain unconfirmed.
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
Lightweight Charts library. It is not a candidate for the selected-run beta;
the approved working chart behavior and Plotly Dash/VectorBT Pro direction are
settled for these slices. Any later reconsideration requires a separate
owner-approved scope.

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

### Scalable multi-run analysis

At VectorBT scale, hundreds or thousands of persisted runs require a separate
analysis surface rather than loading their aggregate exploration into the
selected-run Results workspace. It must support aggregation, slicing, ranking,
filtering and selection by maximum drawdown, total return, profitable-trade
measures and other useful evidence dimensions. Metric names and populations
must remain explicit so a profitable-trade count is not silently confused with
a percentage or another basis. Selecting one run opens that exact run in
Results; selecting multiple runs can feed Compare.

Decision 282 accepts this product requirement, not a particular route name,
information architecture, control set, storage/query design or implementation.
A bounded design must establish those details before implementation and must
remain truthful and usable at the stated scale.

### Exact-repeat computation caching

Exact repeat research computations must be materially faster through safe
reuse of validated computed artifacts rather than rebuilding all computation.
This is distinct from the existing CI dependency cache and market-data cache:
it concerns reusable research computation outputs.

Every explicit operator request still creates a distinct durable run ticket
and lifecycle under ADR 0011, including its own identity, lineage, status and
operator-visible outcome. A cache hit is recorded as reuse within that run; it
does not silently reopen the source run, omit the new ticket, or count the same
computation as an independent evidence observation.

Reusable computed artifacts must be integrity-validated and traceable to every
input that can affect the result. At minimum, the design must account for
immutable configuration, dataset/manifest identity, execution and cost
assumptions, strategy/code identity, runtime and engine versions, evidence
stage, and protected-data population or partition. Failed, partial, corrupt,
mismatched, stale, or submission-unknown work is never reusable. A missing or
unverifiable input fails closed to recomputation or an explicit unavailable
state; it never produces an assumed cache hit.

Decision 283 accepts this behavior requirement, not an implementation. A
bounded design must evaluate the identity/keying mechanism (including whether
content addressing is suitable), storage, schema, publication safety,
concurrent access, invalidation, retention/eviction, target topology,
observability and implementation sequencing. It must also decide whether
explicit **Reproduce** always recomputes, uses cached work only to verify a
fresh computation, or offers a clearly labelled separate mode. Until that
decision is accepted, existing Reproduce semantics must not be changed.

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

## Approved detailed selected-run Results specification

**Status: ACCEPTED DESIGN / IMPLEMENTATION AUTHORIZED.** Decision 282 records
the owner's hands-on approval of this selected-run specification. It translates
the chart-first direction and validated-preview constraints into testable
behavior and may now be implemented. This status does not claim implementation,
deployment, testing, licensed-target proof, acceptance of the eventual
implemented experience, or Milestone 23 completion.

### Operator task and page order

The Results page answers, in order: **Which persisted run am I viewing? What
happened on the price chart? Which trades produced it? Is the evidence usable?
What should I do next?** The normal page order is:

1. the permanent application shell and Results route identity;
2. a compact selected-backtest strip;
3. the primary price-and-trade chart workspace;
4. the Metrics / Trades report in normal page flow;
5. evidence, review, provenance and assumptions; and
6. collapsed operations and technical diagnostics.

Run History is reached through the secondary **Change run** control. It must
not appear above, or push down, the selected-run chart. Selecting a run changes
only the selected persisted run and its derived display state; it never launches,
reproduces, retries, cancels or mutates a run.

### Region contract

#### 1. Selected-backtest strip

Keep this strip compact and visible immediately before the chart. It shows:

- trader-readable strategy or fixture name, instrument, source interval, and
  explicit start/end or completion date and time with timezone;
- run status in text, not color alone;
- the fixture/non-profitability warning when applicable;
- the four selected-run fields: **Run status**, **Evidence outcome**, **Human
  decision**, and **Next safe action**; and
- **Change run**, with raw run/configuration identities available only in a
  labelled technical drill-down.

The Change run surface provides searchable, sortable persisted history with an
explicit date and time, instrument, strategy, stage, status, review state,
evidence outcome, artifact state and reproducibility state. Its rows are
keyboard selectable and use available width without avoidable page-level
horizontal scrolling or large empty columns. A row selection adopts that exact
run and closes the secondary surface only after the selected identity is
confirmed.

#### 2. Primary chart workspace

The selected run's truthful OHLC/price chart is the largest and first analytical
surface. Its header always exposes:

- instrument, evidence timezone, source interval and immutable backtest period;
- **Bars:** `1m`, `5m`, `15m`, `1D`;
- **View:** `Full run`, `1D`, `1W`, `1M`;
- an entry/exit marker legend and plain-language visible bar/marker counts; and
- any interval-unavailable reason next to the disabled but still visible
  interval control.

Bars changes only the visual aggregation. View changes only the visible time
window. Selecting Bars never changes View, and selecting View never changes
Bars. Neither changes the selected run, persisted backtest period, metrics,
trades, evidence, or review. Pan and zoom may temporarily refine the visible
window. If the proposed **Reset range** engineering default is retained, it
returns to the independently selected Bars/View window without altering either
control; it is not Decision 281's accepted **Reset layout** requirement.

Entry and exit markers use the persisted event price and exact timestamp.
Hover or focus text states the exact event time and, when aggregated, the
containing bar time. The selected marker is distinguishable by shape/outline
and text as well as color. As a proposed accessibility implementation detail,
the chart has a text-equivalent status region that announces the focused trade
leg, exact event time, containing bar, active interval and visible window. That
proposal does not add a new research or persistence requirement.

#### 3. Metrics / Trades report

The report follows the chart and has two primary tabs, **Metrics** and
**Trades**. Both grow with the document and must not use a fixed-height nested
vertical scrollbar. Pagination or incremental page rendering may bound the
number of trade groups in the DOM, but the browser page remains the vertical
scroll owner.

Metrics begins with a compact headline summary, followed in normal flow by the
required persisted performance evidence: portfolio equity against the stated
benchmark, drawdown, and closed-trade P&L. The exact headline quartet used by
the preview remains a proposed engineering default below, not unconditional
accepted conformance. Every figure names its evidence basis and reports
unavailable data rather than substituting a different calculation silently.

Closed trades are grouped by completed trade rather than presented as unrelated
order rows. Each closed group shows direction, outcome/status, P&L and return,
plus paired entry and exit rows with exact timestamp, price, size and recorded
fees. An open or unconfirmed position is labelled separately, shows only
recorded entry and current/valuation information, and has no fabricated exit
row, exit marker, exit action, realized P&L, or win/loss outcome. Winning/losing
filters apply only to closed trades; long/short filters apply to every group;
and an exit-date filter excludes open, unconfirmed or undated groups with an
explicit excluded-count explanation. Every filter states the count shown
versus total.

Every persisted entry row has a keyboard-accessible **Show entry on chart**
action. A **Show exit on chart** action appears only for a recorded closed-trade
exit. Activating either available action:

1. preserves the selected run and exact persisted event data;
2. selects the trade and leg in the ledger;
3. brings the containing interval into the current chart view, adding useful
   context while keeping the requested View duration when possible;
4. identifies the corresponding marker without fabricating a new event; and
5. if the proposed text-equivalent status region is retained, announces the
   focused trade leg without forcing keyboard focus into the Plotly canvas.

#### 4. Evidence, review and technical detail

After the report, retain the existing required evidence, review, lineage,
provenance and execution-assumption capabilities. The first visible summary
uses operator language: evidence outcome, every blocking reason, human decision
and next safe action. Evidence stages, review history and decision controls are
available without opening raw files. Configuration IDs, checksums, artifact
references, callback/runtime diagnostics and raw event identities live in
clearly labelled collapsed technical sections.

Review controls remain bound to the selected persisted run. Changing chart
interval, view, tab, trade selection or panel size cannot change or save a
review. Run actions, recovery controls and operator events remain progressively
disclosed and retain their existing route and explicit-action safety gates.

### Truthful data and aggregation contract

- All displayed identity, OHLC, trades, metrics and evidence come from the
  selected persisted run and its validated artifacts. The UI never treats a
  partial, missing or corrupt artifact as a successful result.
- Source OHLC timestamps must be ordered, unique and valid before aggregation.
  Do not synthesize missing bars, forward-fill prices, or infer trades from
  chart geometry.
- For a supported coarser interval, each output bar uses the first persisted
  open, maximum persisted high, minimum persisted low and last persisted close
  within the declared bucket. Empty buckets remain empty. The displayed bucket
  timezone/session basis must come from recorded evidence; if that basis is
  insufficient for truthful aggregation, keep the interval visible but
  unavailable with a reason.
- Exact persisted entry timestamps and prices, and any recorded closed-trade
  exit timestamps and prices, never change. At a coarser interval, each real
  marker maps to the bar containing the event while its accessible text and
  hover detail retain both the exact event timestamp and containing-bar
  timestamp. Missing exits remain missing.
- The owner-accepted SPYM fixture counts are 53,528 `1m`, 13,340 `5m`, 4,474
  `15m`, and 173 `1D` bars from the same validated private evidence. The same
  preview also contained 366 closed trades; that trade count is validated
  preview evidence and a proposed engineering regression, not an owner-accepted
  universal requirement.
- Portable synthetic data-contract tests prove aggregation and marker mapping
  without licensed inputs. They do not prove the four private-fixture bar
  counts or the preview's 366-trade evidence; those require separate validation
  against the authorized private fixture source.
- Metrics, trade counts and performance figures name their population and
  calculation basis. Closed-trade metrics exclude open/unconfirmed positions.
  Backtest execution remains explicitly theoretical; no field implies actual
  broker fills.

### State, persistence and reset behavior

- Selected-run identity is represented by the Results deep link and survives
  refresh, direct open, and browser back/forward navigation. An invalid run ID
  must not be rendered as valid evidence or silently overwrite a proven
  selection.
- Route hydration and passive refresh may update the same persisted run's
  status/evidence, but cannot launch work, change route, or adopt another run
  without an explicit operator action.
- Bars, View, report tab, selected trade/leg and desktop panel dimensions are
  presentation state, not persisted research evidence. The unratified
  engineering default below proposes browser-session persistence; this is not
  a hidden owner choice or a research-record change.
- The proposed **Reset range** affects only chart pan/zoom. Decision 281's
  accepted **Reset layout** restores the approved default chart/report
  dimensions without changing selected run, report tab, selected trade/leg,
  evidence, review or route. Whether any panel is expanded or collapsed is not
  part of the accepted Reset layout requirement.
- Changing run clears any trade selection that does not belong to the new run.
  It must never display one run's chart with another run's ledger or review.

### Responsive and resize behavior

Desktop presents chart then report as one linked vertical workspace with three
subtle horizontal resize edges: chart top, shared chart/report boundary, and
report bottom. Each edge has a visible hover/focus affordance, bounded minimum
and maximum size, and an explicit text label for assistive technology. Dragging
the shared boundary grows one region while reducing the other within those
bounds. Resizing changes presentation only.

Tablet and mobile stack selected-run strip, chart, and report in that order at
auto height. Desktop resize handles are absent or inoperative there. Controls
wrap into readable rows, trade groups become one column, and required evidence
remains available without page-level horizontal scrolling. Metrics and Trades
retain comfortable space after their final content; the preview's 52-pixel
space and two-CSS-pixel typography increase are evidence, not fixed tokens.

Acceptance viewports include at least `1440×1000`, `1024×768`, and `390×844`.
At each size there is no clipped required content, avoidable horizontal page
overflow, nested vertical report scrollbar, or reliance on hover alone.

### Keyboard and focus behavior

- The tab order follows the visual task order and every action has a persistent
  visible focus indicator.
- Bars and View controls expose their pressed state in text/semantics. Report
  tabs use tab/tab-panel semantics, arrow-key movement, and one active tab.
- Each resize edge is focusable with `separator` semantics, current/minimum/
  maximum values, and arrow-key resizing. Keyboard resizing uses the same
  bounds and effects as pointer resizing.
- Run-history rows and trade groups are keyboard selectable. The explicit Show
  action is the non-pointer route to chart linkage; chart hover is never the
  only source of event detail.
- Opening Change run moves focus into that surface; closing it or confirming a
  selection returns focus to Change run. Escape closes it without changing the
  selected run.
- The proposed accessibility default keeps focus on an activated Show-on-chart
  control and announces the chart change through the text-equivalent status
  region. It also returns focus to the activated Reset layout control and, if
  retained, the proposed Reset range control. No interaction moves focus
  unexpectedly merely because a callback refreshes display content. These
  focus/live-announcement mechanics are proposed accessibility details, not
  owner-ratified product decisions; the underlying Reset layout behavior
  remains accepted.

### Loading, empty and failure states

| Condition | Required operator behavior |
|---|---|
| Results is hydrating | Keep route and selected-run identity stable; mark the affected region busy and show plain loading text without presenting stale data as current. |
| No persisted runs | Show a neutral empty Results state and a link to Run test; do not render sample metrics, trades or chart points as real evidence. |
| Run is queued/running/retrying | Show truthful status and next safe action; unavailable result regions say that persisted evidence is not ready. |
| Run failed/cancelled/timed out | Keep it selectable and show the user-readable error/stop reason before technical diagnostics. |
| Price evidence missing or invalid | Replace the chart with an unavailable/corrupt-evidence state; do not infer bars or markers. |
| Trades absent | Keep valid price/evidence visible and show a neutral no-trades report; closed-trade metrics are unavailable rather than zero unless zero is explicitly persisted. |
| One interval unsupported | Leave its control visible and disabled with a plain-language reason; other truthful intervals remain usable. |
| Artifact is partial/corrupt or lineage mismatches | Show an explicit blocking warning, suppress affected derived visuals and retain validated unaffected evidence only when its basis is clear. |
| Deep-linked run is unknown | State that the requested run was not found; never label another run as the requested one. |
| Display callback fails | Keep the route stable, show a concise retryable message, and place diagnostics in the technical disclosure. No mutation is retried automatically. |

### Acceptance evidence for implementation

The eventual implementation is conformant only when all applicable checks pass:

1. Portable synthetic unit/data-contract tests prove OHLC aggregation,
   supported/unavailable intervals, exact event preservation, containing-bar
   mapping, missing-exit behavior, and closed/open trade and filter semantics.
   Separate authorized private-fixture validation proves the four accepted SPYM
   bar counts; the 366-trade count is an engineering regression only.
2. Registered Dash callback tests prove selected-run isolation, Bars/View
   independence, Show-on-chart linkage, accepted Reset layout boundaries,
   review isolation, route gating, and truthful missing/corrupt states. If the
   proposed Reset range control is retained, test its narrower boundary too.
3. Real-browser tests prove direct deep link, refresh, back/forward, Change run
   selection, route identity after callback hydration, and absence of missing-
   component or unexpected-route errors under ADR 0008.
4. Desktop, tablet and mobile tests prove the responsive/overflow contract,
   normal-flow Metrics and Trades, readable typography, report-tab switching,
   desktop resizing and accepted Reset layout behavior, and no resize
   affordances on smaller layouts.
5. Keyboard-only tests prove Change run selection, tabs, filters, closed/open
   trade selection, every available Show action, all three desktop resize
   edges, and pointer-independent Reset layout activation. If retained, the
   proposed focus-return, Reset range and live-status defaults receive their
   own conditional keyboard and announcement tests.
6. Failure fixtures prove loading, no-run, active, failed, missing-price,
   no-trades, unsupported-interval, corrupt-artifact and unknown-run behavior.
7. Browser diagnostics show no Dash renderer error, uncaught page error,
   unexpected external request, or page-level horizontal overflow. Manual
   owner review then covers comprehension, visual hierarchy and trader-facing
   language; automated checks do not substitute for renewed acceptance.

### Owner-visible implementation boundary

The owner approved the preview's overall selected-run interaction and visual
hierarchy, including the discoverable **Change run** control, direct chart pan
and mouse-wheel zoom, resizable panels, Metrics and Trades. A momentary request
to change mouse-wheel/Control-key behavior was withdrawn after the owner
confirmed the existing zoom interaction already worked. The following details
remain implementation or later-review choices rather than new product gates:

1. the final visual direction: palette, chart rendering style, typography and
   overall density (including whether to return to the earlier blue/white
   treatment);
2. the exact implementation form of **Change run** (anchored panel, drawer or
   dialog), provided it preserves the approved discoverability and behavior; and
3. the opening chart behavior: independently selected initial Bars and View
   values, and what the chart focuses on when no trade is selected. After the
   page opens, Bars and View remain independent as required by Decision 281.

### Engineering defaults

The following are evidence-based implementation defaults rather than separate
owner decisions. An implementation review may change them without changing
product mandate, provided the accepted contract above remains intact:

- Use the validated preview's headline metric quartet (total return, maximum
  drawdown, profitable closed trades, and closed-trade count) before the other
  required performance evidence.
- Make marker-to-ledger linkage bidirectional: ledger actions focus the chart;
  activating a marker selects and reveals its trade group. Never alter or
  visually jitter the exact event time to separate collisions; expose every
  colliding event through the ledger and an accessible count/chooser.
- Begin with 12 trade groups per page, preserving the accepted normal document
  flow. Keep required filters immediately above Trades on wide screens and in
  a labelled expandable filter region when space is narrow.
- Start from the preview's bounded desktop sizing and 20-CSS-pixel keyboard
  resize increment. Switch to auto-height stacking when the controls or content
  no longer fit, rather than treating a device name as authoritative; validate
  that behavior at the three required viewports.
- Persist Bars, View, report tab, selected trade/leg and panel dimensions for
  the current browser session only, scoped by selected run. Keep the run ID in
  the deep link. **Reset layout** clears only stored layout dimensions and
  leaves expanded/collapsed state unchanged; changing run discards incompatible
  trade state.
- Use a separate **Reset range** action and a polite text-equivalent chart
  status region as the proposed usability/accessibility implementation for
  pan/zoom recovery and Show-on-chart feedback. These supplement, and must not
  be confused with, Decision 281's accepted **Reset layout** behavior.
- Keep the proposed below-report order of evidence summary, human review,
  provenance/assumptions and collapsed technical diagnostics because it follows
  the accepted operator task flow. Reordering within that lower section is an
  implementation detail if every required capability remains easy to find.

### Explicit exclusions

This Results specification does not authorize a framework rewrite, TradingView
or QAMC code/asset copying, Lightweight Charts adoption, a persistence-schema
change, research-logic or validation-logic changes, new market data, strategy
discovery, optimization, protected-test evaluation, external-source retrieval,
credentials, paper/live orders, broker/account/order-entry surfaces, production
deployment, Milestone 23 completion, or acceptance of the implemented page.

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
- research-computation cache action, source computation identity and validation
  status when Decision 283 is implemented, without treating reuse as
  independent evidence;
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

23C-1 is complete for the selected-run Results experience under Decision 282.
The approved specification covers the
approved workflow, responsive desktop/tablet/mobile behavior, novice language,
the four persistent selected-run fields, truthful chart/ledger linkage,
progressive disclosure, and labelled technical drill-downs. The separate
Decision 282 scalable multi-run requirement still needs a bounded design; its
exact UI and architecture are not pre-approved. 23C-2 retains the ADR 0008
mounted-route architecture and uses Dash AG Grid and Dash Bootstrap Components
as approved implementation components. Implementation, deployment, automated
and browser testing, licensed-target proof, and renewed owner acceptance of the
implemented Results experience remain pending; 23C-3 also requires real-browser
lifecycle and end-to-end workflow evidence.
