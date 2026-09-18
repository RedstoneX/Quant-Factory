# Quant Factory Decisions

This clean-history log preserves the accepted decision set needed to operate
the public project. Detailed private operational history remains in the
private archive. New decisions are appended and supersede earlier decisions
explicitly.

## Foundation and product direction

1. The canonical public Quant Factory repository becomes the sole forward
   source of truth after Decision 275's controlled cutover. Until then, the
   existing private repository remains canonical and the temporary public
   candidate is validation-only. Repository documentation is durable project
   memory.
2. The closed Tier 1 authority set is `AGENTS.md`, `docs/MILESTONES.md`, and
   `docs/DECISIONS.md`. Supporting documents cannot create competing mandate,
   status, or roadmap authority.
3. Quant Factory is infrastructure first, evidence first, dashboard first, and
   operating-proof first. Plotly Dash is the operator interface and VectorBT
   Pro is the licensed research engine.
4. Research, validation, evidence, and strategy logic remain venue-neutral.
   Research cannot submit venue orders directly.
5. Deterministic fixtures prove infrastructure; their results are not
   profitability evidence or deployment approval.

## Research and evidence

6. Data provenance, adjustment policy, validation status, identity, and
   checksums are required. Downloaded market data and generated results remain
   outside Git.
7. Hypotheses and parameter ranges require attribution and explicit approval.
   Reference reproduction precedes bounded exploration; protected data cannot
   participate in selection.
8. Screening, chronological out-of-sample, walk-forward, robustness, and
   Monte Carlo evidence retain distinct pass, fail, invalid, and insufficient-
   evidence outcomes.
9. Evidence decisions never execute protected tests, promote a strategy, or
   authorize deployment automatically.

## Dashboard architecture

10. ADR 0008 is the accepted dashboard baseline: one persistent
    `dcc.Location`, one permanent shell, permanently mounted route containers,
    pathname-driven visibility, page-owned callbacks, reusable components,
    and mandatory browser-lifecycle acceptance.
11. Dynamic `page-content.children` replacement is prohibited as the active
    routing mechanism. Hidden compatibility content and test-only presentation
    behavior are prohibited.
12. Operator language and decision-useful visuals are primary. Technical IDs,
    hashes, storage details, and diagnostics belong in labelled drill-downs.
13. The target flow is Home → Ideas → Set up → Run test → Results → Compare.
    During Milestone 23, Ideas is non-executing and may capture safe drafts or
    source references only. External retrieval and backtesting remain gated.

## Execution and security

14. Alpaca Paper Trading is the first execution venue. SCHX is the broad-
    market whole-share execution fixture; SPYM remains an ingestion and
    deterministic research fixture.
15. Paper and live deployments are separate security domains. A configuration
    change cannot convert paper execution into live execution.
16. Real-capital activation requires successful paper evidence, explicit human
    approval, isolated credentials and state, authenticated private networking,
    deterministic risk controls, and an independent Risk Sentinel.
17. OneCLI is the selected first credential gateway, subject to ADR 0010.
    Agents never receive unrestricted vault access or underlying secret values.
    Paper and live credentials remain separate; withdrawal permission is
    prohibited.
18. The broker-neutral journal records a durable submission claim before a
    broker call. Ambiguous submissions are never retried automatically;
    reconciliation and restart behavior fail closed.

## Repository and agent operation

19. Substantive work uses dedicated branches and pull requests. Direct pushes
    to `main`, force pushes, blanket staging, destructive Git, and anonymous
    stashes are prohibited.
20. CI execution and target-environment proof are separate. Required-check
    enforcement is proven only when a controlled failing check blocks merging
    and the restored green path passes.
21. Independent pull requests use required status checks with GitHub's strict/
    up-to-date option disabled under Decision 276. They do not refresh or
    serialize merely because an independent pull request merged first.
    Overlapping or dependent changes remain serialized and retested against
    the resulting `main`.
22. During the scoped revival, the lead orchestrates multiple bounded workers,
    independently validates critical evidence, and remains the sole owner-
    facing coordinator. Outside that scope, Claude Code remains the primary
    sustained implementation agent.

