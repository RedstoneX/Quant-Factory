"""Typed models for deterministic rolling walk-forward evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from backtesting.experiments.models import ExperimentConfig, ExperimentResult
from backtesting.out_of_sample.models import DataPartition, ParameterLock

TrainingMode = Literal["rolling", "expanding"]
IncompleteWindowPolicy = Literal["drop", "include"]


@dataclass(frozen=True)
class WalkForwardConfig:
    experiment: ExperimentConfig
    training_window_size: int
    selection_window_size: int | None
    test_window_size: int
    step_size: int
    training_mode: TrainingMode
    minimum_rows_per_window: int
    shortlist_size: int
    incomplete_final_window: IncompleteWindowPolicy
    output_path: Path

    def __post_init__(self) -> None:
        integer_fields = {
            "training_window_size": self.training_window_size,
            "test_window_size": self.test_window_size,
            "step_size": self.step_size,
            "minimum_rows_per_window": self.minimum_rows_per_window,
            "shortlist_size": self.shortlist_size,
        }
        if self.selection_window_size is not None:
            integer_fields["selection_window_size"] = self.selection_window_size
        for name, value in integer_fields.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be int")
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if self.training_mode not in {"rolling", "expanding"}:
            raise ValueError(f"unsupported training_mode: {self.training_mode}")
        if self.incomplete_final_window not in {"drop", "include"}:
            raise ValueError(
                "incomplete_final_window must be 'drop' or 'include'"
            )
        if self.training_window_size < self.minimum_rows_per_window:
            raise ValueError("training_window_size is below the minimum")
        if self.test_window_size < self.minimum_rows_per_window:
            raise ValueError("test_window_size is below the minimum")
        if (
            self.selection_window_size is not None
            and self.selection_window_size < self.minimum_rows_per_window
        ):
            raise ValueError("selection_window_size is below the minimum")
        if self.step_size < self.test_window_size:
            raise ValueError(
                "step_size must be at least test_window_size to avoid overlapping tests"
            )

    @classmethod
    def rolling_default(
        cls,
        *,
        experiment: ExperimentConfig,
        output_path: Path,
    ) -> "WalkForwardConfig":
        return cls(
            experiment=experiment,
            training_window_size=756,
            selection_window_size=252,
            test_window_size=126,
            step_size=126,
            training_mode="rolling",
            minimum_rows_per_window=30,
            shortlist_size=5,
            incomplete_final_window="drop",
            output_path=output_path,
        )


@dataclass(frozen=True)
class WalkForwardWindow:
    fold_id: str
    train: DataPartition
    selection: DataPartition | None
    test: DataPartition


@dataclass(frozen=True)
class WalkForwardFoldResult:
    fold_id: str
    status: Literal["successful", "failed"]
    window: WalkForwardWindow
    training_result: ExperimentResult | None
    selection_result: ExperimentResult | None
    test_result: ExperimentResult | None
    shortlist_parameters: tuple[dict[str, Any], ...]
    parameter_lock: ParameterLock | None
    selected_parameters: dict[str, Any] | None
    test_metrics: dict[str, float | int]
    failure_reason: str | None


@dataclass(frozen=True)
class ParameterFrequency:
    normalized_parameters: tuple[tuple[str, Any], ...]
    fold_count: int
    fold_percentage: float


@dataclass(frozen=True)
class WalkForwardResult:
    folds: tuple[WalkForwardFoldResult, ...]
    total_fold_count: int
    successful_fold_count: int
    failed_fold_count: int
    selected_parameters_by_fold: tuple[tuple[str, dict[str, Any]], ...]
    unique_parameter_set_count: int
    parameter_frequencies: tuple[ParameterFrequency, ...]
    parameter_change_percentage: float
    maximum_consecutive_persistence: int
    failed_fold_ids: tuple[str, ...]
    failure_reasons: tuple[tuple[str, str], ...]
    fold_test_metrics: pd.DataFrame
    average_fold_metrics: dict[str, float]
    median_fold_metrics: dict[str, float]
    out_of_sample_returns: pd.Series
    out_of_sample_equity: pd.Series
    compounded_return: float | None
    endpoint_max_drawdown: float | None
    fold_return_sharpe: float | None
    total_trades: int
