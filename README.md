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
