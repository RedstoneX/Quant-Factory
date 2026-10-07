# VectorBT UI and Optimization Reuse Research

This is supporting technical research. `docs/MILESTONES.md` remains the sole
authority for current status, priority, sequencing, and next action.

## Purpose

Preserve the VectorBT, Plotly, and dashboard findings recovered from the
2026-10-06 through 2026-10-07 operator-product investigation. These findings
guide reuse choices; they do not authorize a Candidate, parameter search,
protected-test access, paper/live trading, or capital exposure.

## Sources inspected

- VectorBT Pro private repository, including the first-party agent guidance in
  `vectorbtpro/agents/skills/vbt-optimization/SKILL.md`,
  `vbt-cross-validation/SKILL.md`, and `vbt-plotting/SKILL.md`.
- VectorBT Pro [strategy optimization](https://members.vectorbt.pro/features/optimization/strategy-optimization/)
  and [time-series cross-validation](https://members.vectorbt.pro/features/optimization/time-series-cross-validation/)
  documentation.
- The official public VectorBT
  [Dash candlestick-pattern application](https://github.com/polakowo/vectorbt/tree/master/apps/candlestick-patterns).
- VectorBT [issue #699](https://github.com/polakowo/vectorbt/issues/699), where
  the maintainer recommends portfolio resampling or `plotly-resampler` for
  high-granularity line plots.
- VectorBT [discussion #866](https://github.com/polakowo/vectorbt/discussions/866)
  on correcting a selected Sharpe for the number of trials. It is rationale,
  not an accepted Quant Factory evidence method.
- Plotly Resampler's maintained Dash integration and trace limitations.
- Two community dashboards reviewed as interaction references only. Neither
  declared a software license, so their code is not a Quant Factory source.

The private GitHub repository is available through the configured GitHub CLI.
The members site rejected unattended access through Cloudflare; browser cookies
were never read or reused. The private repository and owner-provided members
content therefore remain the reproducible sources available to Codex.

## Durable conclusions

### Existing stack

Keep Plotly Dash as the operator application, VectorBT Pro as the simulation
and analytics engine, Plotly for figures, and Dash AG Grid for result tables.
Use Plotly Resampler only where a measured chart problem and supported trace
type justify it. Do not add a second frontend, chart framework, or optimization
engine.

### Results performance

VectorBT and Plotly guidance supports resampling large line series. Plotly
Resampler dynamically aggregates `Scatter`/`Scattergl` traces, but it does not
resample candlesticks and can break mixed-trace figures. Quant Factory's price
workspace combines candlesticks with trade markers, so it must not be globally
wrapped merely because the page is slow.

Profiling the real sealed ORB/VWAP run found the current bottlenecks at the
server boundary: decoding one 80 MB JSON artifact, scanning every rendered bar
for every entry/exit event, and eagerly building charts inside closed or not-yet
active UI regions. The correct reusable pattern is one checksum-validated read,
indexed event lookup, progressive chart construction, and bounded payloads.
Dynamic resampling remains appropriate for a future measured line-only chart.

The first deployed implementation at revision `b7ad084` removed those server
hotspots, then a representative browser trace exposed the next owning boundary:
the mounted callback graph loaded a 909 KB trade-grid response twice while the
Trades tab was inactive, and the deferred chart callback rejected its own
combined initial trigger. The durable pattern is therefore route- and tab-aware
hydration driven by one canonical selection state, plus explicit handling of
simultaneous Dash inputs. Server timings alone do not establish operator load
time.

### Parameter studies and automatic optimization

Use VectorBT Pro's native conditional parameter grids, random subsets,
chunking, caching, and supported parallel execution. Quant Factory supplies the
approved Candidate bounds, immutable configuration identity, search budget,
costs, data period, objective, lineage, evidence stages, and operator review.

During a sweep, return only the metrics required for ranking and rejection,
such as return, Sharpe, drawdown, Sortino, and trade count. Do not retain a full
portfolio for every combination. Recompute and persist complete portfolio,
chart, trade, and evidence artifacts only for selected finalists.

The operator experience should expose:

- approved parameter ranges and conditional relationships;
- combination count or random-sample budget before launch;
- progress, cancellation, and readable failures;
- sortable/filterable metrics, including return versus drawdown;
- heatmaps or equivalent parameter-region views;
- neighboring-parameter stability rather than one winning row;
- OOS, walk-forward, regime, and higher-cost evidence;
- trade diagnostics by available time, side, holding period, losing streak,
  and documented regime;
- finalist shortlist, comparison, reopen, and exact evidence drilldown.

Automatic optimization produces candidates for review. It never promotes an
edge automatically and cannot alter an already fixed Candidate contract.

### Intraday metric basis

VectorBT's source `freq` describes bar spacing. Annualized metrics also require
an explicit effective trading-year basis. Quant Factory now owns this at its
metric boundary by using completed exchange-session closing equity plus the
recorded calendar, sessions per year, risk-free rate, and derivation basis.
Sealed historical runs are not rewritten.

### Version compatibility

VectorBT Pro v2026.10.5 is the selected upgrade target but is not installed.
The private release is source-only and changes stop-price, risk-free-rate, and
statistics defaults. Upgrade work therefore requires its own source-build and
compatibility proof before deployment. The deployed engine remains v2026.4.7.
