"""Lightweight fallback rows for Results history hydration."""

from __future__ import annotations

from orchestration import FixtureRunService


def fallback_history_rows(runs: FixtureRunService) -> list[dict[str, object]]:
    """Return recent run identity when enriched history is unavailable."""

    return [
        {
            "run_id": run.run_id,
            "created_at": run.created_at,
            "instrument": "Not recorded",
            "strategy": f"{run.strategy_id} {run.strategy_version}",
            "stage": run.stage,
            "status": run.status,
            "review": "Not checked",
            "evidence": "Unverified",
            "metric_basis": "No persisted ranked result",
            "total_return": None,
            "annualized_return": None,
            "sharpe_ratio": None,
            "number_of_trades": None,
            "artifact_status": "Unverified",
            "reproducibility": "Unverified",
        }
        for run in runs.recent_runs(limit=20)
    ]
