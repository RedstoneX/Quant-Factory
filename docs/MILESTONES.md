# Quant Factory milestones

This is the sole authority for current goal, phase, queue, sequence, blockers,
and next action. Git history preserves completed milestone narratives.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable intraday trading edges. |
| Immediate objective | Owner walkthrough of the deployed R13 recovery and the truthful terminal R15 campaign state. |
| Phase | **R13 live-workflow recovery is active at the final owner-review gate. R15 reached its 12-Candidate terminal ceiling without an executable Candidate; the product remains unaccepted end to end.** |
| Active work | No further mutation is authorized before the owner walkthrough. Factory row hydration, stale-client revision handling, canonical Submit, deterministic admission, and campaign-state presentation are deployed on the review branch. |
| Technology | Reuse the accepted Dash/Mantine shell, existing projections, Plotly/VectorBT evidence, and Dash AG Grid. Keep `dashboard.ui` presentation-only, lazy-load heavy evidence, and preserve bounded server-side data paths. |
| Visual authority | Dashboard: `docs/assets/dashboard/current-visual-contract/dashboard.html`, SHA-256 `266336fb5d62caa844cae6c67d4ed36df63a14bc4de7ad72919375d9318e74c1`. Remaining workflow surfaces: `docs/assets/workspaces/current-workflow-contract/workspaces.html`, SHA-256 `313b098fa43ca0e25e6c92dad55b2d508faca94765c3cd8fe9c7005837f71b31`; it contains no Dashboard composition. |
| Visual proof state | The approved contracts remain the visual baseline. Fresh-browser proof shows Factory's persisted rows, 12 exact canonical Candidate admission outcomes, working Candidate search/sort/selection/detail, truthful retained Results, and unavailable Compare/Paper states. No genuine survivor or evidence-complete new run exists. |
| Next action | Terry performs the consolidated live walkthrough of the deployed review revision. A later executable campaign requires a new decision about implementing exact Candidate adapters; do not bind these hypotheses to nearby retained adapters or reopen R15. |
| Owner checkpoints | One consolidated live walkthrough now. Merge remains behind that walkthrough. R15 is terminal and grants no further Candidate or run authority. |
| Deferred | Broad or open-ended edge discovery; VectorBT Pro upgrade; new or paid/protected data; paper-lane activation; broker work; orders; live trading; and capital exposure. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R13 | 1 | in_progress | none | Recovery revision deployed: persisted Factory rows hydrate, obsolete callback clients fail visibly and reload, Submit uses the audited gateway, and canonical admission outcomes project into Candidates. Final acceptance remains Terry's unaided walkthrough. |
| R14 | 2 | blocked | R13 | Broad unattended Candidate research remains outside the completed product-validation campaign and requires a later owner decision. |
<!-- active-work:end -->

## Authorized R15 product-validation campaign

Terry authorizes this one campaign to create canonical Candidate and research
state after R13's submission and campaign-admission prerequisites pass. It is
for truthful end-to-end product validation, not a demand to discover an edge.

