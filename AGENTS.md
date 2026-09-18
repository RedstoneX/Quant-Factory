# Quant Factory Agent Instructions

The permanent AI-agent collaboration rules are in
[`docs/ai-programming-agent-policy.md`](docs/ai-programming-agent-policy.md).
Documentation work must also follow
[`docs/DOCUMENTATION_GOVERNANCE.md`](docs/DOCUMENTATION_GOVERNANCE.md).
Claude Code must also follow [`CLAUDE.md`](CLAUDE.md) and run the
`implementation-preflight` project skill before executable implementation.

## Start and source of truth

The closed Tier 1 set is `AGENTS.md` (working contract),
`docs/MILESTONES.md` (product intent, current status, ordered active work and
acceptance), and `docs/DECISIONS.md` (owner decisions and supersessions).
Read current scope and relevant decisions before acting. Supporting documents
have the roles defined in `docs/DOCUMENTATION_GOVERNANCE.md`; none may create
a competing mandate, status, or plan.

At the initial revival handoff, summarize this understanding and obtain the
project owner's confirmation before writing application code. The owner
confirmed the scoped full-authority revival on 2026-09-02; carry that
authorization forward within its approved scope and do not repeatedly ask.

## Communication and evidence

- Lead with the answer, current phase, next action, and real blocker. Use short lines or point form and keep the overview to six short bullets or fewer.
- Report what changed, why, what was verified, and any decision needed. Mention material scope exclusions when they affect the result. Keep unnecessary paths, IDs, and implementation detail in linked evidence.
- Say when something is unknown, unverified, or inferred. Do not round partial success up to completion or use fabricated precision.
- Check the assertion that the next action depends on, cheaply and adversarially. For a test-pass claim, inspect the result and counts; for a causal claim, reproduce the symptom; for "never worked," look for a counterexample.
- Verify dates, durations, and history from Git, filesystem, or recorded runtime evidence rather than impression. Distinguish proposed, implemented, tested, merged, deployed, and operator-accepted work.
- Do not reopen a defect from stale notes alone. Report newly verified pre-existing problems in ordinary language; discovery is not authorization to repair unrelated work.
- Run the narrowest decisive validation first. Broaden only for a concrete remaining risk and stop when the result is proven.
- Correct demonstrably wrong documentation on sight without another permission request; check the existing primary home first. A factual correction must not silently change mandate, scope, architecture, or acceptance.
- Attribute agent-chosen scope cuts, deferrals, or simplifications to the agent and state the reason. Trace unattributed mandate constraints to their source; if still unverified, ask the project owner before relying on them.
- Only the project owner ratifies mandate or policy changes. An agent's proposal or its own merge is not owner ratification. Explicit owner instructions to adopt or record a rule count as acceptance.
- Record owner corrections and explicitly confirmed unusual successful approaches in the proper standing-rule document, with context and boundaries. Do not leave them only in chat or generalize one success into unlimited scope.
- Keep AGENTS a curated contract, current work an ordered queue, and completed incidents in readable history. Follow the document lifecycle and enforcement-status distinctions in `docs/DOCUMENTATION_GOVERNANCE.md`.
- Use explicit text labels for status; the operator must not need to distinguish red from green to understand the result.

## Repository

- Resolve the active checkout from `QF_REPO_ROOT`; public examples use
  `/srv/quant-factory/repo`. Isolated task worktrees must have explicit
  ownership. Never treat an unrelated clone as authoritative.
- Decision 275's controlled migration is complete. The clean-history public
  `RedstoneX/Quant-Factory` repository is canonical and is the sole forward
  source of truth. The original repository remains private, read-only
  historical evidence; never rewrite or delete its history or treat it as a
  development remote.
- Use `main` as the accepted integration baseline. Use dedicated branches and PRs for substantive work; never push changes directly to `main` or force-push. Review and preserve any existing branch/worktree state before changing it.
- On the public canonical repository, require the applicable CI checks for
  pull requests. Decision 276 permanently sets GitHub's strict/up-to-date
  requirement to `false` unless the owner changes that decision. Independent
  green pull requests may merge without rebasing, updating, or rebuilding
  solely because another independent pull request merged first. CI concurrency
  is per ref and no merge queue is used. Keep required checks and admin
  enforcement enabled; keep repository auto-merge and merged-branch deletion
  enabled. Overlapping or dependent changes must still be integrated serially
  and retested against the resulting `main`; this throughput rule is not
  permission to merge incompatible work.
- Never use the retired Windows clone for development.
- GitHub remains authoritative for committed state and the owned worktree for
  live local state. External recovery snapshots are temporary evidence only.
