"""Typed configuration and results for chronological out-of-sample tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.experiments.models import ExperimentConfig, ExperimentResult


@dataclass(frozen=True)
class ChronologicalSplitConfig:
    """Fractions and minimum sizes for contiguous chronological partitions."""

    train_fraction: float = 0.60
    selection_fraction: float = 0.20
    test_fraction: float = 0.20
    minimum_rows_per_partition: int = 30

    def __post_init__(self) -> None:
        fractions = (
            self.train_fraction,
            self.selection_fraction,
            self.test_fraction,
        )
        if any(value <= 0 or value >= 1 for value in fractions):
            raise ValueError("split fractions must be between zero and one")
        if abs(sum(fractions) - 1.0) > 1e-12:
            raise ValueError("split fractions must sum to one")
        if self.minimum_rows_per_partition < 1:
            raise ValueError("minimum_rows_per_partition must be positive")


@dataclass(frozen=True)
class DataPartition:
    name: str
    data: pd.DataFrame
    start: str
    end: str
    row_count: int


@dataclass(frozen=True)
class ChronologicalSplit:
    train: DataPartition
    selection: DataPartition
    test: DataPartition


@dataclass(frozen=True)
class ParameterLock:
    """Immutable evidence that selection completed before test evaluation."""

    lock_id: str
    experiment_id: str
    strategy_id: str
    strategy_version: str
    normalized_parameters: tuple[tuple[str, Any], ...]
    selection_parameter_row_id: str
    selection_start: str
    selection_end: str
    ranking_columns: tuple[str, ...]
    ranking_ascending: tuple[bool, ...]


@dataclass(frozen=True)
class OutOfSampleConfig:
    experiment: ExperimentConfig
    split: ChronologicalSplitConfig
    output_path: Path
    shortlist_size: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.shortlist_size, int) or isinstance(
            self.shortlist_size, bool
        ):
            raise TypeError("shortlist_size must be int")
        if self.shortlist_size < 1:
            raise ValueError("shortlist_size must be positive")


@dataclass(frozen=True)
class OutOfSampleResult:
    split: ChronologicalSplit
    training_result: ExperimentResult
    selection_result: ExperimentResult
    test_result: ExperimentResult
    parameter_lock: ParameterLock
    shortlist_parameters: tuple[dict[str, Any], ...]
    selected_parameters: dict[str, Any]
