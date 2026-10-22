"""Parity: VectorBT PRO ``Splitter`` reproduces Quant Factory's split boundaries.

Each test builds the library splitter that would replace the home-made one and
asserts the integer row boundaries are identical on the same fixture.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backtesting.out_of_sample import ChronologicalSplitConfig, split_chronologically
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.vectorbt_runtime import require_vectorbtpro
from backtesting.walk_forward import WalkForwardConfig, build_walk_forward_windows


def _frame(rows: int) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame({"close": range(rows)}, index=index)


def _bounds(data: pd.DataFrame, partition) -> list[int]:
    start = data.index.get_loc(partition.data.index[0])
    return [start, start + partition.row_count]


def _library_bounds(splitter) -> list[list[list[int]]]:
    return splitter.get_bounds_arr(index_bounds=False).tolist()


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize("rows", [100, 157, 251, 1000])
@pytest.mark.parametrize(
    ("train", "selection"), [(0.60, 0.20), (0.50, 0.25), (0.70, 0.15), (0.34, 0.33)]
)
def test_chronological_split_matches_library(rows, train, selection):
    vbt = require_vectorbtpro()
    data = _frame(rows)
    config = ChronologicalSplitConfig(
        train_fraction=train,
        selection_fraction=selection,
        test_fraction=round(1.0 - train - selection, 10),
        minimum_rows_per_partition=10,
    )
    split = split_chronologically(data, config)
    splitter = vbt.Splitter.from_single(
        data.index,
        split=(
            vbt.RelRange(length=train, length_space="all"),
            vbt.RelRange(length=selection, length_space="all"),
            vbt.RelRange(length=1.0),
        ),
    )
    ours = [_bounds(data, getattr(split, name)) for name in ("train", "selection", "test")]
    assert _library_bounds(splitter) == [ours]


def _walk_forward(
    rows: int, train: int, selection: int, test: int, step: int, mode: str, policy: str
):
    vbt = require_vectorbtpro()
    data = _frame(rows)
    config = WalkForwardConfig(
        experiment=EXPERIMENT_CONFIG,
        training_window_size=train,
        selection_window_size=selection or None,
        test_window_size=test,
        step_size=step,
        training_mode=mode,
        minimum_rows_per_window=2,
        shortlist_size=1,
        incomplete_final_window=policy,
        output_path=Path("unused.json"),
    )
    ours = [
        [_bounds(data, part) for part in (w.train, w.selection, w.test) if part is not None]
        for w in build_walk_forward_windows(data, config)
    ]
    lengths = (selection, test) if selection else (test,)
    if mode == "rolling":
        splitter = vbt.Splitter.from_rolling(
            data.index,
            length=train + sum(lengths),
            offset=step,
            offset_anchor="prev_start",
            split=(train, *lengths),
        )
    else:
        splitter = vbt.Splitter.from_expanding(
            data.index,
            min_length=train + sum(lengths),
            offset=step,
            split=(1.0, *lengths),
            split_range_kwargs={"backwards": True},
        )
    return ours, _library_bounds(splitter)


WALK_FORWARD_CASES = [
    (40, 10, 0, 5, 5),
    (40, 10, 5, 5, 5),
    (40, 10, 5, 5, 7),
    (97, 20, 0, 7, 7),
    (97, 20, 10, 10, 13),
    (500, 120, 30, 25, 25),
]


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize("mode", ["rolling", "expanding"])
@pytest.mark.parametrize(("rows", "train", "selection", "test", "step"), WALK_FORWARD_CASES)
def test_walk_forward_drop_matches_library(rows, train, selection, test, step, mode):
    ours, library = _walk_forward(rows, train, selection, test, step, mode, "drop")
    assert ours and ours == library


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize("mode", ["rolling", "expanding"])
@pytest.mark.parametrize(("rows", "train", "selection", "test", "step"), WALK_FORWARD_CASES)
def test_walk_forward_include_extends_library_with_truncated_tail(
    rows, train, selection, test, step, mode
):
    """The library stops at the last complete window; "include" adds only shorter tails."""
    ours, library = _walk_forward(rows, train, selection, test, step, mode, "include")
    assert ours[: len(library)] == library
    for fold in ours[len(library):]:
        assert fold[-1][1] == rows
        assert fold[-1][1] - fold[-1][0] < test
