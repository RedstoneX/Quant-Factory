# harvest-arxiv-2605-04004: rejected

- Title: SPY opening gap fade [ideas:harvest-arxiv-2605-04004]
- Hypothesis: Ideas thesis: Paper tests ORB, Asia expansion/liquidity-grab, gap fill/continuation, volume spike/dry-up, VVG reverse/continue/fade on MNQ — treat each family as a candidate to re-test with our cost gates (many failed in paper). | Pilot behavior: Moderate overnight gaps in SPY may partly fill in the first hours.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_98a492af479a4692892e16672a89b6bf; tested 2026-10-25T13:40:56-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 9 / 0
- Best screen setting: {'parameters': {'gap_frac': 0.0075, 'hold_bars': 30}, 'sharpe_ratio': -0.4087, 'total_return': -0.0844, 'annualized_return': -0.0122, 'max_drawdown': -0.1507, 'number_of_trades': 297.0, 'win_rate': 0.4444}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'IWM 15-min ORB gap-day aligned, wide % trail', 6), ('candidate', 'SPY opening gap fade', 6), ('candidate', 'SPY RSI(2) pullback in uptrend (Connors), intraday [ideas:harvest-classic-connors-rsi2]', 5)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.0843584048678061. | annualized_return failed: expected > 0.0 (exclusive); observed -0.012195099343622617. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.4086777013609501.
