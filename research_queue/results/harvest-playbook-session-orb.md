# harvest-playbook-session-orb: rejected

- Title: MES 15-minute opening-range breakout (Crabel) [ideas:harvest-playbook-session-orb]
- Hypothesis: Ideas thesis: Define RTH opening range (e.g. first 15–30m); buy break of OR high / sell break of OR low; stop mid-OR or opposite side; time-stop by session end. | Pilot behavior: A completed close beyond the first 15 minutes' range may continue in the breakout direction for the rest of the session.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_cac45b49fa9a47bfb133c8c9864c33e9; tested 2026-10-25T10:43:01-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 12 / 0
- Best screen setting: {'parameters': {'offset_ticks': 4, 'stop_atr': 1.0}, 'sharpe_ratio': 0.1875, 'total_return': 0.0113, 'annualized_return': 0.0025, 'max_drawdown': -0.0266, 'number_of_trades': 1083.0, 'win_rate': 0.2456}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('prior_work', '', 8), ('candidate', 'NVDA 5-minute opening range breakout on high opening-volume days', 8), ('candidate', 'MES 15-minute opening-range breakout (Crabel)', 8)]
- Detail: sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.1845578193629714.
