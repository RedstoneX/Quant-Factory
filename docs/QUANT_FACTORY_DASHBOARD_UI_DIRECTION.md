# Quant Factory Dashboard UI Direction

- **Status:** Accepted non-Results 23C-1 specification; Results direction
  accepted under Decision 280 with detailed replacement specification pending
- **Owner direction accepted:** 2026-09-18
- **Objective implementation and browser evidence:** Pending

## Purpose and authority

This document is the implementation-ready page specification for the
Milestone 23C operator experience. It supports, but does not replace,
[`docs/MILESTONES.md`](MILESTONES.md),
[`docs/dashboard-product-requirements.md`](dashboard-product-requirements.md),
[`docs/milestones/milestone-23-acceptance.md`](milestones/milestone-23-acceptance.md),
and [ADR 0008](architecture/0008-dashboard-mounted-route-architecture.md).

The approved research flow is:

**Home → Ideas → Set up → Run test → Results → Compare**

The owner-authorized bounded 23C implementation follows this specification
outside the reopened Results experience. Decision 279 supersedes Decision
277's acceptance for the current Results page. Decision 280 accepts the
chart-first replacement direction recorded below but does not approve this
document as the detailed replacement Results specification. That responsive
specification or mockup and its owner approval remain pending before broad
implementation. This document does not record Milestone 23 completion or waive
implementation, deployment, browser, workflow, failure-handling, testing,
renewed operator acceptance, or documentation evidence. It does not authorize
strategy discovery, external-source retrieval, paper execution or live
trading.

## Product and visual contract

Quant Factory remains a Plotly Dash application. VectorBT Pro remains the
portfolio analytics and Plotly-compatible chart engine. Dash Bootstrap
Components may provide responsive layout and controls; Dash AG Grid is the
approved component for dense interactive tables. No framework migration or
research-logic rewrite is part of this work.

The product should look like a restrained, light-mode trading research
workspace rather than a stack of administrative forms. On Results, the
selected-run truthful price chart is the primary workspace rather than one
report section in a long page:

- selected-run identity, status, evidence outcome, human decision and next safe
  action remain compact and visible without displacing the chart;
- persisted price, entry/exit points and their linked trade records are
  visually primary; equity, benchmark, drawdown, evidence, assumptions and
  review remain immediately reachable supporting analysis;
- one accent colour identifies selection and navigation; green, red and amber
  never carry meaning without a text label;
- cards, charts and grids share consistent spacing, borders and type hierarchy;
- technical identifiers, hashes, storage references and diagnostics appear only
  in labelled drill-downs.

TradingView's current Strategy Report and backtesting-results interaction in
its chart-first Supercharts context is the primary Results UX reference. This
does not import TradingView's live-trading, brokerage, order-entry, position or
account surfaces. QAMC is a secondary reference only for docking, resizing and
chart/ledger-link mechanics; its information density and compressed content
hierarchy are explicitly not the target.

