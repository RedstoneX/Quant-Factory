"""An undefined luck score (1-setting grid) is recorded as null; evidence persistence still succeeds."""

from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path

import pytest

pytestmark = pytest.mark.licensed_vectorbt

from backtesting.validation.walk_forward_artifacts import (  # noqa: E402
    build_walk_forward_evidence_document,
)
from backtesting.walk_forward.overfitting import IdeaOverfitting  # noqa: E402
from persistence.serialization import canonical_json  # noqa: E402
import pandas as pd  # noqa: E402

from backtesting.experiments import execute_experiment  # noqa: E402
from tests.test_deflated_sharpe import COMBINATIONS, _audit, _config, _run  # noqa: E402
from tests.test_walk_forward_artifacts import (  # noqa: E402
    _evidence,
    _registered_document,
    _result,
    _rules,
    _service_with_walk_forward_run,
)


def test_single_setting_grid_records_null_luck_and_persists(tmp_path: Path) -> None:
    # Real VectorBT PRO engine, one setting: the library cannot deflate a single trial.
    recorded = _run(replace(_config(tmp_path), parameter_combinations=COMBINATIONS[:1]))
    luck = recorded.deflated_sharpe
    assert luck is not None and luck.trials == 1
    assert math.isnan(luck.probability)

    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        result = replace(
            _result(tmp_path),
            overfitting=IdeaOverfitting(trials=1, deflated_sharpe=luck, overfitting_pbo=None),
        )
        document = build_walk_forward_evidence_document(
            run_id="wf-run",
            source=_evidence(service).source_document("wf-run"),
            result=result,
            rules=_rules(),
        )
        assert document["evidence"]["idea_overfitting"]["deflated_sharpe_probability"] is None
        assert document["evidence"]["idea_overfitting"]["trial_count"] == 1
        # The NaN guard in canonical JSON stays; the record carries null instead.
        canonical_json(document)
        _registered_document(service, run_id="wf-run", artifact_root=root, document=document)
        retrieved = _evidence(service).retrieve_walk_forward("wf-run", artifact_root=root)
        assert retrieved.document == document
    finally:
        service.close()


def test_single_session_dataset_records_undefined_luck_without_failing(tmp_path: Path) -> None:
    # Real VectorBT PRO engine, one trading session of minute bars: one daily value per
    # setting gives no daily return rows, so the luck score is undefined, not a crash.
    index = pd.date_range("2024-01-02 09:30", periods=390, freq="min", tz="America/New_York")
    close = [100 + ((i % 13) - 6) * 0.2 + i * 0.001 for i in range(len(index))]
    data = pd.DataFrame(
        {
            "Open": [value - 0.1 for value in close],
            "High": [value + 0.2 for value in close],
            "Low": [value - 0.2 for value in close],
            "Close": close,
            "Volume": [1_000.0] * len(index),
        },
        index=index,
    )
    recorded = execute_experiment(
        _config(tmp_path), data, _audit(data), write_output=False, run_timestamp="fixed"
    )
    luck = recorded.deflated_sharpe
    assert luck is not None and luck.trials == len(recorded.normalized_parameters) >= 2
    assert luck.observations == 1 and luck.returns_basis == "daily"
    assert math.isnan(luck.probability)
    assert recorded.overfitting_pbo is None
    assert all(math.isnan(r.deflated_sharpe_probability) for r in recorded.screening_results)
