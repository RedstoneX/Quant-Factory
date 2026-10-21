"""Candidate validation plan: fixed, serializable boundaries for the validation engines."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from backtesting.monte_carlo import MonteCarloConfig
from backtesting.out_of_sample import (
    ChronologicalSplitConfig,
)
from backtesting.robustness import (
    FixedRuleCostStressPlan,
    NeighborhoodConfig,
    RegimeConfig,
)
from backtesting.validation import WalkForwardWindowRules


@dataclass(frozen=True)
class CandidateValidationPlan:
    """Fixed, serializable boundaries for the existing validation engines."""

    out_of_sample_split: ChronologicalSplitConfig
    out_of_sample_shortlist_size: int
    walk_forward_rules: WalkForwardWindowRules
    walk_forward_shortlist_size: int
    robustness_neighborhood: NeighborhoodConfig | None
    robustness_regimes: RegimeConfig
    robustness_maximum_drawdown: float
    robustness_minimum_return: float
    robustness_minimum_sharpe: float | None
    monte_carlo: MonteCarloConfig
    data_as_of: str | None = None
    fixed_rule_cost_stress: FixedRuleCostStressPlan | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("out_of_sample_shortlist_size", self.out_of_sample_shortlist_size),
            ("walk_forward_shortlist_size", self.walk_forward_shortlist_size),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.data_as_of is not None:
            timestamp = pd.Timestamp(self.data_as_of)
            if timestamp.tzinfo is None:
                raise ValueError("data_as_of must include a timezone")
        if (self.robustness_neighborhood is None) != (self.fixed_rule_cost_stress is not None):
            raise ValueError("fixed-rule cost stress must replace, not accompany, parameter variation")

    def document(self) -> dict[str, Any]:
        return {
            "out_of_sample": {
                "split": asdict(self.out_of_sample_split),
                "shortlist_size": self.out_of_sample_shortlist_size,
            },
            "walk_forward": {
                "rules": asdict(self.walk_forward_rules),
                "shortlist_size": self.walk_forward_shortlist_size,
            },
            "robustness": {
                "neighborhood": asdict(self.robustness_neighborhood) if self.robustness_neighborhood is not None else None,
                "regimes": asdict(self.robustness_regimes),
                "maximum_drawdown": self.robustness_maximum_drawdown,
                "minimum_return": self.robustness_minimum_return,
                "minimum_sharpe": self.robustness_minimum_sharpe,
                **({"fixed_rule_cost_stress": asdict(self.fixed_rule_cost_stress)} if self.fixed_rule_cost_stress is not None else {}),
            },
            "monte_carlo": asdict(self.monte_carlo),
            "data_as_of": self.data_as_of,
            "protected_data_state": "gated",
        }
