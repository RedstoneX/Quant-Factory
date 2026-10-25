# harvest-classic-elder-triple-screen: rejected

- Title: SPY MACD signal-line trend [ideas:harvest-classic-elder-triple-screen]
- Hypothesis: Ideas thesis: Screen1: weekly/impulse trend via MACD-Histogram or EMA slope (trade only with weekly tide). Screen2: daily oscillator pullback (Force Index or Stoch) against the weekly tide. Screen3: intraday breakout entry in tide direction with stop bey | Pilot behavior: MACD crosses on the trend side of zero may capture intraday trend legs.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_467ed3e4c82149e796cb7b95ce657832; tested 2026-10-25T12:33:53-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 4 / 0
- Best screen setting: {'parameters': {'fast': 12, 'slow': 39}, 'sharpe_ratio': 0.0365, 'total_return': -0.0047, 'annualized_return': -0.0007, 'max_drawdown': -0.1897, 'number_of_trades': 4305.0, 'win_rate': 0.3921}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'SPY RSI(2) pullback in uptrend (Connors), intraday [ideas:harvest-classic-connors-rsi2]', 7), ('candidate', 'MES Donchian 20/55-day channel breakout (Turtle), intraday [ideas:harvest-playbook-donchian-turtle]', 7), ('candidate', 'SPY Parabolic SAR flip, % trail', 7)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.004669038806452419. | annualized_return failed: expected > 0.0 (exclusive); observed -0.0006513640959542322. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.036507697499347125.
