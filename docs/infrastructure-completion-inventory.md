# Quant Factory Infrastructure Completion Inventory

## Purpose

This document preserves the research-factory requirements and historical gap inventory. [MILESTONES](MILESTONES.md) is the authority for current status and active work. The baseline-state and planned-work columns below predate later implementation: they are historical context, not current defect findings or a second queue. Verify code and current acceptance evidence before reopening a listed gap. Existing RSI, MES ORB, and SPY Donchian implementations are retained as deterministic infrastructure fixtures and historical evidence. They are not active profitability candidates.

The normal operator experience must occur through the dashboard. Python modules, terminal commands, CSV files, JSON artifacts, and backend logs are implementation details rather than the primary product interface.

## Work-allocation rule

Every task is assigned in this order:

1. **ChatGPT direct** — planning, architecture, documentation, GitHub inspection, remote documentation commits, acceptance review, and small isolated repository changes that do not require the local runtime.
2. **WSL copy/paste** — short, safe commands the user can run directly when local state must be observed or a service launched.
3. **Claude Code local implementation** — executable multi-file implementation, VectorBT Pro integration, local artifacts, tests, migrations, debugging, and local Git validation.

Under ordinary routing, Claude Code must not receive documentation-only or
planning work that ChatGPT can complete directly. While the lead is
orchestrating, delegable documentation follows the agent-policy qualification.
Current agent allocation and the bounded revival exception are defined in [the
agent policy](ai-programming-agent-policy.md).

## V1 completion inventory

