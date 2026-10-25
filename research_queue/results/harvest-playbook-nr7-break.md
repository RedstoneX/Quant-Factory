# harvest-playbook-nr7-break: rejected

- Title: MES NR4/NR7 narrow-range bar breakout (Crabel) [ideas:harvest-playbook-nr7-break]
- Hypothesis: Ideas thesis: Identify NR7 (narrowest range of last 7 bars); enter break of NR7 high/low next session; stop opposite side. Crabel-style. | Pilot behavior: Range contraction tends to precede range expansion.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_2cb5d460e7ad46aab3500dede7d0a231; tested 2026-10-25T11:19:24-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 12 / 0
- Best screen setting: {'parameters': {'hold_bars': 12, 'nr_bars': 4, 'stop_atr': 2.0}, 'sharpe_ratio': -1.554, 'total_return': -0.1017, 'annualized_return': -0.0234, 'max_drawdown': -0.105, 'number_of_trades': 3299.0, 'win_rate': 0.4556}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'MES NR4/NR7 narrow-range bar breakout (Crabel)', 10), ('candidate', 'MES 15-minute opening-range breakout (Crabel) [ideas:harvest-playbook-session-orb]', 9), ('candidate', 'MES Donchian 20/55-day channel breakout (Turtle), intraday [ideas:harvest-playbook-donchian-turtle]', 7)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.09674820048772415. | annualized_return failed: expected > 0.0 (exclusive); observed -0.022241890226123884. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -1.5738039767873269.
