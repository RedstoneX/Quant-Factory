"""Validated adapters from pipeline artifacts to Monte Carlo return sources."""
import json, math
from pathlib import Path
from typing import Any
from backtesting.monte_carlo.models import SourceSeries

def load_rsi_walk_forward_source(path: Path) -> SourceSeries:
    base = dict(source_id="rsi_walk_forward_fold_returns", source_kind="fold_endpoint_returns", experiment_id="rsi_spy_daily_demo", strategy_id="rsi_mean_reversion", strategy_version="1.0.0", values=(), provenance={"artifact": str(path), "verified": False}, execution_assumptions={})
    if not path.exists(): return SourceSeries(**base, input_status="insufficient_evidence", input_reasons=("walk-forward artifact is missing",))
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: return SourceSeries(**base, input_status="invalid_input", input_reasons=(f"walk-forward artifact is malformed: {exc}",))
    if not isinstance(payload, dict) or not isinstance(payload.get("folds"), list): return SourceSeries(**base, input_status="invalid_input", input_reasons=("walk-forward artifact folds are missing or malformed",))
    folds = payload["folds"]
    valid_statuses = {"successful", "failed"}
    if any(not isinstance(f, dict) or f.get("status") not in valid_statuses for f in folds): return SourceSeries(**base, input_status="invalid_input", input_reasons=("walk-forward fold status is invalid",))
    expected = {"experiment_id": "rsi_spy_daily_demo", "strategy_id": "rsi_mean_reversion", "strategy_version": "1.0.0"}
    declared_errors = [f"{key} mismatch" for key, value in expected.items() if key in payload and payload[key] != value]
    if "schema_version" in payload and payload["schema_version"] != 1: declared_errors.append("unsupported walk-forward schema version")
    if declared_errors: return SourceSeries(**base, input_status="invalid_input", input_reasons=tuple(declared_errors))
    successful = [f for f in folds if f["status"] == "successful"]
    if not successful:
        provenance = {"artifact": str(path), "verified": False, "successful_folds": 0, "legacy_identity_unavailable": True}
        return SourceSeries(**(base | {"provenance": provenance}), input_status="insufficient_evidence", input_reasons=("walk-forward artifact has no successful folds",))
    errors = [f"{key} mismatch" for key, value in expected.items() if payload.get(key) != value]
    if payload.get("schema_version") != 1: errors.append("unsupported or missing walk-forward schema version")
    execution = payload.get("execution_assumptions")
    if not isinstance(execution, dict) or execution.get("execution_mode") != "next_bar_open": errors.append("execution assumptions are missing or incompatible")
    values = []
    for fold in successful:
        metrics, test = fold.get("test_metrics"), fold.get("test")
        value = metrics.get("total_return") if isinstance(metrics, dict) else None
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value): errors.append(f"{fold.get('fold_id', 'unknown')} total_return is invalid")
        elif not isinstance(test, dict) or not all(test.get(k) for k in ("start", "end", "row_count")): errors.append(f"{fold.get('fold_id', 'unknown')} test boundaries are invalid")
        else: values.append(float(value))
    if errors: return SourceSeries(**base, input_status="invalid_input", input_reasons=tuple(errors))
    provenance = {"artifact": str(path), "verified": True, "successful_folds": len(values), "schema_version": 1}
    return SourceSeries(**(base | {"values": tuple(values), "provenance": provenance, "execution_assumptions": execution}))
