# ADR 0009: Execution Venues and Programming-Agent Direction

- **Status:** Accepted
- **Date:** 2026-07-28
- **Superseded in part:** Decision 237 retires Codex from the fallback and
  review roles described below. Claude Code remains the primary programming
  agent.

## Context

Several architectural and workflow decisions were made across separate discussions and were not yet consolidated in the repository. The existing documentation still overemphasizes Hyperliquid and Codex, while the current direction is WEEX-first for crypto and Claude Code-first for implementation.

## Decisions

### 1. Venue-neutral core

Research, strategy, validation, evidence, risk policy, and lifecycle state remain broker- and exchange-neutral. Venue-specific behavior is isolated in execution adapters or workers.

### 2. Execution order

- **Alpaca is the first equities execution proof**, beginning with paper trading.
- **WEEX is the first crypto execution target**, subject to legal eligibility, API verification, paper/sandbox capability, and security review.
- Hyperliquid and MEXC remain later comparison or fallback candidates, not the first crypto implementation.
- Interactive Brokers remains deferred until the simpler execution paths are proven.

WEEX is preferred first because its agent-oriented tooling appears closer to turnkey integration and may reduce custom adapter and control-layer work. This preference does not override legal, jurisdictional, security, or operational eligibility checks.

### 3. Deterministic supervisor and bounded AI

Python services enforce hard execution, position, exposure, loss, stale-data, connectivity, and kill-switch rules. AI may analyze, explain, alert, recommend, and operate only through explicitly bounded tools. AI does not receive unrestricted authority to increase risk or bypass deterministic controls.

### 4. Research, paper, and live separation

Validated strategies progress through an explicit registry and promotion process. Research cannot submit orders directly. Paper and live environments use separate credentials, state, logs, permissions, deployments, and release gates.

### 5. Dashboard-first operator workflow

The dashboard remains the primary operator interface. Routine use must not require terminals, Python, raw JSON, CSV inspection, or direct log reading. Research evaluation and paper/live operation remain distinct workflows even when presented within one product.

### 6. Claude Code becomes the primary programming agent

Claude Code is the preferred local implementation agent because its multi-agent and looping workflows better match the project's need for sustained implementation, review, testing, and iterative correction. This supersedes the earlier assumption that Codex is the default local programming agent.

The original decision retained Codex as a bounded fallback and reviewer.
Decision 237 supersedes that portion: Codex is now retired from active project
work unless explicitly reauthorized.

Neither agent is trusted as a source of truth. Repository documentation, deterministic tests, diffs, and runtime evidence remain authoritative.

### 7. ChatGPT role

ChatGPT continues to handle architecture, research, decision reconciliation, acceptance criteria, documentation, GitHub inspection, review, and repository changes it can safely perform directly. Local implementation is delegated only when execution, dependencies, tests, or runtime access require it.

The 2026-09-02 owner addendum qualifies this allocation only while a lead is
actively orchestrating: all delegable implementation, including documentation
and mechanical work, must be routed to a suitable worker under the [current
agent policy](../ai-programming-agent-policy.md). This cross-reference does not
alter venue, security, or execution mechanisms in this ADR.

### 8. CloddsBot use

CloddsBot is an extraction and reference source, not the Quant Factory foundation. Evaluate it for exchange-adapter interfaces, risk controls and kill switches, trade-decision ledgers, monitoring and alerting, bounded MCP or agent tools, and operator-interface patterns. Do not import unrelated ecosystem scope without a separate approved need and license/security review.

### 9. Source of truth

GitHub Markdown, ADRs, tests, and committed specifications remain the durable project memory. Chat history, Claude memory, Codex context, Google Docs, and Obsidian may assist discussion but are not authoritative.

## Consequences

- Existing Hyperliquid-first or Codex-first wording is superseded where it conflicts with this ADR.
- The first crypto feasibility work should evaluate WEEX eligibility, official tooling, API coverage, sandbox or paper behavior, permissions, rate limits, WebSocket reliability, and credential isolation.
- Agent-facing trading tools must be narrow, auditable, permissioned, and subordinate to deterministic risk controls.
- CloddsBot extraction should produce an adopt/adapt/reference/reject map before any code is copied.
- Operational agent instructions and the concise decision log must be synchronized with this ADR during the next documentation-maintenance pass.