## Current accepted sequence

256. **Scoped revival authority.** The project owner authorized the current
     bounded revival, including root-cause repair, extensive testing, and
     reviewed repository operations. This did not accept Milestone 23,
     authorize discovery or orders, or permit live capital.

259. **Parallel research deployment preparation.** Portable research-only
     packaging, migration preparation, and isolated target validation may
     proceed while Milestone 23 owner review is pending. This does not complete
     Milestone 24 or authorize execution.

262. **Parallel execution preparation.** Broker-neutral contracts, isolated
     paper-adapter implementation, offline tests, and target validation may
     proceed without paper-order activation. Credential use remains subject to
     ADR 0010 and the account-ownership boundary.

266. **Authoritative research runtime.** Research runtime migration is
     authorized only after backup, reconciliation, authenticated private
     access, restart, restore, and rollback checks. Production coordinates and
     evidence remain external to the public repository.

269. **Credential gateway selection.** OneCLI remains selected; replacement or
     resumed fallback evaluation requires separate explicit owner instruction.

270. **Revival orchestration.** All task execution in the scoped revival uses
     bounded workers matched to complexity. The lead orchestrates and
     independently validates critical evidence.

271. **One-shot authentication exception.** A fixed operator-controlled paper
     account GET may verify authentication through the gateway without
     exposing keys. It authorizes no orders, worker activation, account reuse,
     live access, or general gateway adoption.

272. **Dedicated paper-account boundary.** A dedicated simulated account is
     reserved for Quant Factory. Its identity and credentials remain private;
     this allocation does not authorize paper orders.

273. **Milestone 23C direction.** Retain Plotly Dash and VectorBT Pro, use Dash
     AG Grid and Dash Bootstrap Components where appropriate, show persistent
     run status/evidence/decision/next action, keep technical detail in labelled
     drill-downs, and obtain page-spec and browser/operator acceptance.

274. **Dashboard-first strategy qualification (accepted 2026-09-17).** Finish
     Milestone 23 dashboard and operator acceptance first. Then conduct
     controlled strategy intake and research under Milestone 25 until a
     defensible edge qualifies. Resume paper activation only after the edge and
     every account, credential, endpoint, worker, reconciliation, and safety
     gate pass. Automated paper evidence follows under Milestone 26. Micro-live
     work is far future and requires separate explicit owner approval.

275. **Clean-history public repository migration (accepted 2026-09-18).** The
     project will use a sanitized clean-history public repository at the
     canonical name after controlled cutover. Until then, the public candidate
     retains its temporary name and the original private repository remains
     canonical. At cutover, the original is retained privately as a read-only
     archive and is not rewritten or deleted. The public repository contains
     no credentials, private infrastructure, machine-specific state, licensed
     packages, downloaded data, generated results, or private operational
     evidence. Publication grants no source-code license; all rights are
     reserved. This decision remediates repository enforcement only and does
     not authorize strategy discovery, paper activation, live capital, or a
     production deployment.

276. **Parallel pull-request throughput policy (accepted and implemented on
     the temporary public candidate 2026-09-18).** The owner permanently sets
     `required_status_checks.strict` to `false` unless the owner later changes
     this decision. Required checks remain `Documentation contracts`,
     `Portable tests`, and `Dependency review`; `enforce_admins` remains true;
     repository auto-merge and merged-branch deletion remain enabled; CI
     concurrency remains per ref; and no merge queue is used. Independent
     green pull requests may merge without rebasing, updating, rebuilding, or
     serializing merely because another independent pull request merged first.
     Overlapping or dependent changes still integrate serially and are retested
     against the resulting `main`. GitHub API verification on 2026-09-18
     confirmed these settings on the temporary public candidate. Controlled PR
     #1 proved enforcement: its first revision failed `Portable tests` and was
     blocked, its corrected revision passed all three required checks, and the
     PR was closed without merging. These settings must survive the controlled
     canonical cutover required by Decision 275.
