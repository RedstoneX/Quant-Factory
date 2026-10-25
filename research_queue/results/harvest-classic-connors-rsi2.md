# harvest-classic-connors-rsi2: rejected

- Title: SPY RSI(2) pullback in uptrend (Connors), intraday [ideas:harvest-classic-connors-rsi2]
- Hypothesis: Ideas thesis: Long only when close > SMA200 and RSI(2) ≤ 5 at the close; exit on first close above SMA5. Short mirror when close < SMA200 and RSI(2) ≥ 95, exit below SMA5. No stop in the published book rules (Connors & Alvarez, Short-Term Trading Strateg | Pilot behavior: Very short-term oversold pullbacks inside an uptrend may revert upward within the session.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_2fd3245ae2934d0c89179cc6444a46b0; tested 2026-10-25T12:09:35-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 12 / 0
- Best screen setting: {'parameters': {'hold_bars': 60, 'rsi_entry': 5, 'target_pct': 0.1}, 'sharpe_ratio': -0.1717, 'total_return': -0.0445, 'annualized_return': -0.0063, 'max_drawdown': -0.1596, 'number_of_trades': 3508.0, 'win_rate': 0.6582}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'SPY RSI(2) pullback in uptrend (Connors), intraday', 9), ('candidate', 'QQQ Bollinger band mean reversion [ideas:harvest-classic-bb-pctb-mr]', 7), ('candidate', 'SPY Double 7s (Connors), intraday', 7)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.03889623610269621. | annualized_return failed: expected > 0.0 (exclusive); observed -0.005508293318916224. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.17389448961286647.
