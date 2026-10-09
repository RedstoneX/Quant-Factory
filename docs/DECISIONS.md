# Quant Factory decisions

This file contains only decisions that still change current behavior. Full
historical decision prose remains recoverable in Git history and is not active
instruction material.

`docs/MILESTONES.md` alone controls current priority, sequence, status, and next
action.

## Current effective decisions

| Decision | Current effect |
|---:|---|
| **344** | **Single visual authority and clean implementation.** The sole visual contract is `docs/assets/dashboard/current-visual-contract/quant-factory-reconciled-mockups.html` with SHA-256 `d87f311127c513cefb50e75472a49aeb27d3031ac76c84e26a9940b73b23264a`. Dashboard is the first and only initial slice. Mantine is the default UI layer with Dash Core Components, Plotly, VectorBT Pro, and Dash AG Grid. Local actual/reference comparison, secondary interface audit, and independent adversarial review precede owner visual approval; only separately authorized private hands-on use closes comprehension. |
| **341** | **Separate Alpaca paper system.** QAMC remains a separate project whose code may be adapted but whose runtime, database, credentials, and availability are never Quant Factory dependencies. Quant Factory may create an immutable handoff package only inside a separately activated paper lane. It shows handoff status and one external destination link, not paper P&L or broker controls. |
| **339** | **Automated high-throughput filtration.** Owner- and LLM-authored QF Candidate packets share one provider-neutral intake. In-policy work progresses automatically through deterministic validation, bounded repair, prior-work checks, immutable study construction, VectorBT screening, OOS, walk-forward, robustness, and Monte Carlo within preauthorized budgets. Ordinary failures close automatically. Only genuine semantic, authority, cost/data, protected, paper/live, broker, or capital exceptions require the owner. This does not activate research. |
| **335** | **Retain VectorBT-native research and performance evidence.** Existing annualization and Results-latency corrections remain valid technical evidence. VectorBT Pro v2026.10.5 remains a separate, deferred compatibility change and is not part of Dashboard implementation. The two fixed MES proof Candidates remain screened out and may not be tuned or rerun. |
| **326** | **Exact identity and lineage.** Candidate, version, StudyPlan, run, artifact, evidence, chart, trade, and paper-package identities remain exact across every surface. Fixtures or nearby records never substitute for a missing identity. |
| **325** | **No broad browser automation.** Browser CI and broad multi-page/device suites are prohibited. Owner-authorized frontend work may use one bounded local read-only capture for the exact surface/state under repair. Terry performs hands-on browser acceptance. |
| **319** | **One-way component architecture.** Preserve existing backend/service ownership, persistence, evidence, orchestration, and dependency boundaries. Dashboard implementation does not authorize a research-logic rewrite or reverse dependency. |
| **314** | **Direct, economical working mode.** Use outcome → reuse → smallest implementation → decisive proof → deliver → stop. Independent frontend review is required only at the defined visual gate or when Terry explicitly requests it. |
| **313** | **Product before research.** Complete and hand off the usable single-owner product before starting another Candidate campaign. |
| **312** | **Credential authority.** Bitwarden Secrets Manager through the scoped `Codex` machine account and `Quant Factory` project is the unattended credential source of truth. Frontend work does not expand credential authority. |
| **309** | **Intraday mission.** Active edge discovery is same-session day trading with minutes-to-hours holds and no overnight or multi-day carry. |
| **285** | **Adopt before building.** Prefer maintained, legally compatible project dependencies and licensed capabilities over custom commodity components. |

## Stable authority boundaries

- Research, protected-data inspection, paper/live activation, broker access,
  orders, and capital exposure require their own explicit authority.
- A successful run is not a surviving edge. A survivor is not paper or live
  approval.
- No fabricated chart, trade, Candidate, run, survivor, metric, or fixture is
  presented as operational truth.
- Current product behavior is defined by
  `docs/factory-operating-contract.md`; runtime architecture is defined by ADR
  0016; visual behavior is defined only by the checksum-locked HTML contract.
