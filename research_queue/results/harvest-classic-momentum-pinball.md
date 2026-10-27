# harvest-classic-momentum-pinball: rejected

- Title: MES Momentum Pinball intraday (RSI3 of 1-bar ROC) with EMA50 side [ideas:harvest-classic-momentum-pinball]
- Hypothesis: Short bursts of selling inside an intraday uptrend mean-revert within an hour or two.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_f7f486d789894864b075da667f3dcba4; tested 2026-10-27T17:36:49-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 9 / 0
- Best screen setting: {'parameters': {'hold_bars': 12, 'low_th': 10}, 'sharpe_ratio': -0.1936, 'total_return': -0.0003, 'annualized_return': -0.0001, 'max_drawdown': -0.0007, 'number_of_trades': 12.0, 'win_rate': 0.5}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'SPY slow stochastic oversold/overbought reversal [ideas:harvest-arxiv-1412-7649]', 9), ('candidate', 'SPY opening gap fade [ideas:harvest-arxiv-2605-04004]', 9), ('candidate', 'SPY RSI(2) pullback in uptrend (Connors), intraday [ideas:harvest-classic-connors-rsi2]', 9)]
- Detail: number_of_trades failed: expected >= 20 (inclusive); observed 12. | total_return failed: expected > 0.0 (exclusive); observed -0.000252354556428247. | annualized_return failed: expected > 0.0 (exclusive); observed -5.578912233050737e-05. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -
