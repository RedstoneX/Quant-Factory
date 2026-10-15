# 20-strategy pilot

Twenty well-known published intraday or swing strategies written as `qf_candidate_v1` packets with `qf_rules_v1` rule specs, so the factory can test them.

- Every packet passes `validate_candidate_packet` and `validate_rule_spec` with zero errors; grids are 3 to 12 settings.
- The rule language requires a same-session flat time, so every packet is intraday and flat by 15:55 ET; swing ideas (Turtle, RSI(2), Double 7s, IBS) are intraday translations, and multi-day lookbacks use `across_sessions` windows.
- Exits can only be stops, targets, trailing stops, N-bar time exits or opposite signals (no indicator-based exit on main yet), so "exit at the middle band" style exits are replaced by time exits.
- The prior session close is read as `value_at(sum(close, 2, across_sessions) - close, first bar)`.
- SPY and QQQ use the `equities_<SYMBOL>_1m_alpaca_sip` datasets from 2016-01-04; MES uses `futures_MES_5m_databento`.

| # | Packet | Market | Source | Rule |
|---|---|---|---|---|
| 1 | MES 15-minute opening-range breakout (Crabel) | MES 5m | Toby Crabel (1990), Day Trading with Short Term Price Patterns and Opening Range Breakout | Trade the first close beyond the 09:30-09:45 range plus an offset, ATR stop, flat by 15:55. |
| 2 | SPY RSI(2) pullback in uptrend (Connors), intraday | SPY 1m | Larry Connors and Cesar Alvarez (2008), Short Term Trading Strategies That Work | Buy when RSI(2) drops below a threshold while price is above its one-session average; target, time and 0.5% stop exits. |
| 3 | QQQ Bollinger band mean reversion | QQQ 1m | John Bollinger (2001), Bollinger on Bollinger Bands | Fade closes that cross outside the 20-bar Bollinger band; exit after N bars or 0.5% stop. |
| 4 | MES Donchian 20/55-day channel breakout (Turtle), intraday | MES 5m | Richard Donchian; Turtle Trading rules (Curtis Faith, Way of the Turtle, 2007) | Trade a close beyond the prior 20- or 55-day high/low channel with a Turtle 2N-style ATR stop, flat by 15:55. |
| 5 | SPY MACD signal-line trend | SPY 1m | Gerald Appel (1979), MACD | Go with MACD line crossing its signal line on the side of zero; reverse on the opposite cross; 0.5% stop. |
| 6 | QQQ VWAP deviation reversion | QQQ 1m | Session VWAP benchmark (Berkowitz, Logue and Noser, 1988, Journal of Finance) | Fade price stretched a set percent from session VWAP; exit after N bars or 0.5% stop. |
| 7 | SPY opening gap fade | SPY 1m | Gap fill pattern (Bulkowski, Encyclopedia of Chart Patterns) | At 09:31, fade an opening gap larger than a threshold versus the prior close; exit after N bars or 0.75% stop. |
| 8 | SPY first-half-hour predicts last-half-hour (Gao et al.) | SPY 1m | Gao, Han, Li and Zhou (2018), Market Intraday Momentum, Journal of Financial Economics | At 15:30, take the sign of the prior-close-to-10:00 return; hold to 15:55. |
| 9 | MES NR4/NR7 narrow-range bar breakout (Crabel) | MES 5m | Toby Crabel (1990), NR4/NR7 narrow-range patterns | After the narrowest bar of the last 4 or 7, trade the break of its high or low; ATR stop, N-bar time exit. |
| 10 | QQQ inside-bar breakout | QQQ 1m | Inside-bar pattern (Thomas Bulkowski, Encyclopedia of Candlestick Charts) | After an inside bar, trade the break of its high or low; percent stop, N-bar time exit. |
| 11 | MES Keltner channel breakout | MES 5m | Chester Keltner (1960), How to Make Money in Commodities | Trade closes crossing outside an EMA(20) +/- k ATR(10) channel; ATR trailing stop; reverse on opposite signal. |
| 12 | SPY slow stochastic oversold/overbought reversal | SPY 1m | George Lane, stochastic oscillator (1950s) | Buy %K crossing above %D below the oversold line, short the mirror; N-bar exit, 0.4% stop. |
| 13 | QQQ EMA cross filtered by ADX trend strength | QQQ 1m | J. Welles Wilder (1978), New Concepts in Technical Trading Systems (ADX) | Trade fast/26 EMA crosses only when ADX(14) exceeds a threshold; reverse on opposite signal; 0.5% stop. |
| 14 | MES Williams %R exit-from-extreme reversal | MES 5m | Larry Williams (1973), How I Made One Million Dollars Last Year Trading Commodities | Buy %R crossing back up through the oversold line, short the mirror; ATR stop, N-bar exit. |
| 15 | QQQ CCI reversal from +/-100 | QQQ 1m | Donald Lambert (1980), Commodity Channel Index, Commodities magazine | Buy CCI crossing back above -threshold, short crossing back below +threshold; N-bar exit, 0.4% stop. |
| 16 | MES Parabolic SAR stop-and-reverse trend | MES 5m | J. Welles Wilder (1978), New Concepts in Technical Trading Systems (Parabolic SAR) | Go long when close crosses above SAR and short when below; always reverse; 3 ATR stop backstop. |
| 17 | QQQ rest-of-day return predicts last half hour | QQQ 1m | Baltussen, Da, Lammers and Martens (2021), Hedging demand and market intraday momentum, Journal of Financial Economics | At 15:30, take the sign of the prior-close-to-15:30 return; hold to 15:55. |
| 18 | MES overnight gap-and-go continuation | MES 5m | Breakaway gap continuation (Bulkowski, Encyclopedia of Chart Patterns) | If the open gaps beyond a threshold and the first 5m bar closes in the gap direction, trade with it at 09:35; ATR stop. |
| 19 | SPY Double 7s (Connors), intraday | SPY 1m | Larry Connors and Cesar Alvarez (2009), Short Term Trading Strategies That Work (Double 7s) | Buy a new N-bar closing low while above the 5-session average; N-bar time exit, 0.5% stop. |
| 20 | QQQ internal bar strength mean reversion, intraday | QQQ 1m | Internal Bar Strength effect (Pagonidis, The IBS Effect: Mean Reversion in Equity ETFs, NAAIM 2014) | At 10:00, buy if the close sits in the bottom of its trailing one-session range (IBS); 1% stop, flat at 15:55. |
