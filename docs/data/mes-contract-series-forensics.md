# MES contract-series forensics

## Status and conclusion

Classification: **confirmed**.

The imported file is reproducibly Databento `MES.c.0` with
`stype_in="continuous"`, calendar/front-expiry rank zero, original unadjusted
contract prices, and UTC one-minute OHLCV aggregated into left-labeled
five-minute bars using first open, maximum high, minimum low, last close, and
summed volume.

## Local provenance inspection

- The canonical Parquet SHA-256 exactly matches the committed manifest:
  `fe6bfe4ea3328660e70c2291fc76ea8039249dfb2d5bb35a6390bd8fc7bf4dd1`.
- Parquet metadata contains only pandas and Arrow structural entries. Its
  schema is UTC `ts_event`, double OHLC, and uint64 volume; `created_by` is
  `parquet-cpp-arrow version 23.0.1`.
- The extracted legacy project contains the preserved MES Parquet and CSV but
  no DBN, symbol mapping, instrument ID, downloader, notebook, or request
  metadata. The narrowly searched shell history had no relevant entries.
- The configured source archive is absent from its recorded location.

## Databento candidates and schema deviation

The tested rank-zero continuous candidates were:

- `MES.c.0`: calendar/front-expiry ranking;
- `MES.n.0`: previous-day open-interest ranking;
- `MES.v.0`: previous-day volume ranking.

Databento continuous data uses original contract prices and does not back-adjust
roll gaps. The current API does not accept the remotely planned `ohlcv-5m`
schema. Databento 0.80.0 returned:

```text
ValueError: The `schema` was not a valid value of Schema, was 'ohlcv-5m'.
```

The comparisons therefore requested supported `ohlcv-1m` and aggregated it
deterministically to five minutes. The exact matches below prove that this is
also the imported file's bar construction.

## Windows, cost estimates, and downloads

The six predefined UTC windows were used without alteration:

| Period | Expiration Friday | Comparison window |
|---|---:|---|
| Early history | 2019-09-20 | 2019-09-09 through 2019-09-23 |
| High volatility | 2020-03-20 | 2020-03-09 through 2020-03-23 |
| Middle history | 2022-06-17 | 2022-06-06 through 2022-06-20 |
| Middle/recent | 2023-12-15 | 2023-12-04 through 2023-12-18 |
| Recent | 2025-03-21 | 2025-03-10 through 2025-03-24 |
| Latest complete | 2025-12-19 | 2025-12-08 through 2025-12-22 |

`Historical.metadata.get_cost` was called separately before every request:

| Window | `MES.c.0` | `MES.v.0` | `MES.n.0` |
|---|---:|---:|---:|
| 2019-09 | 0.04786544 | 0.05371034 | 0.04786544 |
| 2020-03 | 0.04628830 | 0.04848242 | 0.04838750 |
| 2022-06 | 0.05276844 | 0.05454272 | 0.05276844 |
| 2023-12 | 0.05315542 | 0.05528748 | 0.05315542 |
| 2025-03 | 0.05370304 | 0.05541526 | 0.05370304 |
| 2025-12 | 0.05356796 | 0.05541891 | 0.05356796 |
| **Total USD** | | | **0.93965352** |

All 18 bounded requests were downloaded once as compressed DBN under `/tmp`;
the aggregate size was 4,188,110 bytes. DBN instrument mappings were retained.
No individual contract or full-history request was needed. The client provides
the exact historical request cost before submission but no separate
post-download receipt; USD 0.93965352 is the estimated and incurred request
cost.

## Normalization

- Timestamps were normalized to timezone-aware UTC and compared on `ts_event`.
- Columns were normalized to lowercase OHLCV without numeric conversion.
- One-minute bars were grouped into UTC left-closed, left-labeled five-minute
  intervals using first/max/min/last/sum.
- Empty intervals were omitted; no bars were filled, synthesized, or silently
  dropped.
- Exact comparisons used native values. Tolerance comparisons used
  `rtol=1e-12`, `atol=1e-9`.

## Evidence table

Percentages use overlapping timestamps. `First/last` are OHLCV mismatches.

