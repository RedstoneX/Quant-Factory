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
- Rule specs (`qf_rules_v1`) accept `"bar": "1m"` (390 bars/session) or `"5m"` (78); the
  spec's bar must match the data's bar size, nothing is resampled.
- Other markets have manifests in `data/manifests/` but no cost data, so they
  cannot be tested honestly yet. No options data exists.
- US stock/ETF library: Alpaca SIP 1-minute bars, 45 symbols in labelled
  groups in `market_data/alpaca_sip_universe.py` (picked for tight spread,
  high volume and whole-share price), from 2016 (or listing date),
  split-adjusted, with pre/post-market bars labelled by a `session` column.
  Backtests load it by dataset id (`verified_local_catalog:<dataset_id>`,
  `adjusted=True`) and get the regular session. The list was picked in Oct 2026
  by recent liquidity, so results carry survivorship bias. No cost data yet.
- It is topped up nightly at 02:00 UTC by the `market-data-topup` compose
  service (`python -m market_data.alpaca_sip_cli --all --daily-at 02:00`); a
  manual run drops `--daily-at`. Its manifests live in the data mount
  (`downloaded_manifests`, default `<data root>/manifests`), and the catalog
  reads both that folder and the repo manifests. Resolve its files by dataset
  id, never by path: each top-up commits a new data slot via its manifest.
- Suspect bars (bad prints, one-bar spikes) are flagged by the published highfrequency
  `rmOutliersTrades` advanced rule (`market_data/bar_outliers.py`): the loader drops them
  and says how many in the audit; stored files are never edited; manifests list a count.
- Tickers get reused (Alpaca keys bars by symbol): the top-up keeps only bars after the last
  gap of more than 10 NYSE sessions and records the cut in the manifest (`history_cut`).
- Downloaded market data lives outside the repo. Never modify or delete it;
  only that top-up service writes there.

## How code goes live

- Only merged `main` goes live. The server deploys it automatically and rolls
  back on failure (`deployment/release/qf_deploy.py`). Nobody deploys by hand.
- Changes reach `main` through a pull request whose required checks pass.

## Hard rules for agents

- **No greenfield code. No hand-written code.** Use the proven, tested library that
  already does the job (VectorBT PRO first, then pandas or another published package).
  Never write your own version of something a library provides, and never build new
  architecture. The only exception is express permission from the owner (the account
  holder) for that specific piece. Before writing non-trivial code, name the library
  function that does it; if none exists, stop and report instead of writing it.
  (Owner ruling, 2026-10-14.)
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
