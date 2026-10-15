"""Deterministic chronological window construction for walk-forward folds."""

from __future__ import annotations

import pandas as pd

from backtesting.out_of_sample.models import DataPartition
from backtesting.walk_forward.models import WalkForwardConfig, WalkForwardWindow


def _partition(name: str, data: pd.DataFrame) -> DataPartition:
    return DataPartition(
        name=name,
        data=data.copy(),
        start=str(data.index[0].date()),
        end=str(data.index[-1].date()),
        row_count=len(data),
    )


def _day_start(dates: pd.Index, position: int) -> int:
    """First row at or after ``position`` that opens a new day, so no day straddles two partitions."""
    if position <= 0 or position >= len(dates):
        return position
    return int(dates.searchsorted(dates[position - 1], side="right"))


def build_walk_forward_windows(
    data: pd.DataFrame,
    config: WalkForwardConfig,
) -> tuple[WalkForwardWindow, ...]:
    """Build ordered folds without shuffling or within-fold overlap."""
    if data.empty:
        raise ValueError("cannot build walk-forward windows from empty data")
    if not data.index.is_monotonic_increasing:
        raise ValueError("market data must be sorted in increasing time order")
    if not data.index.is_unique:
        raise ValueError("market data index must be unique")

    selection_size = config.selection_window_size or 0
    # Partitions are labelled by date, so intraday cuts are moved to the next day's first row.
    dates = data.index.normalize()
    raw_cursor = config.training_window_size
    windows: list[WalkForwardWindow] = []
    fold_number = 1
    while _day_start(dates, raw_cursor) + selection_size < len(data):
        cursor = _day_start(dates, raw_cursor)
        selection_end = _day_start(dates, cursor + selection_size)
        requested_test_end = selection_end + config.test_window_size
        if requested_test_end > len(data):
            if config.incomplete_final_window == "drop":
                break
            test_end = len(data)
            if test_end - selection_end < config.minimum_rows_per_window:
                break
        else:
            test_end = _day_start(dates, requested_test_end)

        train_start = (
            0 if config.training_mode == "expanding" else _day_start(dates, raw_cursor - config.training_window_size)
        )
        fold_id = f"fold_{fold_number:03d}"
        train = _partition(f"{fold_id}:train", data.iloc[train_start:cursor])
        selection = (
            _partition(
                f"{fold_id}:selection",
                data.iloc[cursor:selection_end],
            )
            if selection_size
            else None
        )
        test = _partition(f"{fold_id}:test", data.iloc[selection_end:test_end])
        if selection is not None:
            ordered = train.end < selection.start < test.start
        else:
            ordered = train.end < test.start
        if not ordered:
            raise ValueError(f"{fold_id} partitions overlap or are out of order")
        windows.append(
            WalkForwardWindow(
                fold_id=fold_id,
                train=train,
                selection=selection,
                test=test,
            )
        )
        fold_number += 1
        raw_cursor += config.step_size
    return tuple(windows)
