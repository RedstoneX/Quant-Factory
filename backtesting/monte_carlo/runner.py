"""Monte Carlo validation, simulation, summaries, and thresholds."""
from datetime import datetime, timezone
import numpy as np
from backtesting.monte_carlo.metrics import cumulative_return, maximum_drawdown, path_sharpe
from backtesting.monte_carlo.models import ExecutionStressResult, MonteCarloResult, ThresholdResult
from backtesting.monte_carlo.resampling import resample_paths

def _summary(values, percentiles):
    a = np.asarray(values, dtype=float)
    result = {"minimum": float(a.min()), "maximum": float(a.max()), "mean": float(a.mean()), "median": float(np.median(a)), "standard_deviation": float(a.std(ddof=0))}
    result.update({f"p{p:g}": float(np.percentile(a, p)) for p in percentiles})
    return result

def _base(status, source, config, reasons, warnings=()):
    return MonteCarloResult(1, status, source, config, len(source.values), {}, {}, None, None, (), (), tuple(reasons), tuple(warnings), datetime.now(timezone.utc).isoformat())

def run_monte_carlo(source, config):
    if source.input_status is not None:
        return _base(source.input_status, source, config, source.input_reasons)
    values = np.asarray(source.values, dtype=float)
    if values.size == 0: return _base("insufficient_evidence", source, config, ("source return series is empty",))
    if not np.isfinite(values).all(): return _base("invalid_input", source, config, ("source returns contain NaN or infinity",))
    if (values <= -1).any(): return _base("invalid_input", source, config, ("source returns must be greater than -1",))
    if len(values) < config.minimum_observations: return _base("insufficient_evidence", source, config, (f"requires at least {config.minimum_observations} observations; received {len(values)}",))
    if config.method == "moving_block_bootstrap" and config.block_length > len(values): return _base("invalid_input", source, config, ("block_length exceeds observation count",))
    paths = resample_paths(values.copy(), config)
    terminals = np.array([cumulative_return(p) for p in paths])
    drawdowns = np.array([maximum_drawdown(p) for p in paths])
    volatilities = paths.std(axis=1, ddof=1)
    sharpes = np.array([path_sharpe(p, config.annualization_factor) for p in paths])
    distributions = {"terminal_return": _summary(terminals, config.percentiles), "maximum_drawdown": _summary(drawdowns, config.percentiles), "path_volatility": _summary(volatilities, config.percentiles)}
    if config.annualization_factor is not None:
        annualized = np.power(1.0 + terminals, config.annualization_factor / len(values)) - 1.0
        distributions["annualized_return"] = _summary(annualized, config.percentiles)
    finite_sharpes = sharpes[np.isfinite(sharpes)]
    if finite_sharpes.size: distributions["sharpe_ratio"] = _summary(finite_sharpes, config.percentiles)
    loss_p = float(np.mean(terminals < 0))
    dd_p = float(np.mean(drawdowns <= -config.drawdown_threshold))
    lower = distributions["terminal_return"][f"p{config.lower_percentile:g}"]
    checks = (("loss_probability", loss_p <= config.maximum_loss_probability, loss_p, config.maximum_loss_probability), ("drawdown_breach_probability", dd_p <= config.maximum_drawdown_breach_probability, dd_p, config.maximum_drawdown_breach_probability), ("lower_percentile_return", lower >= config.minimum_lower_percentile_return, lower, config.minimum_lower_percentile_return))
    rules = tuple(ThresholdResult(i, ok, obs, threshold, f"{i}: observed {obs}, threshold {threshold}") for i, ok, obs, threshold in checks)
    stress: list[ExecutionStressResult] = []
    observed = cumulative_return(values)
    for scenario in config.execution_cost_scenarios:
        costs = {"fee_increase": scenario.fee_increase, "slippage_increase": scenario.slippage_increase, "execution_price_penalty": scenario.execution_price_penalty}
        if source.source_kind != "trade_returns":
            stress.append(ExecutionStressResult(scenario.name, source.source_kind, costs, None, observed, None, None, "insufficient_evidence", ("execution stress requires realized trade returns; period turnover metadata is unavailable",)))
            continue
        penalty = 2 * (scenario.fee_increase + scenario.slippage_increase) + scenario.execution_price_penalty
        stressed_values = values - penalty
        if (stressed_values <= -1).any():
            stress.append(ExecutionStressResult(scenario.name, source.source_kind, costs, "round-trip per realized trade", observed, None, None, "insufficient_evidence", ("stressed trade return is at or below complete loss",)))
            continue
        stressed = cumulative_return(stressed_values)
        stress.append(ExecutionStressResult(scenario.name, source.source_kind, costs, "subtract two-sided fee and slippage increases plus execution penalty from each realized trade return", observed, stressed, stressed - observed, "applied", ()))
    warnings = ["IID bootstrap destroys serial dependence"] if config.method == "iid_bootstrap" else []
    if np.std(values, ddof=1) == 0: warnings.append("source has zero variance; Sharpe is undefined")
    original_metrics = {"cumulative_return": observed, "maximum_drawdown": maximum_drawdown(values)}
    original_sharpe = path_sharpe(values, config.annualization_factor)
    if np.isfinite(original_sharpe): original_metrics["sharpe_ratio"] = original_sharpe
    else: warnings.append("original Sharpe is unavailable")
    if config.method == "path_permutation": warnings.append("permutation preserves terminal compounded return and measures sequencing/drawdown risk only")
    return MonteCarloResult(1, "passed" if all(r.passed for r in rules) else "failed", source, config, len(values), original_metrics, distributions, loss_p, dd_p, rules, tuple(stress), tuple(r.message for r in rules if not r.passed), tuple(warnings), datetime.now(timezone.utc).isoformat(), tuple(tuple(float(x) for x in p) for p in paths) if config.persist_paths else None)
