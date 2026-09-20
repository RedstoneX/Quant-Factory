# Sanitized R07 evidence facts

Status: development/reference screening evidence only. It is not independent
profitability evidence, a protected test, a qualified edge, or promotion,
deployment, paper, futures-execution, or live authority.

## Integrity and shape — measured

- 38 of 38 preserved-file SHA-256 checks passed.
- SQLite integrity passed; schema version is 5.
- Four runs succeeded.
- 32 ranked rows persisted: 2 references plus 30 matrix variants.
- 28 artifact references and 4 run manifests persisted.
- Long and short 30-minute/zero-offset references exactly matched their matrix
  counterparts.
- All 30 matrix variants screened out.
- All four current-`main` application read paths opened without warnings.
- For every run, the database-selected row, saved metrics artifact, and
  dashboard-adapter metric values agreed exactly.

## Rendering comparison — measured

Current `main` displayed only 5 of 15 rows for each matrix direction and did
not expose the key evidence classification, native interval, units, or blocked
promotion context. Local commit `31cf941` displayed 15 of 15 rows and the
correct 5-minute source, index-point prices, USD P&L, development/reference
classification, and not-promotion-eligible status.

## Selected screening summaries — measured from preserved records

| Selection | Total return | Annualized return | Sharpe | Max drawdown | Trades | Win rate |
|---|---:|---:|---:|---:|---:|---:|
| Reference long | 0.97% | 0.21% | 0.10 | -4.76% | 1,170 | 54.27% |
| Reference short | -5.52% | -1.25% | -0.45 | -7.56% | 1,049 | 46.43% |
| Matrix-long selected row | 5.42% | 1.17% | 0.46 | -4.19% | 1,227 | 56.23% |
| Matrix-short selected row | Equal to reference short | Equal | Equal | Equal | 1,049 | 46.43% |

These summaries do not override the screen: every candidate failed its
predeclared baseline gate.

## Calculation convention — inferred, not a persisted contract

The persisted metrics mathematically reproduce using 105,120 five-minute
periods per year (365 days), zero risk-free rate, and sample standard deviation.
The code does not explicitly pass `freq`, `year_freq`, or `risk_free`. This is
an inference from matching arithmetic, not a persisted or verified deployment
default. The recorded interval is 5 minutes.

The R07 run record identifies executable revision
`0f7701fd6d3823b9603576777df441dd92df45a8`, Python 3.12.14, VectorBT Pro
2026.4.7, and a common package fingerprint. Dirty state was unavailable. The
fingerprint and private record identifiers are deliberately omitted.
