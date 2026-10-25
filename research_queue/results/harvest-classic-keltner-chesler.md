# harvest-classic-keltner-chesler: rejected

- Title: MES Keltner channel breakout [ideas:harvest-classic-keltner-chesler]
- Hypothesis: Ideas thesis: Keltner mid = EMA(20) or SMA of typical price; bands = mid ± 2×ATR(10) (Chesler/modern) or 10-day SMA of high/low (original). Long close above upper; short close below lower; trail mid or opposite band. | Pilot behavior: Closes outside a volatility channel may mark intraday trend starts.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_6f6af97e924b4477bbccc66534362c3f; tested 2026-10-25T13:16:52-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 6 / 0
- Best screen setting: {'parameters': {'kc_mult': 2.5, 'trail_atr': 3}, 'sharpe_ratio': -0.0535, 'total_return': -0.0021, 'annualized_return': -0.0005, 'max_drawdown': -0.0263, 'number_of_trades': 586.0, 'win_rate': 0.4317}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'MES Donchian 20/55-day channel breakout (Turtle), intraday [ideas:harvest-playbook-donchian-turtle]', 6), ('candidate', 'MES NR4/NR7 narrow-range bar breakout (Crabel) [ideas:harvest-playbook-nr7-break]', 5), ('candidate', 'MES Keltner channel breakout', 5)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.0021044308524041933. | annualized_return failed: expected > 0.0 (exclusive); observed -0.0004655717336043974. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.05351938704656518.
