# 2026-10-25-mnq-vwap-pullback: rejected

- Title: MNQ VWAP pullback continuation (5m)
- Hypothesis: On MNQ trend days, institutional VWAP participation creates pullbacks to session VWAP that resume the morning trend once price reclaims the line.
- Verdict: **rejected**; failed stage: oos; QF state: screened_out (oos)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_1a2c1c4347c648a1b22050780f2777a5; tested 2026-10-25T00:25:56-04:00
- Stages: {'chain': 'stopped', 'oos': 'invalid'}
- Stable region (stress stage): None
- Settings tested / passing screen: 27 / 17
- Best screen setting: {'parameters': {'band_atr': 0.5, 'stop_atr': 1.5, 'trend_bars': 3}, 'sharpe_ratio': 0.9437, 'total_return': 0.0839, 'annualized_return': 0.018, 'max_drawdown': -0.0296, 'number_of_trades': 976.0, 'win_rate': 0.4037}
- Locked setting: {'band_atr': 1.0, 'stop_atr': 2.0, 'trend_bars': 3}
- Unseen 20% (pre-holdout): {'status': 'screened_out', 'total_return': -0.0047, 'max_drawdown': -0.0406, 'win_rate': 0.4125, 'number_of_trades': 257, 'sharpe_ratio': -0.1572, 'selected_parameters': {'band_atr': 1.0, 'stop_atr': 2.0, 'trend_bars': 3}}
- Walk-forward: None
- Scored stage fails: ['oos']
- Prior matches: [('candidate', 'TEST ONLY - Claude usability check 2026-10-13 (ignore)', 4), ('candidate', 'QQQ VWAP side trend, reverse on cross', 3), ('candidate', 'SPY first-hour trend continuation at 10:30, wide % trail', 3)]
- Detail: out-of-sample run has no single valid source-lock artifact: source-lock evidence is invalid: test did not pass
