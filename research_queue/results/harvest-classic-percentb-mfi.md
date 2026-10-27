# harvest-classic-percentb-mfi: rejected

- Title: MES Bollinger %B + MFI exhaustion fade [ideas:harvest-classic-percentb-mfi]
- Hypothesis: Band excursions backed by extreme money flow exhaust and revert to the mean intraday.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_62f041be4a134b6495e89b0dee66dd35; tested 2026-10-27T18:08:08-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 12 / 0
- Best screen setting: {'parameters': {'bb_len': 40, 'mfi_lo': 20, 'stop_atr': 3.0}, 'sharpe_ratio': -0.8231, 'total_return': -0.0214, 'annualized_return': -0.0048, 'max_drawdown': -0.0215, 'number_of_trades': 337.0, 'win_rate': 0.4599}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'QQQ Bollinger band mean reversion [ideas:harvest-classic-bb-pctb-mr]', 8), ('candidate', 'MES opening-range failure fade (break, then close back inside) [ideas:harvest-playbook-orf-failure]', 6), ('candidate', 'MES Momentum Pinball intraday (RSI3 of 1-bar ROC) with EMA50 side [ideas:harvest-classic-momentum-pinball]', 6)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.020388590000834372. | annualized_return failed: expected > 0.0 (exclusive); observed -0.004543179276257914. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -1.0715880958587551.
