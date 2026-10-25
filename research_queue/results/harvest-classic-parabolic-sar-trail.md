# harvest-classic-parabolic-sar-trail: rejected

- Title: MES Parabolic SAR stop-and-reverse trend [ideas:harvest-classic-parabolic-sar-trail]
- Hypothesis: Ideas thesis: Long while SAR dots below price; flip short when SAR flips above (and vice versa). AF start 0.02, step 0.02, max 0.20 (Wilder defaults). Pure mechanical trail/flip. | Pilot behavior: A stop-and-reverse trailing system may capture intraday trends.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_b1dac6880bea4cdfbce0f987b6f6854f; tested 2026-10-25T15:06:07-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 4 / 0
- Best screen setting: {'parameters': {'af_max': 0.1, 'af_step': 0.01}, 'sharpe_ratio': -1.1599, 'total_return': -0.0788, 'annualized_return': -0.018, 'max_drawdown': -0.0815, 'number_of_trades': 1984.0, 'win_rate': 0.3765}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'MES Keltner channel breakout [ideas:harvest-classic-keltner-chesler]', 8), ('candidate', 'MES Donchian 20/55-day channel breakout (Turtle), intraday [ideas:harvest-playbook-donchian-turtle]', 8), ('candidate', 'SPY MACD signal-line trend [ideas:harvest-classic-elder-triple-screen]', 7)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.07877671346411697. | annualized_return failed: expected > 0.0 (exclusive); observed -0.017974491244404533. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -1.1598710158681536.
