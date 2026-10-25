# harvest-classic-wilder-adx-di: rejected

- Title: QQQ EMA cross filtered by ADX trend strength [ideas:harvest-classic-wilder-adx-di]
- Hypothesis: Ideas thesis: +DI crosses above −DI and ADX(14) rising above 25 → long; reverse when −DI > +DI with ADX strong. Exit/flat when ADX rolls over below ~20 (trendless). Classic New Concepts in Technical Trading Systems. | Pilot behavior: Moving-average crosses work better when ADX confirms a trend.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_5ba9fc396f824db9b0d624279821ecec; tested 2026-10-25T15:06:26-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 6 / 0
- Best screen setting: {'parameters': {'adx_min': 30, 'fast': 12}, 'sharpe_ratio': 0.0559, 'total_return': 0.0106, 'annualized_return': 0.0015, 'max_drawdown': -0.1009, 'number_of_trades': 532.0, 'win_rate': 0.4342}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'QQQ EMA cross filtered by ADX trend strength', 10), ('candidate', 'SPY MACD signal-line trend [ideas:harvest-classic-elder-triple-screen]', 8), ('candidate', 'MES Parabolic SAR stop-and-reverse trend [ideas:harvest-classic-parabolic-sar-trail]', 7)]
- Detail: sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.05585160792005536.