- Never run destructive Git commands without explicit instruction.
- Stage explicit owned paths only; never use `git add -A` or `git add .`.
- Never use a bare `git stash`. Prefer an isolated task worktree from the active repository when needed to preserve concurrent work. If a stash is necessary, give it a unique name, record its exact object identity and owned paths, and verify that identity before restoration or removal; stash refs are shared across sessions.
- Keep rollback possible and preserve other sessions' edits. Concurrent writers must have separate directories/worktrees; a separate branch alone does not isolate files in one working tree.
- Never commit secrets, credentials, downloaded market data, generated result files, environment files, or machine-specific artifacts.
- Commit and push executable work only after its diff and required validation are reviewed.

## User Git-operation boundary

- The user does not independently operate Git or GitHub synchronization and is not expected to infer Git commands.
- Repository-changing Git work must be completed by ChatGPT through an available repository tool, by one exact bounded command beginning with `clear`, or by one explicit bounded Claude Code instruction.
- Codex is retired from ordinary project work. The owner's 2026-09-02 full-
  authority revival authorization reauthorizes the current assistant for the
  scoped revival, including root-cause repair, extensive testing, and reviewed
  repository operations needed to push and merge. The scope and supersession
  are recorded in DECISIONS and the agent policy.
- Never tell the user merely to pull, sync, merge, rebase, reset, or resolve conflicts.
- Before a repository-changing command, state the concrete change, any material scope exclusions, stop conditions, and verification output.
- A permanent rule is not established until it is recorded under the documentation-governance procedure.

## Mission and current direction

- Quant Factory is a private system for Terry, its single owner/operator, to
  find and validate a trading edge and pursue consistent market income. It is
  not an enterprise product, SaaS offering, software-sales project, or
  multi-user/team platform. Multitenancy, customer onboarding, billing,
  organization administration, and features that exist only for hypothetical
  external customers are out of scope unless the owner separately approves
  them.
- Quant Factory is infrastructure first, evidence first, dashboard first, and operating-proof first.
- The goal is to reject false edges, preserve reproducible evidence, paper trade qualified strategies, reconcile model and venue state, and deploy only tightly bounded capital under explicit human approval and independent risk controls.
- The dashboard is the primary operator interface. Python, terminals, raw CSV/JSON, and backend logs are implementation details.
- RSI, MES opening-range breakout, and SPY Donchian are infrastructure fixtures and historical evidence, not active profitability candidates.
- Decision 279 supersedes Decision 277's acceptance of the former Results-page
  comprehension and flow. Decisions 280–281 establish the chart-first and
  validated-preview requirements. Decision 282 records the owner's hands-on
  approval of the detailed selected-run Results specification and authorizes
  its implementation. A separate scalable multi-run analysis surface must
  aggregate, slice, rank, filter and select hundreds or thousands of persisted
  runs; its exact design remains pending. Selected-run implementation,
  deployment, tests, licensed-target proof, and renewed acceptance of the
  eventual implemented page remain pending. Strategy
  discovery remains blocked until Milestone 23 passes those gates and its
  remaining browser-lifecycle, end-to-end workflow, failure-handling, and
  documentation/status-synchronization gates.
- Decision 283 requires safe reuse of validated results for exact repeat
  research computations so repeats are materially faster than rebuilding all
  computation. Every explicit request still receives its own durable run
  ticket and lifecycle. Reusable computed artifacts must be validated,
  traceable, isolated by every result-changing input and protected-data
  boundary, and must never turn one computation into multiple independent
  evidence observations. Failed, partial, corrupt, or unknown work is not
  reusable. Cache architecture, identity/keying mechanism, storage, eviction,
  implementation sequence, and whether explicit **Reproduce** bypasses or
  verifies cached work require a bounded design before implementation.
- Under Decisions 259 and 262, research-only Docker/Compose packaging,
  deployment preparation, broker-neutral contracts, isolated paper-adapter
  implementation, tests, and target validation may proceed in parallel with
  Milestone 23. Any use of harmless or paper credentials requires the existing
  ADR 0010 credential-isolation proof and the documented account-ownership
  boundary, except for the one-shot operator check in Decision 271. This does not
  authorize paper-order activation, discovery, protected tests, optimization,
  live capital, or completion of Milestone 24. Decision 266 separately
  authorizes authoritative OVH research-runtime migration after backup,
  reconciliation, private-access, restart, restore, and rollback checks; this
  does not accept Milestone 23 or authorize execution.

