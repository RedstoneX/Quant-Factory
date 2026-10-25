# harvest-playbook-vwap-bands: rejected

- Title: QQQ VWAP deviation reversion [ideas:harvest-playbook-vwap-bands]
- Hypothesis: Ideas thesis: Fade touches of ±1–2σ VWAP bands back toward VWAP in mean-revert mode, or break-and-hold beyond ±2σ in trend mode; flatten at VWAP or opposite band. | Pilot behavior: Institutional VWAP execution may pull stretched prices back toward VWAP.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_9fffc912b5f24ede937e1ac81a7562a0; tested 2026-10-25T10:43:22-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 6 / 0
- Best screen setting: {'parameters': {'dev_frac': 0.005, 'hold_bars': 30}, 'sharpe_ratio': -0.8175, 'total_return': -0.3606, 'annualized_return': -0.0604, 'max_drawdown': -0.4006, 'number_of_trades': 3374.0, 'win_rate': 0.471}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'SPY VWAP mean-reversion (ATR bands), TP toward VWAP', 5), ('candidate', 'QQQ VWAP deviation reversion', 5), ('candidate', 'MNQ VWAP pullback continuation (5m)', 4)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.3215476798210616. | annualized_return failed: expected > 0.0 (exclusive); observed -0.0525789646709689. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.9308397813407793.
