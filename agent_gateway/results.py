"""Finished-run results the research agent may read: OOS metrics, walk-forward folds, trades, requeue."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from agent_gateway.contracts import GatewayError
from agent_gateway.store import GatewayStore
from orchestration.auto_campaign import POLICY_ID as CAMPAIGN_POLICY_ID
from persistence import ArtifactType, PersistenceService, RunStage, RunStatus

FINISHED = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})
_OOS_KEYS = ("total_return", "max_drawdown", "win_rate", "number_of_trades", "sharpe_ratio")
EASTERN = "US/Eastern"


def evidence_summaries(retrieval: Any) -> list[dict[str, Any]]:
    summaries = []
    for artifact, checked in zip(retrieval.artifacts, retrieval.validations, strict=True):
        if artifact.artifact_type.value != "validation_evidence":
            continue
        document = json.loads(Path(checked.resolved_path or "").read_text())
        summaries.append(
            {
                "logical_name": artifact.logical_name,
                "checksum": artifact.checksum,
                "evidence_identity": (document.get("artifact") or {}).get("evidence_identity"),
                "normalized_evidence": (document.get("evidence") or {}).get("normalized_evidence"),
            }
        )
    return summaries


def is_finished(run: Any) -> bool:
    return run.status in FINISHED


def require_finished(run: Any) -> None:
    if not is_finished(run):
        raise GatewayError("protected_result_denied", "out-of-sample results are available once the run has finished")


def _artifact_documents(
    service: PersistenceService, run_id: str, artifact_root: Path, kind: ArtifactType
) -> list[tuple[str, Any]]:
    retrieval = service.retrieve_run_artifacts(run_id, artifact_root=artifact_root)
    found = []
    for artifact, checked in zip(retrieval.artifacts, retrieval.validations, strict=True):
        if artifact.artifact_type != kind:
            continue
        if not checked.valid:
            raise GatewayError("evidence_invalid", "run evidence failed persisted artifact validation")
        found.append((artifact.logical_name, json.loads(Path(checked.resolved_path or "").read_text())))
    return found


def oos_results(service: PersistenceService, run: Any, artifact_root: Path) -> dict[str, Any]:
    """Out-of-sample metrics read from the persisted report; nothing is recomputed."""
    require_finished(run)
    reports = [
        doc
        for name, doc in _artifact_documents(service, run.run_id, artifact_root, ArtifactType.VALIDATION_EVIDENCE)
        if name.startswith("source_lock_evidence:")
    ]
    if not reports:
        return {"out_of_sample": None, "note": "no out-of-sample report was saved for this run"}
    report = reports[0]
    metrics = report.get("metrics") or {}
    return {
        "out_of_sample": {
            "status": report.get("test_status"),
            **{key: metrics.get(key) for key in _OOS_KEYS},
            "selected_parameters": report.get("selected_parameters"),
        }
    }


def walk_forward_results(service: PersistenceService, run: Any, artifact_root: Path) -> dict[str, Any]:
    """Per-fold walk-forward Sharpe read from the persisted evidence."""
    require_finished(run)
    docs = [
        doc
        for name, doc in _artifact_documents(service, run.run_id, artifact_root, ArtifactType.VALIDATION_EVIDENCE)
        if name == "walk_forward_evidence"
    ]
    if not docs:
        return {"walk_forward": None, "note": "no walk-forward evidence was saved for this run"}
    folds = (docs[0].get("evidence") or {}).get("folds") or []
    return {
        "walk_forward": [
            {
                "fold_id": fold.get("fold_id"),
                "status": fold.get("status"),
                "sharpe_ratio": (fold.get("test_metrics") or {}).get("sharpe_ratio"),
                "total_return": (fold.get("test_metrics") or {}).get("total_return"),
            }
            for fold in folds
        ]
    }


def finished_stage_results(service: PersistenceService, run: Any, artifact_root: Path) -> dict[str, Any] | None:
    if run.stage == RunStage.OOS:
        return oos_results(service, run, artifact_root)
    if run.stage == RunStage.WALK_FORWARD:
        return walk_forward_results(service, run, artifact_root)
    return None


def _eastern(value: Any) -> str | None:
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp
    return stamp.tz_convert(EASTERN).isoformat()


def trade_list(service: PersistenceService, run: Any, artifact_root: Path) -> dict[str, Any]:
    """Per-trade list from the trades the run already saved; never re-simulated."""
    require_finished(run)
    try:
        documents = _artifact_documents(service, run.run_id, artifact_root, ArtifactType.TRADES_OR_ORDERS)
    except RuntimeError:  # no persisted manifest: nothing was saved
        documents = []
    saved = [doc for name, doc in documents if name.endswith("trades_and_orders")]
    if not saved:
        return {"trades": None, "note": "trades were not saved for this run"}
    trades = []
    for row in saved[0].get("trades") or []:
        entry, exit_ = row.get("Avg Entry Price"), row.get("Avg Exit Price")
        short = str(row.get("Direction", "")).lower() == "short"
        points = None if entry is None or exit_ is None else (entry - exit_ if short else exit_ - entry)
        ret = row.get("Return")
        trades.append(
            {
                "entry_time_eastern": _eastern(row.get("Entry Index")),
                "exit_time_eastern": _eastern(row.get("Exit Index")),
                "side": row.get("Direction"),
                "entry_price": entry,
                "exit_price": exit_,
                "pnl_points": points,
                "pnl_percent": None if ret is None else ret * 100,
            }
        )
    return {"trades": trades, "price_unit": saved[0].get("price_unit"), "timezone": EASTERN}


def requeue_interrupted(store: GatewayStore, candidate_id: str) -> dict[str, Any]:
    """Queue an idea again after a server-side interruption. The interruption budget is not reset."""
    latest = store.latest_campaign_event(candidate_id)
    detail = str((latest or {}).get("reason_detail") or "")
    if not latest or latest["state"] != "failed" or latest["reason_code"] != "run_error" or "interrupted" not in detail:
        raise GatewayError(
            "requeue_not_allowed", "only an idea whose test was interrupted by a server failure can be requeued"
        )
    store.append_campaign_event(
        candidate_id=candidate_id,
        policy_id=CAMPAIGN_POLICY_ID,
        state="queued",
        reason_code="requeued_by_agent",
        packet_sha256=latest["packet_sha256"],
    )
    return {"candidate_id": candidate_id, "latest_event": store.latest_campaign_event(candidate_id)}