The primary-source interaction evidence checked on 2026-09-18 is TradingView's
[Strategy Report overview](https://www.tradingview.com/support/solutions/43000764138-tradingview-strategy-report-how-to-start/)
and [Pine strategy documentation](https://www.tradingview.com/pine-script-docs/concepts/strategies/):
strategy markers remain on the main chart, the report occupies the chart's
bottom panel, and trade records provide a **Show on chart** path. These sources
are UX references, not a runtime dependency or proof of Quant Factory behavior.

The public-safe concept images in
[`docs/assets/dashboard/approved/`](assets/dashboard/approved/) continue to
define the accepted visual density and hierarchy outside the reopened Results
experience. They contain synthetic data and do not establish implemented
behavior or operating evidence. The prior Results image is retained as
historical design evidence and is not the Decision 280 replacement mockup:

1. `01_research_data_catalog.png` — data catalog and coverage inspection.
2. `02_research_experiment_overview.png` — experiment and outcome overview.
3. `03_research_backtest_detail.png` — chart-led selected result.
4. `04_research_compare_experiments.png` — aligned run comparison.
5. `05_paper_strategy_fleet_overview.png` — later paper direction only.
6. `06_paper_strategy_detail.png` — later paper direction only.
7. `07_system_infrastructure_overview.png` — system-health direction.

Paper mockups are not part of Milestone 23 and must not be used to introduce
deployment, broker, order, position, capital-allocation or live controls.

## Route and navigation contract

The permanent shell contains the brand/Home link, the primary research steps,
the support links, the active-route state and all registered route containers.
The primary labels and URLs are exact:

| Order | Navigation label | URL | Page identity |
|---:|---|---|---|
| 0 | Quant Factory brand / Home | `/` | `Home` |
| 1 | Ideas | `/research/ideas` | `Ideas` |
| 2 | Set up | `/research/setup` | `Set up a test` |
| 3 | Run test | `/research/run-test` | `Run test` |
| 4 | Results | `/research/backtest-results` | `Results` |
| 5 | Compare | `/research/compare-backtests` | `Compare results` |

Support navigation remains visually separate from the numbered flow:

| Navigation label | URL | Page identity |
|---|---|---|
| Market data | `/research/market-data` | `Market data` |
| System status | `/system` | `System status` |
| Data sources | `/system/providers` | `Data sources` |
| Settings | `/settings` | `Settings` |

The brand always returns to `/`. Durable review belongs to the Results review
area; it is not a seventh workflow step. The completed transitional
`/research/strategy-review` address is retired and renders Page Not Found like
any other unknown route. It is neither a duplicate primary-navigation
destination nor a hidden compatibility surface. Existing Paper Trading routes
may remain read-only pending pages during the transition, but are not primary
Milestone 23 navigation and expose no operational controls.

Every final registered route has one real, permanently mounted container. Route
changes alter container visibility and active-link styling only. There is one
persistent `dcc.Location`; `pathname` remains the route source of truth. No
page callback writes the URL, rebuilds navigation, renders another page, or
uses dynamic `page-content.children` replacement as routing.

## Shared operator shell

Every workflow page uses the same shell and page-heading pattern:

1. eyebrow showing **RESEARCH / [STEP]**;
2. one unambiguous page identity heading;
3. one sentence explaining what the operator can decide here;
4. a compact workflow progress indicator with the current step labelled;
5. page-local primary action at the right on wide screens and below the heading
   on narrow screens;
6. user-readable loading, empty, blocked and failed states in the content area.

When a run is selected, the persistent run-context quartet defined below sits
directly below the heading on Run test, Results and Compare. It remains visible
while the operator changes tabs, filters, trade selection or chart range. On a
page with no selected run, the quartet is replaced by a plain-language empty
state; placeholder values must not resemble evidence.

## Page specifications

### Home — `/`

**Purpose:** orient the operator and identify the next safe action.

Show:

- research-system and local data readiness in plain language;
- current milestone and the discovery gate;
- the most recent selected or active run, if one exists;
- recent failures that require attention;
- the six-step research path with completed, current and unavailable labels;
- one primary **Continue research** action that opens the next valid step.

Home is an overview, not an execution surface. It never launches, retries,
cancels, reviews or reproduces a run. If health is not checked, say **Not
checked** rather than implying healthy. If there is no work yet, the primary
action is **Capture an idea**.

### Ideas — `/research/ideas`

**Purpose:** safely capture what might be tested later without retrieving or
executing anything.

The page may show and accept:

- a short owner-authored title and description;
- an optional source URL stored as text only;
- source type and attribution supplied by the operator;
- assumptions, questions and uncertainty notes;
- local draft state with **Save draft** and **Discard draft**;
- a clear **Draft only — nothing will run** status.

During Milestone 23, Ideas must not:

- fetch, preview, download or summarize a URL;
- execute submitted text, code or instructions;
- create or approve a strategy hypothesis;
- create a launchable configuration;
- launch, queue or reproduce a backtest;
- promote a strategy or place an order.

The forward action is **Continue to Set up**. It carries only operator-authored
draft text or a safe draft identity. It does not imply approval. External
retrieval, untrusted-content handling and approval-to-configuration handoff are
Milestone 25 work.

States:

- **Empty:** explain what an idea draft is and offer **Start a draft**.
- **Unsaved:** label local changes and require confirmation before discard.
- **Saved:** show saved time and the next safe action.
- **Invalid URL:** retain the text, explain the format problem and do not fetch.
- **Save failed:** keep the editable draft, explain that it was not saved and
  offer retry without duplicate creation.

### Set up — `/research/setup`

**Purpose:** inspect and choose an approved immutable fixture configuration
before any work starts.

Show:

- approved instrument, strategy/fixture and saved-configuration selectors;
- bounded parameter controls defined by the approved specification;
- requested data period, provider, timeframe and local availability;
- sizing, timing, fee and slippage assumptions;
- configuration readiness and every blocking reason;
- a persistent warning that fixture results prove infrastructure, not profit;
- a read-only summary of the exact configuration that will be used.

The operator may edit a page-local setup draft. **Save configuration** creates
or selects an immutable persisted configuration through existing service
boundaries. The forward action is **Review test**, linking to Run test with the
persisted configuration identity. Set up does not launch a run.

States:

- **No approved choices:** say which prerequisite is missing and link to the
  relevant support page.
- **Loading:** preserve labels and layout while controls are disabled.
- **Invalid or unsupported:** list field-level corrections before the summary;
  no launch path is enabled.
- **Data unavailable:** show the affected period/provider and safe remedy; never
  silently substitute data.
- **Save conflict/failure:** preserve the draft, make no partial configuration
  appear saved, and offer a safe retry.

### Run test — `/research/run-test`

**Purpose:** perform the final human review, launch exactly once, and observe
run state without mixing launch controls into analysis.

Before launch, show a read-only configuration summary, data/provenance summary,
execution assumptions, preflight checks and fixture warning. The single primary
action is **Run test**. It remains disabled until the configuration is persisted,
launchable and passes preflight.

Launch requires an explicit click. While submission is unresolved, disable the
button and show **Starting test…**. A successful response displays the run
identity, the persistent quartet, an event/status timeline, **View results** and
only the safe actions valid for the current state. Refresh must reopen the same
persisted run; an inactive mounted page must not submit, retry, cancel or
recover anything.

States:

- **No configuration selected:** link back to Set up.
- **Preflight blocked:** list every blocking reason and the page where it can be
  corrected.
- **Queued/running/retrying:** show explicit text status and last update; do not
  fabricate progress percentages.
- **Submission unknown:** state that a retry could duplicate work, reconcile
  first, and keep launch disabled.
- **Failed/cancelled/timed out:** keep the run visible, explain impact and show
  only a valid retry/reproduce or return-to-setup action.
- **Succeeded:** show **View results**; success means the run completed, not
  that its evidence passed.

### Results — `/research/backtest-results`

**Purpose:** understand what happened, whether the evidence is usable, and what
human decision is required.

Decision 280 accepts this direction; exact layout, labels, dimensions and
responsive behavior still require a detailed mockup or concise specification
and owner approval:

- keep selected-run identity and the persistent quartet in a compact context
  strip that does not crowd out the primary workspace;
- make the selected persisted run's truthful OHLC/price chart the primary
  workspace; never fabricate or reconstruct missing prices or trade points;
- plot entry and exit markers at the persisted trade timestamps and prices;
- link the chart to a ledger grouped by completed trade, with entry and exit
  detail, so selecting a trade brings its interval into view and identifies
  the corresponding markers; provide an explicit keyboard-accessible
  **Show on chart** action rather than relying only on row click;
- place performance summary, equity and benchmark, drawdown, evidence,
  assumptions/data, lineage, review, reproduction and comparison in a
  progressively disclosed dock or adjacent analysis surface while preserving
  the chart context;
- keep searchable/filterable run history as a secondary **Change run** surface,
  not a large table above or before the primary chart; and
- use TradingView's backtesting Strategy Report for interaction hierarchy and
  QAMC only for panel, resizing and linked-selection mechanics.

The default selection remains a persisted evidence-backed fixture run, never a
fabricated example. Saving a review records the prior state, new state, time,
note and responsible operator through the existing durable service.
**Reproduce** creates a distinct run from the immutable saved configuration and
preserves parent identity. The detailed replacement specification must decide
the final analysis labels and information grouping before implementation.

States:

- **No runs:** explain that a test must be launched and link to Set up.
- **Loading selection:** keep run identity visible and mark evidence as loading.
- **Missing or corrupt artifact:** identify unavailable sections, mark the
  evidence invalid/unavailable, and never reconstruct values.
- **Failed run:** show the failure before empty charts and provide the next safe
  action.
- **Review conflict:** preserve the operator's entered note, show that no change
  was saved and require refresh/review before retry.
- **Metric unavailable:** retain the KPI position and use **Unavailable** with a
  reason, not zero.

### Compare — `/research/compare-backtests`

**Purpose:** compare two or more persisted runs without hiding differences that
make a comparison unsafe.

Show:

- selected-run cards with strategy, instrument, timeframe, period and outcome;
- the quartet for each selected run, not one blended status;
- normalized equity and drawdown charts with labelled series;
- aligned metrics with metric-basis warnings;
- parameter, data/provider/date, cost and execution-assumption differences;
- validation-stage and human-review differences;
- explicit comparability warnings before the charts;
- links back to each full Results page.

Comparison selection is independent of the Results selection and never changes
the selected run on another page. Adding or removing a run does not execute or
reproduce it.

States:

- **Fewer than two runs:** explain how to add another persisted run.
- **No comparable runs:** retain selections, list the incompatibilities and do
  not imply that aligned charts are meaningful.
- **Partial evidence:** render only supported sections and label every omission.
- **Loading/failure:** keep selected identities visible so the operator knows
  what was requested; retry only the read.

## Persistent selected-run quartet

Every selected-run context presents these exact labels and meanings:

| Label | Meaning | Examples |
|---|---|---|
| Run status | Orchestration state only | `Queued`, `Running`, `Succeeded`, `Failed`, `Cancelled`, `Retrying` |
| Evidence outcome | Research-evidence conclusion | `Passed`, `Failed`, `Insufficient evidence`, `Invalid`, `Not run` |
| Human decision | Latest durable operator review | `Unreviewed`, `Revise`, `Reject`, `Infrastructure fixture`, `Watchlist`, `Approved for next evidence stage` |
| Next safe action | One plain-language action allowed by current evidence and gates | `Wait for completion`, `Review failure`, `Inspect evidence`, `Record decision`, `No action available` |

Run status must never be presented as evidence outcome. Evidence outcome must
never be presented as human approval. A successful fixture run must not imply a
profitable or deployable strategy. The quartet uses text and, secondarily,
icons/colour. Its values come from persisted orchestration, evidence and review
records; missing values are **Unavailable** or **Not run**, never inferred.

## State ownership

Each browser-visible state has one owner:

| State | Owner and persistence rule |
|---|---|
| Active route | `dcc.Location.pathname`; routing callbacks derive visibility and active navigation only. |
| Idea draft | Ideas page; browser/session draft until a safe draft record is explicitly saved. It is never executable. |
| Setup draft | Set up page; page-local/session state. It is not launchable until explicitly saved as an immutable configuration. |
| Selected configuration | Persisted configuration identity chosen by Set up; Run test reads it and cannot mutate it. |
| Launch submission | Run test page; explicit click plus server-side idempotency owns exactly-once submission behavior. |
| Selected result | Results page and its session store; explicit operator selection wins over refresh/hydration. |
| Review form | Results review area; its selection, note, conflict and save message are page-owned. |
| Comparison selection | Compare page; independent of Results selection and preserved only for the comparison workflow. |

Cross-page movement uses ordinary operator links and persisted identities. Page
callbacks may update controls and links inside their own route container, but
must not write the URL or mutate another page's selection. Passive refreshes
must never overwrite an explicit choice. Expensive or mutating callbacks check
that their route is active and that the initiating operator action occurred.

## Responsive contract

All workflow actions and decision fields remain available without horizontal
page scrolling.

### Desktop — 1200 px and wider

- persistent left navigation and full page heading/actions;
- 12-column content grid;
- quartet in one four-card row;
- the Results price chart uses the dominant width and height; its supporting
  analysis dock may resize or collapse without unmounting or losing selection;
- AG Grid uses the full panel width with important columns pinned first.

### Tablet — 768–1199 px

- collapsible navigation drawer with the active page named in the header;
- content uses six columns; quartet becomes a two-by-two grid;
- the Results price chart remains first and the analysis surface moves below
  it when side-by-side layout would compress either surface;
- grids retain a useful minimum column width and scroll inside their panel.

### Mobile — below 768 px

- navigation opens from a labelled menu button and closes after selection;
- page heading, actions, cards and charts form one column;
- quartet remains near the top as four full-width labelled rows;
- the primary action is full width and remains after explanatory text;
- the Results price chart remains ahead of its analysis sheet; chart-linked
  trade records use an essential-column or stacked-card profile with an
  accessible row-detail view for omitted fields;
- grids may scroll only inside their own bounded panel when an accessible
  alternative cannot preserve all required values; the page itself does not
  scroll horizontally;
- tabs may scroll horizontally, but tab labels and active state remain visible;
- charts keep readable axis/legend text and never replace evidence with a
  simplified invented value.

At every size, direct links, refresh, back/forward, selected state, active
navigation, focus order and all required operator actions must work in a real
browser. Responsive acceptance covers content and interaction, not screenshots
alone.

## Trader-facing vocabulary

Use the first term in normal operator copy; reserve the second for labelled
technical details:

| Operator term | Technical term |
|---|---|
| Test / backtest | experiment run / run ID |
| Saved setup | configuration record / configuration hash |
| Strategy checks | evidence stages / artifact schema |
| Data used | manifest / checksum / cache action |
| Related tests | parent/child lineage |
| Problem details | exception / diagnostic reference |
| Review decision | review-state event |

Use **Set up**, not “parameterization”; **Run test**, not “invoke
orchestration”; **Results**, not “artifact output”. Established finance terms
such as drawdown, benchmark, slippage and profit factor include short help text
where a novice could misread them.

Bounded numeric values may use sliders when visual adjustment is useful, with
the exact value also visible and keyboard-operable. Identifiers, timestamps,
categorical policies and values requiring exact entry use dropdowns, toggles,
text inputs or read-only fields instead.

## Loading, empty and failure behavior

Every page has explicit loading, empty, blocked, failed and ready behavior:

- loading preserves page identity and current selection and disables mutations;
- empty states explain why the page is empty and provide one safe next action;
- blocked states name every unmet prerequisite;
- failures lead with operator impact and next safe action, with diagnostics in
  an expandable technical section;
- stale data displays its observation time and never claims current health;
- failed and cancelled runs remain discoverable in history;
- partial artifacts never render as successful results;
- retry and cancellation are explicit, state-valid and idempotent;
- placeholder text is visually distinct from an entered value.

## Technical drill-down boundary

The primary workflow may show strategy, instrument, timeframe, dates, cost
assumptions and human-readable provenance. These belong under **Technical
details**, **Lineage**, **Diagnostics** or **Data verification** unless required
to resolve a visible failure:

- internal run, artifact and configuration identifiers;
- hashes and schema versions;
- file paths, storage locations and raw manifest references;
- callback, process, worker and database implementation names;
- exception text, stack traces and structured logs;
- raw JSON, CSV or SQLite content;
- recovery tools and stale-run cutoffs.

Technical drill-downs are read-only by default. Advanced recovery actions stay
under a separately labelled **Operations / diagnostics** area, require explicit
inputs and remain governed by current recovery rules. A technical panel may
explain a failure but can never be the only explanation.

## Implementation and acceptance boundary

Implementation should preserve existing services, persistence, evidence,
orchestration and accepted fixture behavior while separating the older mixed
launch/results page into the defined workflow. Reuse existing component IDs
where their meaning still matches; do not keep misleading names through hidden
aliases or test-only presentation.

23C-2 is complete only when focused and relevant full tests pass and all route
containers/callback ownership comply with ADR 0008. 23C-3 additionally requires
real-browser proof for every registered route at desktop, tablet and mobile
sizes, the complete operator workflow and failure behavior, and renewed owner
acceptance of the implemented replacement Results experience. Decision 280
accepts the chart-first direction only: detailed specification approval,
implementation, deployment, tests and renewed operator acceptance remain
pending.

## Explicit exclusions

This specification does not authorize:

- Milestone 25 source fetching, hypothesis extraction, discovery,
  optimization or protected-test evaluation;
- automatic approval or launch from an Idea;
- backend, evidence, persistence or orchestration redesign;
- paper-account, broker, order, position, allocation or reconciliation work;
- live trading, capital changes or credential access;
- a new dashboard framework, commercial-grade polish or dark mode;
- production deployment or changes to a production runtime.
