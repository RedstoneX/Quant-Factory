# MES execution costs and contract-series investigation

## Resolved IBKR execution cost

As checked on 2026-07-07, the current all-in cost for one standard,
non-member MES execution through IBKR is **USD 0.62 per contract per side**:

- IBKR execution commission: USD 0.25 for the first 1,000 monthly E-micro
  contracts.
- CME exchange-fee recovery: USD 0.35 for Micro E-mini futures including MES.
- NFA regulatory-fee recovery: USD 0.02.
- Separate mandatory clearing fee: USD 0.00 on the applicable IBKR CME
  electronic schedule. No additional clearing line is listed.

Sources:

- [IBKR futures commissions](https://www.interactivebrokers.com/en/pricing/commissions-futures.php)
- [IBKR CME electronic exchange and regulatory fees](https://www.interactivebrokers.com/en/accounts/fees/CME.php)

The amount assumes IBKR is both executing and prime broker, so the listed
USD 0.05 give-up surcharge is waived. It also assumes no exchange membership,
incentive program, IB-JP tax, or monthly volume tier above 1,000 contracts.
IBKR notes that its recovery charges may differ from the exchange's underlying
charge. Revalidate the schedule before paper-to-live promotion.

## Implemented execution scenarios

Use one MES contract with these research assumptions:

- MES tick size: 0.25 index points.
- MES point value: USD 5.00.
- MES tick value: USD 1.25.
- Baseline slippage: 1 tick per side.
- Optimistic slippage scenario: 0.5 tick per side.
- Stress slippage scenario: 2 ticks per side.

Fixed fees are charged on entry and exit. Slippage is applied adversely to the
raw execution price: buys pay more and sells receive less. The point adjustment
is then multiplied by USD 5.00. Fixed futures fees and tick slippage are not
approximated as percentage equity fees.

## Databento contract-series facts

Databento continuous futures use symbols of the form `[ROOT].[ROLL_RULE].[RANK]` with `stype_in=continuous`.

Supported roll rules are:

- `c`: calendar/front-expiry ranking;
- `n`: previous-day open-interest ranking;
- `v`: previous-day volume ranking.

Databento continuous prices are original, unadjusted contract prices. Databento does not back-adjust the series to remove rollover gaps.

The imported MES Parquet itself does not preserve contract symbols or instrument
IDs, but bounded authenticated comparison has now reproduced its construction.

## Local investigation result

Classification: **confirmed**.

Evidence inspected:

- The canonical and preserved legacy MES Parquet contain only UTC `ts_event`
  plus OHLCV. Embedded metadata is pandas/Arrow structural metadata only;
  `created_by` is `parquet-cpp-arrow version 23.0.1`.
- The redundant CSV has the same six fields and no symbol, raw symbol,
  instrument ID, mapping, or request metadata.
- Narrow searches of the active repository and documented extracted legacy
  root found no Databento downloader, notebook, DBN sidecar, symbol mapping,
  or command identifying `MES.c.0`, `MES.v.0`, or `MES.n.0`.
- The configured archive path no longer exists, so its member list could not be
  rechecked. The cataloged files remain present and hash-verified.
- The current API rejected the planned `ohlcv-5m` schema, so supported
  `ohlcv-1m` was aggregated deterministically to five minutes.
- Across six quarterly windows, `MES.c.0` reproduced all 17,334 sampled OHLCV
  bars exactly, with zero timestamp or volume differences. `MES.v.0` failed all
  six windows; `MES.n.0` diverged in March 2020.
- Mapping-derived switches agree with the calendar/front-expiry rule. Raw
  prices require no additive or ratio adjustment.

The reproducible rule and full evidence table are recorded in
`docs/data/mes-contract-series-forensics.md`.

## Cost-scenario result

All scenarios evaluated the same exact 30 variants over the hash-verified
476,042-row source:

| Scenario | Slippage/side | Cheap-screen passes | Top variant | Total return | Sharpe | Max drawdown magnitude | Trades |
|---|---:|---:|---|---:|---:|---:|---:|
| Baseline | 1 tick | 0 | Long, 15-minute range, 2-tick offset | 5.4248% | 0.4588 | 4.1905% | 1,227 |
| Optimistic | 0.5 tick | 3 | Long, 15-minute range, 2-tick offset | 6.9585% | 0.5855 | 3.5552% | 1,227 |
| Stress | 2 ticks | 0 | Long, 15-minute range, 2-tick offset | 2.3573% | 0.2064 | 5.4612% | 1,227 |

The baseline top row fails the provisional 0.5 Sharpe threshold. No baseline
candidate survives cheap screening, so no deeper validation is justified.
Optimistic passes do not override the baseline rejection or unresolved roll
construction.
