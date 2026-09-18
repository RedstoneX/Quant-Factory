"""Leakage-resistant chronological data splitting."""

from __future__ import annotations

import pandas as pd

from backtesting.out_of_sample.models import (
    ChronologicalSplit,
    ChronologicalSplitConfig,
    DataPartition,
)


def _partition(name: str, data: pd.DataFrame) -> DataPartition:
    return DataPartition(
        name=name,
        data=data.copy(),
        start=str(data.index[0].date()),
        end=str(data.index[-1].date()),
        row_count=len(data),
    )


def split_chronologically(
    data: pd.DataFrame, config: ChronologicalSplitConfig
) -> ChronologicalSplit:
    """Return three non-overlapping, contiguous partitions in time order."""
    if data.empty:
        raise ValueError("cannot split empty market data")
    if not data.index.is_monotonic_increasing:
        raise ValueError("market data must be sorted in increasing time order")
    if not data.index.is_unique:
        raise ValueError("market data index must be unique")

    train_end = int(len(data) * config.train_fraction)
    selection_end = train_end + int(len(data) * config.selection_fraction)
    frames = (
        data.iloc[:train_end],
        data.iloc[train_end:selection_end],
        data.iloc[selection_end:],
    )
    names = ("train", "selection", "test")
    for name, frame in zip(names, frames, strict=True):
        if len(frame) < config.minimum_rows_per_partition:
            raise ValueError(
                f"{name} partition has {len(frame)} rows; requires at least "
                f"{config.minimum_rows_per_partition}"
            )

    split = ChronologicalSplit(
        train=_partition("train", frames[0]),
        selection=_partition("selection", frames[1]),
        test=_partition("test", frames[2]),
    )
    if not (split.train.end < split.selection.start < split.test.start):
        raise ValueError("chronological partitions overlap or are out of order")
    return split
