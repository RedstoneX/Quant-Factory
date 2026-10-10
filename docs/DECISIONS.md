# Quant Factory decisions

This file contains only decisions that still change current behavior. Full
historical decision prose remains recoverable in Git history and is not active
instruction material.

`docs/MILESTONES.md` alone controls current priority, sequence, status, and next
action.

## Current effective decisions

| Decision | Current effect |
|---:|---|
| **351** | **Seven-surface operator suite technically complete and privately deployed.** Dashboard and Candidates retain owner acceptance. Results, Factory runs, Submit Strategies, Compare Selected, and the external Paper Trading destination are merged, deployed, and passed bounded technical, control, and direct visual implementation proof; they await Terry's single consolidated unaided walkthrough. Live routes remain read-only and truthful, Compare remains secondary, and the Paper outbound action remains unavailable until an explicit private HTTPS destination exists. This product checkpoint does not activate Candidate research, paper trading, broker access, orders, live trading, or capital exposure. |
| **349** | **Approved remaining-workspace contract restored.** The owner-approved interactive structure for Candidates, Results, Factory runs, Submit Strategies, Compare Selected, and the external Paper Trading destination is repository-owned at `docs/assets/workspaces/current-workflow-contract/workspaces.html`, SHA-256 `313b098fa43ca0e25e6c92dad55b2d508faca94765c3cd8fe9c7005837f71b31`. Preserve its page regions, controls, drill-downs, and workflow; apply the accepted modern Dashboard visual language and production Mantine/Dash components. The older Dashboard composition was physically removed. Later pages are translations of this accepted contract, not greenfield redesigns. |
| **348** | **Dashboard and Candidates accepted.** Preserve both accepted production surfaces. Dashboard remains the oversight front door; Candidates remains the high-density gold-discovery workspace with Compare Selected secondary. Decision 350 controls completion of the remaining surfaces. |
| **347** | **Connected private Dashboard is the owner-review gate.** Gate A appearance is accepted. The current slice must bind the approved shell read-only to the explicitly configured external canonical runtime database and run persistently at the established tailnet URL. A screenshot, temporary process, unavailable default database, audit, or test report is not the deliverable. The clean source checkout and external runtime state are separate boundaries; rejected UI code is prohibited, but canonical state stored outside the clean checkout remains required input. Owner walkthrough occurs before secondary audits and merge. |
| **346** | **Modern Dashboard visual reset.** The sole Dashboard authority is `docs/assets/dashboard/current-visual-contract/dashboard.html`, SHA-256 `266336fb5d62caa844cae6c67d4ed36df63a14bc4de7ad72919375d9318e74c1`, promoted unchanged from the owner-approved modern Mantine/toolset preview. Older Dashboard compositions and both rejected Dashboard implementations are prohibited inputs. This decision governs Dashboard only; Decision 349 governs the other six surfaces. |
| **345** | **Dashboard runtime separation.** Implement and review Dashboard directly, outside Docker. Prefect and the agent gateway remain containerized Quant Factory infrastructure. After separate deployment approval, Dashboard defaults to a normal Linux service. Dashboard unavailability must not stop the filtration pipeline. Alpaca paper trading remains a separate system with stronger uptime, monitoring, reconciliation, and recovery controls. |
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
  0016; visual behavior is defined only by the two non-overlapping,
  checksum-locked HTML contracts.
