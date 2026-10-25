# harvest-playbook-donchian-turtle: rejected

- Title: MES Donchian 20/55-day channel breakout (Turtle), intraday [ideas:harvest-playbook-donchian-turtle]
- Hypothesis: Ideas thesis: Enter on N-day Donchian channel breakout (classic 20); exit on shorter M-day channel opposite (classic 10) or ATR trail; voluntary unit sizing optional. | Pilot behavior: A break of a multi-day channel may continue intraday.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_3f5de73db27f46389382b1f348d69d18; tested 2026-10-25T11:18:43-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 6 / 0
- Best screen setting: {'parameters': {'channel_bars': 1560, 'stop_atr': 3}, 'sharpe_ratio': -0.5296, 'total_return': -0.014, 'annualized_return': -0.0031, 'max_drawdown': -0.0206, 'number_of_trades': 189.0, 'win_rate': 0.4921}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'MES Donchian 20/55-day channel breakout (Turtle), intraday', 11), ('candidate', 'SPY Donchian breakout with VWAP side filter, ATR trail', 9), ('candidate', 'MES 15-minute opening-range breakout (Crabel) [ideas:harvest-playbook-session-orb]', 8)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.012248548931112602. | annualized_return failed: expected > 0.0 (exclusive); observed -0.0027205850421810895. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -1.2512428593303035.
