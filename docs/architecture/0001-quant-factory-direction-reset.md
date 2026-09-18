# ADR 0001: Quant Factory Direction Reset

- **Status:** Accepted
- **Date:** 2026-07-04
- **Updated:** 2026-07-06

## Context

Quant Factory exists to help the project owner discover, validate, paper trade,
and ultimately live trade robust strategies that can generate reliable
long-term income. The project is not being built for technical novelty.
Development effort must shorten the responsible path to a validated,
deployable strategy.

The financial objective is deliberately practical rather than spectacular. A modest positive average, potentially beginning around $100 per trading day after costs and losses, would already be materially useful. Larger results should come through evidence-based scaling rather than by designing for unrealistic backtest returns. Daily profit is not expected to be smooth or guaranteed; the relevant measure is positive long-run expectancy after commissions, slippage, financing, drawdowns, and losing periods.

## Decision

### 1. Work one architectural topic at a time

Major decisions will be discussed and approved sequentially. Avoid broad multi-topic design dumps that create cognitive overload or leave decisions ambiguous.

### 2. Keep the strategy engine broker-agnostic

Strategies produce trading decisions only. Broker- and exchange-specific behavior belongs in separate execution adapters.

Initial execution targets may include:

- Alpaca paper and live trading
- Interactive Brokers paper and live trading, including futures where supported
- Hyperliquid testnet and live trading

The same strategy logic should move from research to paper, small-capital live validation, and larger allocation without broker-specific rewrites.

### 3. Treat the dashboard as part of the decision system

The dashboard is not cosmetic. Visual review is essential for understanding equity curves, drawdowns, validation failures, regime behavior, and promotion status.

The first useful dashboard should support rapid human decisions such as:

- Reject
- Revise
- Watchlist
- Paper trade
- Small live test
- Stop trading

Dashboard evaluation and a minimal visual decision interface begin after the reusable experiment runner exists. Advanced dashboard work can continue later as validation, paper, and live workflows mature.

Reuse existing VectorBT Pro visualizations, dashboard examples, QuantStats reports, Forven-inspired workflow patterns, and proven interface components before building custom replacements.

### 4. Integrate before building

Quant Factory is an integration project, not a greenfield rewrite of tools that already exist.

Before building any substantial component, ask:

1. What problem does this solve?
2. Does an existing mature project already solve it?
3. Does adopting it replace planned work?
4. Does it shorten the path to reliable trading income?

Integrate mature components when practical. Build custom replacements only when they provide a measurable advantage.

### 5. Optimize for modest, repeatable profitability before scale

The system does not need extraordinary returns to succeed. It must seek positive expectancy with controlled risk, validate behavior through paper trading and micro-size live capital, and scale only when evidence supports doing so.

A simpler strategy with credible, repeatable net profitability is preferred over a complicated strategy with spectacular but fragile backtest results.

## Consequences

- VectorBT Pro remains the core research and backtesting engine.
- Existing reporting, validation, dashboard, and broker libraries should be evaluated before custom development.
- Projects such as Forven are reviewed primarily for reusable workflow, architecture, and implementation patterns—not merely as interesting software.
- Licensing must be checked before copying code. Concepts and patterns may be reimplemented when direct reuse is unsuitable.
- Paper trading and live trading are part of the core architecture from the beginning, even when implemented after research and validation.
- Initial live deployment uses tightly bounded capital and explicit kill switches.
- Strategy evaluation emphasizes net expectancy, drawdown, robustness, and scalability rather than a fixed daily-profit promise.
- Google Docs may capture meeting discussion, while accepted implementation decisions are recorded in GitHub ADRs for Codex and future development work.

## Mission

> Build an AI-assisted quantitative research platform that discovers, validates, paper trades, and ultimately live trades robust strategies capable of producing modest, repeatable, risk-controlled income and scaling only when supported by evidence.
