# harvest-classic-inside-day-break: rejected

- Title: QQQ inside-bar breakout [ideas:harvest-classic-inside-day-break]
- Hypothesis: Ideas thesis: Day T is inside day (high < prior high and low > prior low). Day T+1: buy stop above inside high, sell stop below inside low; cancel unfilled EOD; stop at opposite side. Classic short-term pattern. | Pilot behavior: A bar inside the prior bar marks compression that may resolve directionally.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_3e8b64180cf24918ba4b58a51bc68aba; tested 2026-10-25T14:02:04-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 6 / 0
- Best screen setting: {'parameters': {'hold_bars': 20, 'stop_pct': 0.2}, 'sharpe_ratio': -0.9328, 'total_return': -0.3492, 'annualized_return': -0.058, 'max_drawdown': -0.3975, 'number_of_trades': 7154.0, 'win_rate': 0.4403}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'MES Keltner channel breakout [ideas:harvest-classic-keltner-chesler]', 7), ('candidate', 'QQQ Bollinger band mean reversion [ideas:harvest-classic-bb-pctb-mr]', 7), ('candidate', 'MES NR4/NR7 narrow-range bar breakout (Crabel) [ideas:harvest-playbook-nr7-break]', 7)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.34915219378716744. | annualized_return failed: expected > 0.0 (exclusive); observed -0.05804231780311386. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.9327926542006645. | drawdown_magnitude failed: expected <= 0.35 (incl
