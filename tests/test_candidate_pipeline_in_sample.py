"""The real candidate pipeline screens only data before the unseen test slice."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backtesting.out_of_sample import split_chronologically
from market_data import load_market_data
from orchestration.candidate_data_window import session_closed_data_end
from orchestration.candidate_screening_artifacts import SCREENING_PRICE_REFERENCE
from tests.test_candidate_pipeline_runtime import _runtime


@pytest.mark.licensed_vectorbt
def test_persisted_screening_evidence_ends_before_unseen_test_start(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    outcome = runtime.launch(idempotency_key="screening_in_sample_only")
    assert outcome.chain.status == "ready_for_protected_test", outcome.chain

    run_id = outcome.launch.claim.run.run_id
    reference = json.loads(
        (runtime.artifact_root / "state" / "artifacts" / run_id / f"{SCREENING_PRICE_REFERENCE}.json").read_text()
    )
    market = runtime.definition.experiment.market_data
    full = load_market_data(
        market,
        now=session_closed_data_end(market, runtime.definition.validation.data_as_of),
        allow_download=False,
    ).data
    split = split_chronologically(full, runtime.definition.validation.out_of_sample_split)

    screened_end = pd.Timestamp(reference["end"])
    assert screened_end < split.test.data.index[0]
    assert screened_end == split.selection.data.index[-1]
    assert reference["row_count"] == split.train.row_count + split.selection.row_count
    assert reference["row_count"] < len(full)
