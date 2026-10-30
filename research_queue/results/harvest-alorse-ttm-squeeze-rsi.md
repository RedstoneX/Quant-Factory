# harvest-alorse-ttm-squeeze-rsi: rejected

- Title: MES TTM squeeze release breakout with EMA/RSI direction [ideas:harvest-alorse-ttm-squeeze-rsi]
- Hypothesis: Intraday volatility compression on MES releases into a directional move that persists long enough to beat costs.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_e05ec019d78f436a9937b9579e872958; tested 2026-10-30T18:08:06-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 12 / 0
- Best screen setting: {'parameters': {'ema_len': 50, 'kc_mult': 2.0, 'stop_atr': 3.0}, 'sharpe_ratio': 0.4737, 'total_return': 0.0175, 'annualized_return': 0.0038, 'max_drawdown': -0.0104, 'number_of_trades': 495.0, 'win_rate': 0.4242}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'SPY TTM Squeeze release with RSI direction', 8), ('candidate', 'MES Momentum Pinball intraday (RSI3 of 1-bar ROC) with EMA50 side [ideas:harvest-classic-momentum-pinball]', 7), ('candidate', 'MES Keltner channel breakout [ideas:harvest-classic-keltner-chesler]', 7)]
- Detail: sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.47370540350006035.
