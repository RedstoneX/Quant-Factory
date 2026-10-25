# harvest-classic-bb-pctb-mr: rejected

- Title: QQQ Bollinger band mean reversion [ideas:harvest-classic-bb-pctb-mr]
- Hypothesis: Ideas thesis: BB(20,2). Long: close below lower band (%B<0) then next close back above lower band; stop under outside-bar low; target middle band; time-stop ~8 bars. Short mirror. Skip if outside ≥3 bars (band walk) or during a squeeze. | Pilot behavior: Closes outside a volatility band may snap back toward the mean within an hour.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_7560b72343c14612905e34ea9ffae498; tested 2026-10-25T12:08:50-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 9 / 0
- Best screen setting: {'parameters': {'hold_bars': 60, 'std_mult': 2.0}, 'sharpe_ratio': -0.3309, 'total_return': -0.2662, 'annualized_return': -0.0422, 'max_drawdown': -0.3915, 'number_of_trades': 7156.0, 'win_rate': 0.4769}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'QQQ VWAP deviation reversion [ideas:harvest-playbook-vwap-bands]', 6), ('candidate', 'SPY Bollinger mean-reversion (touch outer band), TP to mid approx', 6), ('candidate', 'SPY Bollinger breakout (20,2), trail to mid-band approx via % trail', 6)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.1489494074526092. | annualized_return failed: expected > 0.0 (exclusive); observed -0.02220473209507301. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.46261718824458903.
