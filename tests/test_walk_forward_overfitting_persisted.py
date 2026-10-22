"""Idea-level luck checks are recorded in the walk-forward evidence artifact."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from backtesting.screening.deflated_sharpe import DeflatedSharpeResult
from backtesting.screening.overfitting_pbo import OverfittingPBOResult
from backtesting.validation.walk_forward_artifacts import (
    build_walk_forward_evidence_document,
)
from backtesting.validation.walk_forward_artifacts.builder import _identity
from backtesting.walk_forward.overfitting import IdeaOverfitting
from tests.test_walk_forward_artifacts import (
    _evidence,
    _registered_document,
    _result,
    _rules,
    _service_with_walk_forward_run,
)

_DSR = DeflatedSharpeResult(
    trials=6,
    effective_trials=4.0,
    best_trial_index=1,
    best_sharpe=1.2,
    observations=200,
    probability=0.83,
    trial_probabilities=(0.5,) * 6,
)
_PBO = OverfittingPBOResult(probability=0.4, splits=70, trials=6, observations=200)
_LUCK = IdeaOverfitting(trials=6, deflated_sharpe=_DSR, overfitting_pbo=_PBO)


def _document(service, tmp_path: Path, overfitting) -> dict:
    result = replace(_result(tmp_path), overfitting=overfitting)
    return build_walk_forward_evidence_document(
        run_id="wf-run",
        source=_evidence(service).source_document("wf-run"),
        result=result,
        rules=_rules(),
    )


def test_idea_overfitting_is_persisted_and_round_trips(tmp_path: Path) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = _document(service, tmp_path, _LUCK)
        assert document["evidence"]["idea_overfitting"] == {
            "deflated_sharpe_probability": 0.83,
            "trial_count": 6,
            "pbo": 0.4,
            "pbo_split_count": 70,
        }
        _registered_document(service, run_id="wf-run", artifact_root=root, document=document)
        retrieved = _evidence(service).retrieve_walk_forward("wf-run", artifact_root=root)
        assert retrieved.document == document
    finally:
        service.close()


def test_missing_overfitting_records_nulls_and_does_not_change_status(tmp_path: Path) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    try:
        with_luck = _document(service, tmp_path, _LUCK)
        without = _document(service, tmp_path, None)
        assert set(without["evidence"]["idea_overfitting"].values()) == {None}
        assert (
            with_luck["evidence"]["normalized_evidence"]
            == without["evidence"]["normalized_evidence"]
        )
    finally:
        service.close()


def test_old_document_without_key_still_validates(tmp_path: Path) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = _document(service, tmp_path, None)
        del document["evidence"]["idea_overfitting"]
        document["artifact"]["evidence_identity"] = _identity(document["evidence"])
        _registered_document(service, run_id="wf-run", artifact_root=root, document=document)
        retrieved = _evidence(service).retrieve_walk_forward("wf-run", artifact_root=root)
        assert "idea_overfitting" not in retrieved.document["evidence"]
    finally:
        service.close()


def test_tampered_idea_overfitting_breaks_identity(tmp_path: Path) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = _document(service, tmp_path, _LUCK)
        document["evidence"]["idea_overfitting"]["pbo"] = 0.0
        _registered_document(service, run_id="wf-run", artifact_root=root, document=document)
        with pytest.raises(ValueError, match="identity mismatch"):
            _evidence(service).retrieve_walk_forward("wf-run", artifact_root=root)
    finally:
        service.close()
