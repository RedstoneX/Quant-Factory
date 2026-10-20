# Quant Factory

Quant Factory turns trading ideas into backtests. An idea is a
`qf_candidate_v1` packet; if it carries a `qf_rules_v1` rule spec, Quant Factory
compiles it into a strategy and backtests it automatically. It does not trade.

## Flow

1. An idea is submitted through the research gateway (`qf-agent`) or the dashboard.
2. The packet is validated. `research_intake.starter_kit()` gives an example and a guide.
3. Ideas without rules are recorded as can't test yet.
4. Ideas with rules are backtested under the owner's standing policy of
   2026-10-13. Paper trading always needs separate owner approval.
   Every setting in the idea's grid is tested in chunks sized to fit memory for the data's bar count (2 settings on 1-minute bars, about 40 on 5-minute): a chunk builds its own
   signals, runs one simulation and keeps only scores and the account-value
   line the Luck test needs, so signals never pile up for the whole grid.
   Known limit [measured, QQQ 1-minute, 1.05M bars]: the simulation itself
   stays flat apart from the Luck test's account-value line (8.4 MB per
   setting); stacking those lines for the Luck test copies them once more, so
   a 100-setting 1-minute idea still needs more than 3 GB at that step.
5. Two gates decide: **Survives costs** (full history, Sharpe after costs
   >= 0.5) and **Unseen data** (the selected setting made money after all costs
   on the test years it never saw). Inside Unseen data no Sharpe minimum applies:
   the setting is chosen by the experiment's ranking among settings that made
   money after costs on the built-on years, or fails with "lost money on the
   years it was built on". Both slices' Sharpes are recorded as scores. Owner
   ruling, Rex, 2026-10-19: "relaxing is better. Paper trading will eliminate
   since we've gotten nothing so far, relaxing seems obvious." Holds over time,
   Stress test and Luck test are recorded scores, not gates.
   Inside Unseen data the pick keeps the plan's own ranking, and the trade-count
   and drawdown rules still apply; the ruling dropped only the Sharpe minimum.

## Data

MES 5-minute bars with trading costs, history ending 2026-02-13. Other markets
lack cost data and cannot be tested yet. No options data exists.

## Running tests

```bash
python -m pip install -r requirements-runtime.txt -r requirements-ci.txt -r requirements-dashboard.txt
python -m pytest tests/test_qf_research_context_v1.py
```

CI runs the full portable suite on every pull request.

## Deployment

Only merged `main` goes live. The server deploys it automatically and rolls
back on failure. Nobody deploys by hand.

## For AI agents

Read `AGENTS.md`. Research agents receive
`docs/AGENT_RESEARCH_OPERATING_CONTEXT.md` from the gateway at session start.

## Security

See `SECURITY.md`.
