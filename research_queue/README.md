# qr-queue: research packet queue

Branch-only (no PRs). Claude pushes packets; the box runner (Grok, grok-box-1) tests them.

- `pending/<id>.json`: a `qf_candidate_v1` packet with a `rule_spec` in `qf_rules_v1`.
  `<id>` = lowercase letters, digits, `-` (e.g. `2026-10-27-spy-vwap-fade`). Put a
  short hypothesis in `hypothesis.behavior` and the source in `sources[0]` (a source note).
- The box runner (every 15 min, max N per cycle) runs: prior search, validate,
  `tools.local_run` full pipeline (full costs, screen, unseen 60/20/20, walk-forward,
  stress/stable region, Monte Carlo) and writes `results/<id>.md` + `results/<id>.json`.
  The packet moves to `done/` (reached the end: survivor) or `rejected/` (stopped; see `failed_stage`).
- Look-ahead guard: all queue runs only see data up to the locked holdout cut-off
  (see `results/*.json` field `data_cutoff`). Holdout-period metrics are never written
  to this branch; Grok runs the holdout check privately on finalists only.
- Do not edit `done/`, `rejected/` or `results/` by hand. Do not commit secrets.