| Window | Candidate | Imported | Candidate | Overlap | Imp-only | Cand-only | Exact OHLC | Exact OHLCV | Tol OHLC | First / last mismatch | Max diff | Vol mismatches | Switch UTC |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| 2019-09 | `MES.c.0` | 2889 | 2889 | 2889 | 0 | 0 | 2889 (100%) | 2889 (100%) | 2889 (100%) | None | 0.00 | 0 | 2019-09-22 22:00 |
| 2019-09 | `MES.v.0` | 2889 | 3003 | 2889 | 0 | 114 | 1662 (57.53%) | 1662 (57.53%) | 1662 (57.53%) | 09-16 00:00 / 09-20 13:25 | 10.00 | 1227 | 2019-09-16 00:00 |
| 2019-09 | `MES.n.0` | 2889 | 2889 | 2889 | 0 | 0 | 2889 (100%) | 2889 (100%) | 2889 (100%) | None | 0.00 | 0 | 2019-09-22 22:00 |
| 2020-03 | `MES.c.0` | 2709 | 2709 | 2709 | 0 | 0 | 2709 (100%) | 2709 (100%) | 2709 (100%) | None | 0.00 | 0 | 2020-03-22 22:00 |
| 2020-03 | `MES.v.0` | 2709 | 2835 | 2667 | 42 | 168 | 1634 (61.27%) | 1634 (61.27%) | 1634 (61.27%) | 03-16 00:00 / 03-20 13:25 | 31.00 | 1017 | 2020-03-16 00:03 |
| 2020-03 | `MES.n.0` | 2709 | 2834 | 2703 | 6 | 131 | 2073 (76.69%) | 2073 (76.69%) | 2073 (76.69%) | 03-18 00:00 / 03-20 13:25 | 31.00 | 627 | 2020-03-18 00:00 |
| 2022-06 | `MES.c.0` | 2898 | 2898 | 2898 | 0 | 0 | 2898 (100%) | 2898 (100%) | 2898 (100%) | None | 0.00 | 0 | 2022-06-19 22:00 |
| 2022-06 | `MES.v.0` | 2898 | 2988 | 2898 | 0 | 90 | 1632 (56.31%) | 1632 (56.31%) | 1632 (56.31%) | 06-13 00:00 / 06-17 13:25 | 14.25 | 1266 | 2022-06-13 00:00 |
| 2022-06 | `MES.n.0` | 2898 | 2898 | 2898 | 0 | 0 | 2898 (100%) | 2898 (100%) | 2898 (100%) | None | 0.00 | 0 | 2022-06-19 22:00 |
| 2023-12 | `MES.c.0` | 2946 | 2946 | 2946 | 0 | 0 | 2946 (100%) | 2946 (100%) | 2946 (100%) | None | 0.00 | 0 | 2023-12-17 23:00 |
| 2023-12 | `MES.v.0` | 2946 | 3036 | 2946 | 0 | 90 | 2220 (75.36%) | 2220 (75.36%) | 2220 (75.36%) | 12-13 00:00 / 12-15 14:25 | 63.75 | 726 | 2023-12-13 00:00 |
| 2023-12 | `MES.n.0` | 2946 | 2946 | 2946 | 0 | 0 | 2946 (100%) | 2946 (100%) | 2946 (100%) | None | 0.00 | 0 | 2023-12-17 23:00 |
| 2025-03 | `MES.c.0` | 2946 | 2946 | 2946 | 0 | 0 | 2946 (100%) | 2946 (100%) | 2946 (100%) | None | 0.00 | 0 | 2025-03-23 22:00 |
| 2025-03 | `MES.v.0` | 2946 | 3036 | 2946 | 0 | 90 | 2232 (75.76%) | 2232 (75.76%) | 2232 (75.76%) | 03-19 00:00 / 03-21 13:25 | 56.50 | 714 | 2025-03-19 00:00 |
| 2025-03 | `MES.n.0` | 2946 | 2946 | 2946 | 0 | 0 | 2946 (100%) | 2946 (100%) | 2946 (100%) | None | 0.00 | 0 | 2025-03-23 22:00 |
| 2025-12 | `MES.c.0` | 2946 | 2946 | 2946 | 0 | 0 | 2946 (100%) | 2946 (100%) | 2946 (100%) | None | 0.00 | 0 | 2025-12-21 23:00 |
| 2025-12 | `MES.v.0` | 2946 | 3036 | 2946 | 0 | 90 | 2220 (75.36%) | 2220 (75.36%) | 2220 (75.36%) | 12-17 00:00 / 12-19 14:25 | 56.50 | 726 | 2025-12-17 00:00 |
| 2025-12 | `MES.n.0` | 2946 | 2946 | 2946 | 0 | 0 | 2946 (100%) | 2946 (100%) | 2946 (100%) | None | 0.00 | 0 | 2025-12-21 23:00 |

Across all windows, `MES.c.0` matched 17,334/17,334 OHLCV bars with zero
timestamp differences. `MES.v.0` matched 11,600/17,292 overlapping bars;
`MES.n.0` matched 16,698/17,328 and was separated conclusively from `c.0` by
March 2020.

## Adjustment tests

`MES.c.0` needs no adjustment: raw price differences are exactly zero,
additive offset is 0.0, ratio is 1.0, and volume matches exactly in every
window. For all mismatching `v.0` windows and March 2020 `n.0`, neither one
stable additive offset nor one stable multiplicative ratio explains all OHLC
fields, and volume also differs. The imported series is raw and unadjusted, not
difference- or ratio-adjusted.

## Reproducible rule

1. Request `GLBX.MDP3` `MES.c.0` with `stype_in="continuous"` and original,
   unadjusted prices.
2. Obtain supported UTC `ohlcv-1m` bars.
3. Aggregate into left-labeled, left-closed five-minute UTC intervals using
   first open, maximum high, minimum low, last close, and summed volume.
4. Do not back-adjust or ratio-adjust calendar/front-expiry switches.

Mapping-derived sampled switch timestamps were 2019-09-22 22:00,
2020-03-22 22:00, 2022-06-19 22:00, 2023-12-17 23:00,
2025-03-23 22:00, and 2025-12-21 23:00 UTC. The seasonal hour difference is
UTC daylight-saving conversion, not a different roll rule.
