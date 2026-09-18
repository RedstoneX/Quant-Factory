# Quant Factory Claude Instructions

This file contains always-on, project-specific constraints for Claude Code.
Repeatable procedures belong in `.claude/skills/`; specialist workers belong in
`.claude/agents/`; external access belongs in MCP connectors.

## Authority

- Follow `AGENTS.md` as the primary authority for repository rules, allocation,
  safety, testing, and completion.
- Follow `docs/ai-programming-agent-policy.md` for Claude Code's accepted role
  and boundaries.
- Follow `docs/DOCUMENTATION_GOVERNANCE.md` for every durable decision,
  roadmap, architecture, workflow, or milestone change.
- The closed Tier 1 set is AGENTS, MILESTONES, and DECISIONS. Derive product intent, current scope/status, and active work from MILESTONES; owner decisions from DECISIONS; mechanisms from accepted ADRs. CHAT_HANDOFF is navigation only.
- Repository authorities and Git history override chat summaries, external
  notes, recovery snapshots, and connector output when they conflict.
- Do not create a competing roadmap, status file, decision log, handoff, or
  source of project truth.

## Repository and Git safety

- Resolve the active repository from `QF_REPO_ROOT`; public examples use
  `/srv/quant-factory/repo`. Isolated worktrees require explicit ownership.
- During Decision 275's migration, treat the existing private
  `RedstoneX/Quant-Factory` as authoritative for committed state until the
  controlled cutover. The public repository under the temporary candidate
  name is validation-only; after cutover it assumes the canonical name and
  becomes authoritative.
- Use `main` as the integration baseline and a dedicated branch/PR for substantive changes. Do not push directly to main. Follow AGENTS for explicit staging, stash identity, concurrent writers, and rollback.
- Follow Decision 276's permanent throughput policy: required checks and admin
  enforcement stay on, `strict`/up-to-date stays off unless the owner changes
  it, independent green PRs do not rebase, update, rebuild, or serialize merely
  because another independent PR merged, CI concurrency stays per ref, and no
  merge queue is used. Dependent or overlapping work still integrates
  serially and is retested against the resulting `main`.
- Preserve unrelated and uncommitted work.
- Never force-push. Other destructive Git commands require explicit instruction.
- Do not commit or push until the diff and required validation are reviewed.
- Never commit secrets, credentials, environment files, downloaded market data,
  generated results, local databases, or machine-specific artifacts.

## Revival understanding and working discipline

- The project owner confirmed the authority mapping and scoped full-authority revival on
  2026-09-02; see Decision 256. Do not repeat that request within this scope.
- Apply AGENTS' verification, scope attribution, factual-documentation correction, concise communication, and owner-feedback capture rules.
- Temporary helpers follow the agent policy: complete initial prompts, model fit, separate writing directories, no descendants or direct owner escalation, lead verification, and explicit polling budgets. Do not rely on conversation inheritance.

Under Decision 270, all task execution in this scoped revival uses multiple
agents matched to complexity. The lead orchestrates, validates critical
evidence, and stays available to the project owner; it does not implement inline. Follow
the ownership, polling, and CI proof rules in the agent policy. Workers report
delegation or tool-limit blockers to the lead, who records the limitation. Claude Code remains the primary application implementation
agent; a documentation helper does not receive project ownership.

## Product and scope boundaries

- Quant Factory is infrastructure-first, evidence-first, dashboard-first, and
  operating-proof-first.
- Plotly Dash is the normal operator interface. Python, terminal output, raw
  CSV/JSON, SQLite, and backend logs are implementation details.
- Do not begin strategy discovery, optimization, protected-test evaluation,
  paper-order activation, or live work unless the active milestone and explicit user
  approval authorize it.
- Decisions 259 and 262 permit research-only packaging, deployment preparation,
  broker-neutral contracts, isolated paper-adapter implementation, tests, and
  target validation in parallel with Milestone 23. Harmless or paper
  credentials require ADR 0010 credential-isolation proof and the documented
  account-ownership boundary, except for Decision 271's one-shot operator check. Decision 266 separately authorizes authoritative
  OVH research-runtime migration after backup, reconciliation, private-access,
  restart, restore, and rollback checks. It does not authorize paper-order
  activation, discovery, protected tests, optimization, live capital, or
  Milestone 24 completion.
- Private dashboard availability requires owner authorization, authenticated
  private networking, and target-environment proof. Provider-specific private
  coordinates remain outside the public repository.
- Use deterministic fixtures for infrastructure acceptance. Fixture results are
  not profitability evidence or deployment authorization.
- Keep strategy, validation, evidence, and research logic venue-neutral.
  Research must never submit venue orders directly.
- Alpaca Paper Trading remains the first execution venue. WEEX is the preferred
  first crypto proof only after its legal, account, API, security, paper or
  sandbox, and operational eligibility checks pass.
- Production and execution services use portable containers with external
  persistent storage and external secrets. Paper and live remain separate
  security domains, and micro-live requires an independent Risk Sentinel.

## Data, credentials, and implementation

- Before market-data work, read `docs/DATA_CATALOG.md`, inspect
  `data/manifests/`, resolve the configured external data root, and verify file
  identity and SHA-256.
- OneCLI remains the selected first agent credential gateway subject to ADR
  0010's proof-of-concept acceptance. Decision 271 separately authorizes the
  one-shot operator-controlled paper-account GET before general proof or
  upgrade, with no key exposure, orders, worker activation, account reuse,
  live access, or general gateway adoption. Current work is in MILESTONES.
  The Agent Vault fallback pursuit in Decision 268 is superseded by Decision 269; do not replace OneCLI
  or resume that evaluation without separate explicit owner instruction.
  Personal password-manager vaults are unrelated to Quant Factory and must not
  be exposed to agents.
- Use the Python 3.12 environment under `QF_REPO_ROOT`. Do not recreate it as
  `root`.
- Import VectorBT Pro as `import vectorbtpro as vbt`, never `import vectorbt`.
- Verify uncertain VectorBT Pro behavior through installed-package inspection or
  the registered MCP server.
- Read relevant accepted ADRs before changing architecture.
- Preserve behavior outside the approved bounded slice.
- Add deterministic tests, fail clearly, and never weaken tests or acceptance
  criteria to obtain a pass.
- Preserve protected-data boundaries, immutable configurations, lineage,
  checksums, evidence decisions, and fail-closed validation.

## Claude project structure

- Run the `implementation-preflight` skill before executable implementation and
  whenever the milestone, branch, worktree, or task scope changes materially.
- The owner-supplied handoff authorizes this scoped revival, including
  root-cause repair, extensive testing, and reviewed push/merge work. Decision
  270 requires worker execution with lead orchestration and validation;
  temporary workers remain bounded by the agent policy. Creating persistent
  `.claude/agents/` scaffolding still requires explicit authorization.
- Obsidian is a future human-facing AI memory layer, not source-code storage and
  not a replacement for GitHub.
- External recovery checkpoints do not override committed repository state.