| Component | Historical baseline state | Planned requirement (verify current evidence) | Classification | Dependencies | Acceptance test | Dashboard exposure | Owner/tool |
|---|---|---|---|---|---|---|---|
| Repository and environment | WSL clone, Python 3.12, VectorBT Pro, Git hygiene and tests exist | Automated environment health summary and visible dependency/version status | Required | None | Clean clone/environment can run fixture workflow and report versions | System status page | Claude Code local implementation |
| Market-data providers | Yahoo daily equity provider works; additional providers partially implemented | Complete operational equity fixture provider flow before other asset classes | Required | Credentials, manifests | Dashboard-triggered fixture load returns validated current data | Data-source status | Claude Code local implementation |
| Cache and provenance | Typed market-data cache, calendar, validation and audit exist; CI caches Python dependencies; deliberate new/reproduction runs recompute research outputs | Persist provenance with every experiment record and expose cache decisions; design safe reuse for exact repeat research computations while preserving a distinct durable ticket/lifecycle for each request, isolating every result-changing input and protected-data partition, rejecting failed/partial/corrupt/unknown work, and never counting reuse as independent evidence; identity/keying mechanism, storage, schema, eviction, sequencing and explicit Reproduce policy remain undecided | Required | Experiment database, artifact integrity, immutable input identity, ADR 0011 | Prior run displays exact source, dates, adjustment and cache action; a future cache hit is validated and traceable to one source computation, while mismatches fail closed and every explicit request retains its own lifecycle | Run detail/provenance | ChatGPT bounded design; Claude Code local implementation after approval |
| Dataset manifests | Catalog and manifests exist for imported datasets | Standardize equity fixture manifest and verification state | Required | Equity fixture decision | Manifest identity and checksum are queryable | Dataset detail | Claude Code local implementation |
| Credentials and secure injection | Policy exists; secure injection milestone pending | Implement allow-listed, non-repository credential injection and health checks | Required before authenticated providers/brokers | OneCLI proof of concept and approved injection | No secret appears in Git, logs or UI; provider health succeeds | Redacted integration status | Claude Code local implementation; user may approve login prompts |
| Strategy contract | Typed strategy interface exists | Freeze fixture-compatible V1 contract and versioning rules | Required | Registry | Contract/version mismatch fails clearly | Strategy detail | ChatGPT architecture; Claude Code tests |
| Strategy registry | Durable SQLite-backed versioned records exist for strategy identity, lifecycle classification and active state | Dashboard UI integration and operator-facing lifecycle controls | Required | Experiment database | Dashboard lists versioned fixtures and lifecycle state | Strategy catalog | Claude Code local implementation |
| Experiment configuration | Immutable configuration records, canonical JSON and SHA-256 hashes exist in the local database | Saved-configuration UI and orchestration integration | Required | Registry, database | Operator can select and reproduce a configuration without editing Python | Experiment launch | Claude Code local implementation |
| Run orchestration | Individual scripts exist | Unified run service with queued/running/succeeded/failed/cancelled states | Required | Database, logging | Dashboard launches fixture run and shows status to completion | Run queue/status | Claude Code local implementation |
| Job resumability | Not implemented | Idempotency, retry policy, stale-job detection and safe cancellation | Required | Orchestration | Interrupted fixture run can fail/retry without corrupting records | Job controls | Claude Code local implementation |
| Experiment database | SQLite schema version 1 exists at `state/quant_factory.sqlite3` with migrations, repositories, fixture-result adapter and review audit history | Orchestration, artifact-envelope and dashboard integration | Required | Schema decision | Run history survives restart and is queryable | History and comparisons | Claude Code local implementation |
| Run lineage | Partial provenance in result objects | Parent/child relationships across screen, OOS, walk-forward and stress stages | Required | Database, artifact schema | Every derived run links to exact inputs and predecessor | Lineage view | Claude Code local implementation |
| Artifact schemas | Several independent schemas exist | Unified versioned envelope and validation for all artifact types | Required | Database | Invalid artifact is rejected; valid artifact renders consistently | Artifact/evidence panel | ChatGPT schema design; Claude Code implementation |
| Artifact storage and retention | Git-ignored local files | Managed paths, indexing, retention and missing-artifact handling | Required | Database | Dashboard opens indexed artifact and reports missing files safely | Artifact browser | Claude Code local implementation |
| Cheap screening | Implemented and tested | Integrate status/reasons into unified evidence model and UI | Required | Artifact schema | Fixture row shows every rule and rejection reason | Evidence page | Claude Code local implementation |
| Out-of-sample | Implemented and fail-closed | General dashboard adapter and lineage integration | Required | Database, schemas | Partitions, shortlist, lock and stop reason render correctly | OOS view | Claude Code local implementation |
| Walk-forward | Implemented | General dashboard adapter, fold navigation and aggregate evidence | Required | Database, schemas | Folds and failures are understandable without JSON | Walk-forward view | Claude Code local implementation |
| Parameter/regime robustness | Engine exists | Standard adapter and evidence visualization | Required as infrastructure, not an active strategy run | Schemas | Deterministic fixture artifact renders neighborhood/regime evidence | Robustness view | Claude Code local implementation |
| Monte Carlo | Engine exists | Standard adapter and distribution/risk visualization | Required as infrastructure, not an active strategy run | Schemas | Deterministic fixture artifact renders distributions and thresholds | Stress view | Claude Code local implementation |
| Result comparison | Minimal row selection only | Compare runs, parameters, metrics, curves, assumptions and evidence | Required | Database | Operator selects two or more runs and sees aligned differences | Compare page | Claude Code local implementation |
| Reproducibility | Configuration/provenance partially recorded | One-click rerun from immutable saved configuration with version checks | Required | Database, orchestration | Reproduced fixture matches expected deterministic outputs or explains drift | Reproduce control | Claude Code local implementation |
| Logging and errors | Terminal/errors exist | Structured run logs, user-readable error summaries and diagnostic references | Required | Orchestration | Failure is visible and actionable without terminal access | Run status/error drawer | Claude Code local implementation |
| Failure recovery | Mostly manual | Safe retry, cancellation, stale lock cleanup and incomplete-artifact handling | Required | Logging, jobs | Injected fixture failure recovers without database corruption | Operational status | Claude Code local implementation |
| Equity instrument/execution profile | SPY historical fixture exists | Select affordable liquid broad-market ETF; define whole-share and limit-order policies | Required | Verified instrument decision | One- or two-share paper/live path is feasible and assumptions display | Instrument/execution detail | ChatGPT research/decision; Claude Code integration |
| Dashboard navigation | Single-page minimal dashboard | Multi-page product navigation with consistent run context | Required | Database adapters | Operator reaches launch, history, results, evidence, compare and system status | Entire product | Claude Code local implementation |
| Dashboard experiment launch | Not implemented | Approved dropdowns/forms, validation and job submission | Required | Orchestration | Fixture run launches without Python or terminal | Launch page | Claude Code local implementation |
| Dashboard history | Not durable | Searchable/filterable persistent run history | Required | Database | Runs remain after restart and can be reopened | History page | Claude Code local implementation |
| Dashboard multi-run analysis | No dedicated large-run analysis surface in the historical baseline | Design a separate scalable surface that aggregates, slices, ranks, filters and selects hundreds or thousands of persisted runs by maximum drawdown, total return, profitable-trade measures and other useful evidence dimensions; one selected run opens in Results and multiple selected runs can feed Compare | Required | Database, validated metric definitions, Results and Compare selection contracts | The bounded design is approved before implementation; large persisted-run sets remain truthful and usable without overloading selected-run Results | Separate analysis surface; exact name and design pending | ChatGPT product design; Claude Code local implementation |
| Dashboard charts | Equity and drawdown for selected RSI row | Selected-run truthful price chart as the primary Results workspace; separate Bars and View controls; truthful persisted-OHLC aggregation; resettable desktop chart/report resizing; supporting VectorBT-backed equity, drawdown and benchmark analysis | Required | Artifact adapters | Persisted charts render for a stored fixture run without rerunning the grid or reconstructing missing evidence; the validated preview fixture produced 53,528/13,340/4,474/173 bars for 1m/5m/15m/1D, which is evidence rather than a universal count target; resize/reset and responsive stacking preserve selected state | Results page | Claude Code local implementation |
| Dashboard trades | Not complete | Persisted entries/exits on the price chart linked to a ledger grouped by completed trade; exact events map to containing bars; accessible drill-down uses visibly larger, more readable typography and normal page flow without nested vertical scrolling | Required | Portfolio/trade artifact | Selecting a fixture trade focuses useful entry/exit context and exposes exact timestamps, prices, size, costs and P&L at every supported bar interval; page retains comfortable bottom breathing room; the validated preview's 52-pixel spacing and two-CSS-pixel typography increase are evidence rather than fixed targets | Results chart and trade ledger | Claude Code local implementation |
| Dashboard evidence explanations | Minimal review status | Unified pass/fail/insufficient evidence, rule details and stage progression | Required | Evidence model | Operator understands why progression stopped | Evidence page | Claude Code local implementation |
| Dashboard run comparison | Not implemented | Side-by-side metrics, curves, assumptions and evidence differences | Required | Database | Two stored runs compare without manual files | Compare page | Claude Code local implementation |
| Dashboard data provenance | Basic selected-row display | Complete source, coverage, adjustment, manifest and cache status | Required | Provenance persistence | Operator can verify exactly what data a run used | Provenance panel | Claude Code local implementation |
| Dashboard execution assumptions | Basic selected-row display | Full timing, sizing, fees, slippage and future order-policy presentation | Required | Configuration records | Operator can inspect all assumptions before and after run | Assumptions panel | Claude Code local implementation |
| Dashboard operational status | Not implemented | Provider, database, worker, artifact and credential health | Required | Orchestration/integrations | System problems visible before launch | System status page | Claude Code local implementation |
| End-to-end acceptance tests | Component tests exist | Browser-facing workflow and deterministic full-stack fixture acceptance | Required | Milestones 17–22 | Launch fixture, persist, render, compare, reproduce and explain failure entirely through UI | Acceptance report in dashboard | Claude Code local implementation; user acceptance |
| Paper/live boundaries | Policies only | Define interfaces now; implement only after research factory and strategy approval | Future | Accepted research factory | No broker action available before later milestone gates | Future operations pages | ChatGPT architecture; later Claude Code |

## Design dependency order (not the active queue)

1. Durable registry and experiment database.
2. Unified artifact schemas and lineage.
3. Run orchestration, logging, job state and recovery.
4. Dashboard adapters, navigation, history, launch, results and comparisons.
5. Verified affordable equity fixture and operational equity-data flow.
6. Unified validation/evidence presentation.
7. Full end-to-end equity research factory acceptance.

## Hard gate

No systematic strategy discovery, optimization for profitability, or promotion
search may resume until Milestone 23 passes. Decisions 280–282 accept the
chart-first direction, validated preview constraints and detailed selected-run
Results specification. Selected-run implementation, deployment, automated and
browser testing, licensed-target proof, final owner acceptance of the eventual
implemented page, the bounded scalable multi-run design, and the remaining
objective technical gates are not yet complete.
