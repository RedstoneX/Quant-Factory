# harvest-playbook-orf-failure: rejected

- Title: MES opening-range failure fade (break, then close back inside) [ideas:harvest-playbook-orf-failure]
- Hypothesis: Failed opening-range breakouts trap breakout traders; the reversal back through the range runs toward the opposite side.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_2cc4fd353de94c5589b75af10078a1e1; tested 2026-10-27T17:37:13-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 9 / None
- Best screen setting: {}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'MES 15-min ORB failure fade', 12), ('candidate', 'SPY ORB retest failure (5m OR), continuation', 10), ('candidate', 'SPY ORB retest failure (30m OR), continuation', 10)]
- Detail: no trades: the entry rule never fired in this period | no trades: the entry rule never fired in this period | total_return failed: expected > 0.0 (exclusive); observed 0.0. | annualized_return failed: expected > 0.0 (exclusive); observed 0.0. | sharpe_ratio failed: expected >= 0.5 (inclusive); obser
