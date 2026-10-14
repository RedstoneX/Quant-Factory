# Rules for AI agents working on Quant Factory

This is the only agent-rules file. If any other text in the repository
disagrees with it, this file and the code win. Judge behaviour from the code.

## What Quant Factory does

It takes trading ideas, turns those with machine-readable rules into
strategies, and backtests them. It does not trade.

## How ideas arrive and get tested

- Ideas arrive as `qf_candidate_v1` JSON or YAML packets, through the research
  gateway (`agent_gateway/`, client `qf-agent`) or the dashboard.
- A testable idea carries a `rule_spec` written in `qf_rules_v1`
  (`rule_language/`). `research_intake.starter_kit()` returns a worked example
  and a field-by-field guide.
- An idea without rules is recorded as can't test yet
  (`implementation_blocked` / `rules_missing`).
- Every valid idea is auto-tested: backtesting only, with approval stamped
  automatically under the owner's standing policy of 2026-10-13
  (`strategies/rule_spec_strategy.py`).
- Paper trading always needs separate owner approval. Nothing in this repo may
  activate paper or live trading on its own.

## Data

- Testable today: MES 5-minute bars with trading costs; history ends 2026-02-13.
- Other markets have manifests in `data/manifests/` but no cost data, so they
  cannot be tested honestly yet. No options data exists.
- Downloaded market data lives outside the repo. Never modify or delete it.

## How code goes live

- Only merged `main` goes live. The server deploys it automatically and rolls
  back on failure (`deployment/release/qf_deploy.py`). Nobody deploys by hand.
- Changes reach `main` through a pull request whose required checks pass.

## Hard rules for agents

- Never use `sudo` or `docker`.
- Never read, print, copy or commit credentials, tokens, keys or secrets.
- Never permanently delete data; move it to the trash instead.
- Stage explicit paths. Never `git add -A`, `git add .` or a bare `git stash`.
- When a file is at the structural size limit, put new tests in a new file.
- Run only the tests you touch; the full suite runs in CI.

## Where things are

- `research_intake/` packet parsing, validation, starter kit, research context.
- `rule_language/` the `qf_rules_v1` rule language and its limits.
- `strategies/` strategy code, including the rule-spec strategy.
- `backtesting/`, `orchestration/` screening and the test pipeline.
- `agent_gateway/` the research gateway; `dashboard/` the owner's web UI.
- `docs/AGENT_RESEARCH_OPERATING_CONTEXT.md` the text served to research agents.
