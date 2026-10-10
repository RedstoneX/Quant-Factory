# Quant Factory milestones

This is the sole authority for current goal, phase, queue, sequence, blockers,
and next action. Git history preserves completed milestone narratives.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable intraday trading edges. |
| Immediate objective | Finish the remaining approved operator surfaces—Results, Factory runs, Submit Strategies, Compare Selected, and the external Paper Trading destination—and deploy the complete seven-surface product for one consolidated owner review. |
| Phase | **R13 continuous operator-suite completion. Dashboard and Candidates are accepted; Candidate research remains paused.** |
| Active work | Preserve accepted Dashboard and Candidates. Implement Results → Factory runs → Submit Strategies → Compare Selected → Paper Trading destination from the checksum-locked workspace contract without intermediate owner pauses. This continuous batch was explicitly authorized by Terry on 2026-10-09. |
| Technology | Reuse the accepted Dash/Mantine shell, existing projections, Plotly/VectorBT evidence, and Dash AG Grid. Keep `dashboard.ui` presentation-only, lazy-load heavy evidence, and preserve bounded server-side data paths. |
| Visual authority | Dashboard: `docs/assets/dashboard/current-visual-contract/dashboard.html`, SHA-256 `266336fb5d62caa844cae6c67d4ed36df63a14bc4de7ad72919375d9318e74c1`. Remaining workflow surfaces: `docs/assets/workspaces/current-workflow-contract/workspaces.html`, SHA-256 `313b098fa43ca0e25e6c92dad55b2d508faca94765c3cd8fe9c7005837f71b31`; it contains no Dashboard composition. |
| Visual proof state | **Dashboard and Candidates accepted.** Remaining surfaces use their exact workspace-contract regions and the accepted modern Dashboard visual language; representative values remain test-only. |
| Next action | Implement and publish Results, then continue through Factory runs, Submit Strategies, Compare Selected, and the Paper Trading destination. Do not create new mockups, redesign, or wait for intermediate owner approval. |
| Owner checkpoints | One consolidated owner walkthrough after all remaining named surfaces are working at the private application. Lean per-surface technical, control, and direct visual checks continue; they do not pause the batch. |
| Deferred | Candidate campaigns; VectorBT Pro upgrade; paid/protected data; paper activation; broker work; orders; live trading; and capital exposure. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R13 | 1 | in_progress | none | Dashboard and Candidates are accepted; continuous completion of Results, Factory, Submit, Compare, and Paper destination is authorized. |
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
- Dashboard visual contract: `docs/assets/dashboard/current-visual-contract/dashboard.html`
- Remaining-workspace contract: `docs/assets/workspaces/current-workflow-contract/workspaces.html`

No supporting document creates another queue, visual target, or implementation
authority.

## Accepted Dashboard evidence

On 2026-10-09 Terry used the connected Dashboard at the established private URL,
opened and dismissed multiple contextual drawers, and accepted the surface as
working. It runs as the persistent Linux service against the explicitly
configured external database. This closes Dashboard comprehension and unlocks
Candidates; it does not authorize another surface or research campaign.