| Boundary | Fixed authority |
|---|---|
| Policy identity and expiry | `r15-product-validation-v1`; expires permanently when 12 accepted Candidates reach terminal admission/outcome state or four compute hours elapse after the first run starts, whichever occurs first. |
| Intake | At most 12 distinct, source-attributed QF Candidate v1 packets produced by an LLM or the owner. Duplicate and invalid packets do not consume execution budget. |
| Mandate | Same-session intraday directional research only; flat by the declared session boundary; no overnight or multi-day positions. |
| Instruments, sessions, and data | MES only, using the already verified `futures_MES_5m_databento` local dataset, its fixed 2019-05-06 through 2023-12-29 coverage, and the existing NYSE same-session calendar/boundary. No external acquisition, paid/protected data, or new credential use. |
| Families | Distinct explainable intraday archetypes compatible with existing registered MES adapters. Do not rerun, paraphrase, or tune the two prohibited MES proof Candidates. |
| Search | Reference-first, precommitted bounded values only; at most 100 parameter combinations per study and 1,200 across the campaign. No adaptive search, widening, post-result refinement, or arbitrary indicator assembly. |
| Studies and finalists | At most one initial study per accepted Candidate and at most three evidence finalists across the campaign. A refinement is not authorized. |
| Horizon and evidence | Each immutable study must precommit the existing accepted costs, chronological splits, objective, family-level multiplicity controls, and screening/OOS/walk-forward/robustness/Monte Carlo gates without weakening or substitution; a missing value fails admission closed. Stop before any protected-test boundary. |
| Repair and retry | At most two provenance-preserving semantic repair attempts per Candidate and one infrastructure retry per failed operation. Repair may not change the hypothesis. |
| Compute | One concurrent worker, four elapsed hours maximum, 2 GiB additional retained artifacts maximum, and zero incremental monetary spend. |
| Stop conditions | Stop admission at any campaign ceiling. Stop only the affected Candidate for unresolved meaning, missing local data or adapter, prior-work conflict, or deterministic failure. Stop the campaign for repeated infrastructure failure or any need for paid/protected data, new credentials, mandate expansion, paper/live/broker/order/capital authority, or larger budgets. |
| Success | Canonical submission, progression, truthful terminal outcomes, exact lineage, and evidence-complete live page behavior are proven. A qualified survivor is not required. |

Synthetic populations are not part of R15. The completed temporary large-row
proof remains capacity evidence only. If no real survivor appears, one clearly
labelled isolated noncanonical fixture may prove survivor-only presentation;
it cannot close canonical survivor or paper-handoff acceptance.

R15 reached its permanent terminal ceiling on 2026-10-12. Twelve distinct
LLM-authored, source-attributed QF Candidate v1 packets were persisted through
the authenticated gateway. Their fixed grids totalled 47 combinations. The
deterministic policy closed every Candidate as
`implementation_blocked / adapter_unavailable` because no exact registered MES
adapter and immutable StudyPlan compiler matched the submitted hypothesis.
No run, protected evidence, survivor, paper package, broker action, or capital
state was created. This is a valid campaign outcome, not authority to substitute
a nearby implementation or tune a closed proof Candidate.

## Retained technical evidence

- The generic Candidate runtime, bounded study inputs, screening,
  out-of-sample, walk-forward, robustness/regime, Monte Carlo, persistence,
  lineage, durable launch claims, Plotly charts, and Dash AG Grid data paths
  exist and are reusable.
- Intraday annualization corrections and the accepted lazy Results data path
  remain valid. Historical measured Results performance is technical evidence,
  not usability or visual acceptance.
- Canonical state now contains 12 R15 Candidate packets and the two retained
  older MES runs. All 12 R15 Candidates are terminal implementation blocks;
  there is still no survivor. The old successful run remains evidence-invalid
  and has no persisted OHLC bars or trades suitable for a meaningful new
  Results review.
- Recovery revision `46cc5ff6568d653229eaf1d2cb3aa4c565005a0f` is deployed
  for review. Its pre-mutation canonical and gateway databases were backed up
  recoverably before campaign submission.
- Results, Factory runs, Submit Strategies, Compare Selected, and the external
  Paper Trading destination were merged through PRs 198–202 and deployed, but
  route existence, isolated fixtures, and shallow controls did not establish a
  working product. The isolated comparison proof database was deleted.

## Current contracts

- Product behavior: `docs/factory-operating-contract.md`
- Runtime architecture: `docs/architecture/0016-dashboard-runtime.md`
- Frontend execution discipline: `.agents/skills/quant-factory-frontend/SKILL.md`
- Dashboard visual contract: `docs/assets/dashboard/current-visual-contract/dashboard.html`
- Remaining-workspace contract: `docs/assets/workspaces/current-workflow-contract/workspaces.html`

No supporting document creates another queue, visual target, or implementation
authority.

## Accepted Dashboard evidence

On 2026-10-09 Terry accepted the connected Dashboard's composition and basic
drawer interactions. That acceptance remains visual and surface-specific; it
does not prove the later seven-surface workflow or canonical campaign path.