- Private dashboard availability requires owner authorization, authenticated
  private networking, and target-environment proof. Provider-specific private
  coordinates remain external to the public repository.

## Reuse before custom implementation

- Before custom implementation, inventory the existing Quant Factory code and
  tests, licensed dependencies including VectorBT Pro, owner-approved
  prototypes, and mature maintained external components or reference projects
  that may already solve the need. Start with
  [`docs/component-reuse-audit.md`](docs/component-reuse-audit.md) where
  relevant, but revalidate its candidate fit and licensing for the current
  task rather than treating historical evaluation as current proof.
- Compare candidates for functional fit, license and legal use, security,
  maintenance health, integration cost, and truthful handling of Quant
  Factory data and evidence. Prefer adapting or integrating a suitable proven
  component over recreating it.
- Custom code is permitted only for a verified product-specific gap or when
  reuse is materially worse under that comparison. Record the inventory,
  selected reuse, remaining gap, and custom-code rationale in implementation
  preflight before writing executable code.
- Do not recreate mature commercial-grade dashboard, charting, grid, panel,
  or research-engine behavior merely for architectural neatness, local
  control, or speculative future flexibility. This rule does not prohibit the
  smallest necessary domain adapter, evidence-integrity check, or safety
  control, and it never authorizes copying or depending on code without a
  compatible license.
- Clearly distinguish a prototype or reference from integrated, tested,
  deployed, and operator-accepted product behavior. Preserve an
  owner-approved prototype as implementation input; do not discard it and
  independently greenfield the same experience without a documented reason.
- Decision 286 sets a temporary cost and sequencing boundary for the remaining
  selected-run Results beta. Preserve and integrate the approved chart/page
  behavior through exactly three bounded slices: reuse/integration, focused
  browser fixes, then backed-up validated OVH deployment. The remaining work
  has a six-development-hour planning ceiling, measured and reported honestly;
  this is a stop-control, not a promise or fabricated precision. Do not add a
  framework, chart/grid/panel system or architecture, or paid dependency, and
  do not replace the approved behavior. Caching, scalable multi-run design or
  Explorer work, aesthetic polish, and broad refactoring remain outside these
  slices unless evidence demonstrates that an item blocks the beta. Each slice
  has one bounded implementer and one independent reviewer while the lead
  orchestrates and validates. The reviewer checks only the owned diff, decisive
  evidence, and boundary compliance; review is not a second implementation,
  broad audit, discretionary redesign, or duplicate-test exercise. While beta
  work is active, report progress at least hourly with the current slice,
  selected reuse, boundary compliance, scope pressure, and next action. If thin
  integration expands, stop and reassess reuse rather than silently exceeding
  the ceiling or widening the slice. The dashboard remains the essential
  single-user interface, but this beta MVP need not be perfect.

## Accepted execution sequence

Decision 274 sets the current order. The milestone numbers remain unchanged;
the remaining Milestone 24 paper activation follows strategy qualification even
though its deployment and offline execution preparation is already retained.

1. Complete the remaining Milestone 23 dashboard gates, including implementation
   of the owner-approved chart-first Results specification, design of the
   required scalable multi-run analysis surface, evidence, and renewed owner
   acceptance of the implemented experience.
2. Conduct controlled equity strategy intake and research backtesting under
   Milestone 25 until a defensible edge qualifies.
3. Resume and complete the remaining Milestone 24 paper activation only after
   an edge qualifies and account, credential, endpoint, worker and execution
   acceptance gates pass.
4. Run automated Alpaca paper forward testing and reconciliation under
   Milestone 26 for qualified strategies.
5. Treat Alpaca micro-live testing under Milestone 27 as far-future work that
   requires successful paper evidence and separate explicit owner approval.
6. Evaluate a compliant crypto venue and multi-venue operation only after the
   equity path proves its operating value; WEEX remains the preferred first
   crypto execution proof, subject to legal, account, API, and operational
   eligibility verification.

Hyperliquid and MEXC are later evaluation targets. Futures, FX, listed options, and Interactive Brokers remain deferred backlog items. Networking, containers, VPNs, or proxies must not be used to bypass eligibility restrictions.

## Architecture

- Keep strategy, validation, evidence, and research logic venue-neutral.
- Venue-specific SDK objects belong only inside independently deployable execution adapters or workers.
- Quant Factory owns workflow, decisions, records, orchestration, evidence, review, reconciliation, and strategy lifecycle state.
- Research cannot submit venue orders directly.
- Plotly Dash is the application framework; VectorBT Pro remains the portfolio analytics and Plotly-compatible chart engine.
- ADR 0008 governs the dashboard: one persistent `dcc.Location`, one permanent
  application shell, permanently mounted route containers, pathname-driven
  visibility, page-owned callbacks, reusable components, and browser-lifecycle
  acceptance. Dynamic `page-content.children` routing is prohibited as the
  active routing mechanism.
