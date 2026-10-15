"""Deterministic chronological window construction for walk-forward folds."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtesting.out_of_sample.models import DataPartition
from backtesting.walk_forward.models import WalkForwardConfig, WalkForwardWindow
from backtesting.walk_forward.sessions import SessionGrid, alignment_for, boundary_label


def _partition(name: str, data: pd.DataFrame, aligned: bool) -> DataPartition:
    return DataPartition(
        name=name,
        data=data.copy(),
        start=boundary_label(data.index[0], aligned),
        end=boundary_label(data.index[-1], aligned),
        row_count=len(data),
    )


def _day_start(dates, position: int) -> int:
    """First row at or after ``position`` that opens a new session, so none straddles two partitions."""
    if position <= 0 or position >= len(dates):
        return position
    return int(np.searchsorted(dates, dates[position - 1], side="right"))


def _session_floor(dates, position: int) -> int:
    """First row of the session containing ``position``, so a rolling train window keeps its rows."""
    return int(np.searchsorted(dates, dates[position], side="left"))


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
    # Intraday cuts move to the first bar of the next exchange session; daily rows keep date cuts.
    alignment = alignment_for(data, config.experiment.market_data)
    aligned = alignment is not None
    if aligned:
        dates = SessionGrid(alignment, data.index[0], data.index[-1]).session_of(data.index)
    else:
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
            0 if config.training_mode == "expanding" else _session_floor(dates, cursor - config.training_window_size)
        )
        fold_id = f"fold_{fold_number:03d}"
        train = _partition(f"{fold_id}:train", data.iloc[train_start:cursor], aligned)
        selection = (
            _partition(
                f"{fold_id}:selection",
                data.iloc[cursor:selection_end],
                aligned,
            )
            if selection_size
            else None
        )
        test = _partition(f"{fold_id}:test", data.iloc[selection_end:test_end], aligned)
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
                session_calendar=alignment["exchange_calendar"] if aligned else None,
                session_interval=alignment["interval"] if aligned else None,
            )
        )
        fold_number += 1
        # Next train end: one step on, and never so early that the next test overlaps this one.
        raw_cursor = max(cursor + config.step_size, test_end - selection_size)
    return tuple(windows)
