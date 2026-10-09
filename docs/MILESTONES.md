# Quant Factory milestones

This is the sole authority for current goal, phase, queue, sequence, blockers,
and next action. Git history preserves completed milestone narratives.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable intraday trading edges. |
| Immediate objective | Design and implement Candidates as the high-density gold-discovery workspace, then put that exact surface at the existing private review URL for owner walkthrough. |
| Phase | **R13 Candidates surface. Dashboard walkthrough accepted on 2026-10-09. Candidate research remains paused.** |
| Active work | Preserve the accepted Dashboard unchanged. Establish one Candidates visual contract in the same modern visual system, then implement its sortable/filterable AG Grid and exact selection behavior without starting Results. |
| Technology | Reuse the accepted Dash/Mantine shell. Candidates uses Dash AG Grid for server-side ranking, sorting, filtering, pinned columns, saved views, and bounded loading. `dashboard.ui` remains presentation-only. |
| Visual authority | Only `docs/assets/dashboard/current-visual-contract/dashboard.html`, SHA-256 `266336fb5d62caa844cae6c67d4ed36df63a14bc4de7ad72919375d9318e74c1`. |
| Visual proof state | **Gate A passed on 2026-10-09.** Representative values are retired from implementation evidence and may remain only inside the checksum-locked reference. |
| Next action | Produce the Candidates visual contract and real Mantine/AG Grid surface as the next bounded slice. Show the owner-visible Candidates result before starting Results or another page. |
| Owner checkpoints | Dashboard is accepted. Candidates requires its own owner-visible design and working private-route acceptance; internal checks cannot substitute for the walkthrough. |
| Deferred | Results, Factory runs, Submit Strategies, Compare Selected, and Paper destination UI until Candidates acceptance; Candidate campaigns; VectorBT Pro upgrade; paid/protected data; paper activation; broker work; orders; live trading; capital exposure. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R13 | 1 | in_progress | none | Dashboard is accepted; Candidates is the next owner-visible product surface. |
| R15 | 2 | blocked | R13 | Automated bounded-research activation requires a separately approved campaign policy after usable product handoff. |
| R14 | 3 | blocked | none | Provider-neutral Agent Research Gateway is retained but is not current substitute work. |
<!-- active-work:end -->

## Retained technical evidence

- The generic Candidate runtime, bounded study inputs, screening,
  out-of-sample, walk-forward, robustness/regime, Monte Carlo, persistence,
  lineage, durable launch claims, Plotly charts, and Dash AG Grid data paths
  exist and are reusable.
- Intraday annualization corrections and the accepted lazy Results data path
  remain valid. Historical measured Results performance is technical evidence,
  not usability or visual acceptance.
- No persisted survivor was present in the last recorded deployed inspection.
  Survivor behavior remains unproved until a real survivor exists.

## Current contracts

- Product behavior: `docs/factory-operating-contract.md`
- Runtime architecture: `docs/architecture/0016-dashboard-runtime.md`
- Frontend execution discipline: `.agents/skills/quant-factory-frontend/SKILL.md`
- Visual contract: `docs/assets/dashboard/current-visual-contract/dashboard.html`

No supporting document creates another queue, visual target, or implementation
authority.

## Accepted Dashboard evidence

On 2026-10-09 Terry used the connected Dashboard at the established private URL,
opened and dismissed multiple contextual drawers, and accepted the surface as
working. It runs as the persistent Linux service against the explicitly
configured external database. This closes Dashboard comprehension and unlocks
Candidates; it does not authorize another surface or research campaign.