- Production and execution services use portable containers with external persistent storage and external secrets.
- Paper and live deployments remain separate security domains.
- Micro-live operation requires an independent Risk Sentinel, authenticated private networking, cryptographic service identity, firewall allowlists, signed commands, and external audit evidence.
- AI agents may analyze, propose, review, alert, and perform explicitly bounded approved actions. They may not bypass risk limits, silently change parameters, enable live trading, or increase capital.
- Read accepted ADRs under `docs/architecture/` before architectural changes.
- CloddsBot is an extraction and reference source for exchange abstractions, risk controls, trade ledgers, monitoring, MCP patterns, and UI ideas. It is not the Quant Factory foundation.

## Agent allocation

- ChatGPT handles architecture, research, documentation, roadmap and milestone maintenance, decision logging, source-of-truth synchronization, GitHub inspection, remote documentation commits, and isolated changes it can safely verify directly.
- Claude Code is the primary programming agent for sustained local implementation, multi-file work, looping, subagent coordination, runtime debugging, VectorBT Pro integration, migrations, dashboard callbacks, test creation, and local Git validation.
- Codex is retired from ordinary project work except for the current owner-
  authorized revival scope recorded in DECISIONS and the agent policy. Claude
  Code remains the primary programming agent outside that scoped revival.
- Under ordinary routing, do not send documentation-only, planning, roadmap,
  source-of-truth, read-only inspection, diff, status, comparison, counting, or
  explanation work to Claude Code. While the lead is orchestrating, delegable
  work follows the orchestrator qualification below.
- The lead may use bounded read-only helpers and independent implementation workers when parallelism shortens the critical path. Follow the complete initial-prompt, ownership, escalation, and polling rules in `docs/ai-programming-agent-policy.md`; helpers do not inherit authority to expand scope.
- Agents must read repository instructions and accepted decisions rather than requiring the user to relay project history.

Under Decision 270, the current scoped revival uses multiple agents for all
task execution. The lead orchestrates, defines scope, independently validates
critical evidence, and remains available to the project owner; it does not implement
inline. Assign documentation, inventories, and mechanical edits to the cheapest
suitable worker, bounded implementation requiring judgment to a mid-tier
worker, and architecture, risk-bearing logic, or hard-to-reverse decisions to
the strongest suitable worker. Use parallel workers for independent work and
sequence dependencies. Workers report delegation or tool-limit blockers to
the lead; the lead records the limitation rather than silently taking over
implementation. Claude Code remains the primary application implementation
agent outside this revival; helpers do not receive project ownership.

CI is part of initial engineering setup; for this restart, establish and prove
the missing gate in the first authorized executable setup slice. Claim a gate
only after a required test check caused a blocked merge; CI is not target
environment proof. After environment-input changes, validate loading, startup,
and relevant behavior in the actual target environment. See the agent policy
for the controlled-failure procedure and evidence rules.

## Credential management

- OneCLI remains the selected first agent credential gateway under Decision 269, subject to ADR 0010 acceptance. Current work and ordering live in `docs/MILESTONES.md`.
- The Agent Vault fallback evaluation is superseded as current work. Do not replace OneCLI or resume that fallback without separate explicit owner instruction.
- Infisical and a custom Bitwarden SDK integration are deferred for the initial implementation.
- Personal password-manager vaults are unrelated to Quant Factory and must not be exposed to agents or treated as project dependencies.
- Agents never receive unrestricted vault access or underlying secret values.
- Preferred flow: restricted agent identity or placeholder → OneCLI policy and credential injection → approved outbound request, without exposing the secret to the agent.
- Decision 271 authorizes the one-shot operator-controlled Alpaca paper-account GET through existing OneCLI before general gateway proof or upgrade. It exposes no underlying keys and authorizes no orders, worker activation, account reuse, live access, or general gateway adoption. All other credential use retains ADR 0010 and account-ownership gates.
- Begin with harmless test credentials and then paper credentials only.
- Secrets must never appear in prompts, GitHub, committed `.env` files, Python source, Markdown, logs, UI, tests, process output, or generated artifacts.
- Paper and live credentials remain separate. Withdrawal permissions are prohibited.
- Credential use and denials must be auditable and fail closed.

## Milestone gate

- Work proceeds through the active milestone and the explicitly scoped parallel preparation in Decisions 259 and 262.
- Milestone 23 is the end-to-end equity research factory acceptance gate.
- Do not begin candidate discovery, optimization, protected-test evaluation, paper-order activation, or live work unless the active milestone explicitly authorizes it. Independent execution implementation and testing follow Decision 262.
- Infrastructure acceptance uses deterministic fixtures and known artifacts; it does not require a profitable strategy.
- `docs/MILESTONES.md` is authoritative for active scope, slices, status, and acceptance criteria.
- Before accepting or closing a milestone, synchronize `docs/MILESTONES.md`
  with `dashboard/project_status.py`.

## Equity fixtures and initial venue

- SPY remains the primary research benchmark and a possible listed-options instrument later.
- SCHX is the selected future broad-market whole-share paper and micro-live infrastructure fixture.
- SCHB, SCHG, and SCHA remain portability references.
- MSFT and AAPL remain historical and paper portability fixtures unless later approved for micro-live use.
- SPYM remains a completed Databento ingestion, deterministic execution, and dashboard evidence fixture; its evidence is not transferable.
- Alpaca Paper Trading is the first execution venue.
- Every instrument requires its own dataset identity, liquidity/spread evidence, corporate-action review, execution assumptions, validation, and promotion record.

## Documentation governance

- Repository documentation is durable project memory; conversational recall is not a substitute.
- Follow `docs/DOCUMENTATION_GOVERNANCE.md` for every accepted decision, roadmap change, milestone completion, architecture change, deployment decision, venue decision, or permanent workflow change.
- Classify discussions as idea, investigation, accepted decision, implemented decision, or superseded decision.
- Assess impact across `AGENTS.md`, `docs/MILESTONES.md`, `docs/DECISIONS.md`, ADRs, `docs/CHAT_HANDOFF.md`, `README.md`, and relevant runbooks/specifications.
- Search authoritative files for contradictory statements and correct them in the same change set.
- Do not create parallel roadmap, project-state, decision, or handoff documents.

## Dashboard product contract

Before strategy discovery resumes, a non-programming operator must be able to inspect health; launch approved fixture experiments; select instruments, strategies, and configurations; inspect data provenance and execution assumptions; observe run status; view equity, drawdown, benchmark, signals, and trades; review validation evidence; understand pass/fail reasons; compare runs; record decisions; reproduce prior runs; verify lineage; and operate without Python, CSV, JSON, or terminal output.

Authoritative requirements are in `docs/dashboard-product-requirements.md` and `docs/infrastructure-completion-inventory.md`.

For meaningful dashboard or user-experience changes:

- Agree trader-facing vocabulary and visual direction before implementation,
  using an approved mockup or concise page specification when appropriate.
- Keep developer, database, and implementation terms in clearly labelled
  technical drill-downs rather than primary operator language.
- Require manual browser acceptance for navigation, routing, page identity,
  selected states, and visual hierarchy.
- Test affected routing through the registered Dash callback or endpoint;
  helper-only tests are insufficient.
- Do not use hidden compatibility text, invisible markers, legacy aliases, or
  test-only presentation behavior to satisfy acceptance.
- Do not claim the ADR 0008 shell, routing, refresh, or browser lifecycle
  complete until its browser-lifecycle checklist passes.

## Market data and environment

- Read `docs/DATA_CATALOG.md` and inspect `data/manifests/` before acquiring or changing market data.
- Raw data lives outside GitHub under `QF_DATA_ROOT`; public examples use `/srv/quant-factory/data`.
- Resolve the actual root from untracked `config/data_locations.local.toml`.
- Verify file existence and SHA-256 against committed manifests.
- Preserve original archives and source files. Copy; do not move or delete.
- Every imported dataset requires a committed manifest and catalog entry.
- Use the Python 3.12 environment under `QF_REPO_ROOT`.
- Import VectorBT Pro as `import vectorbtpro as vbt`.
- Inspect current code, tests, authoritative documentation, relevant ADRs, and Git history before editing.
- Prefer reusable tested logic, maintained external components, deterministic tests, and clear failures.
- Check licensing before copying third-party code.

## Testing and completion

- Do not bypass, weaken, or skip relevant tests.
- Run focused tests first and the full suite only when required for milestone acceptance.
- Do not rerun expensive backtests unless relevant inputs changed.
- A milestone is complete only after required tests pass, the diff is reviewed, the commit is pushed, `origin/main` is synchronized, milestones and durable decisions are updated, and the documentation completion gate passes.
- Return concise reports using: Repository; Files changed; Validation; Documentation impact; Commit; Push; Warnings or deviations.
