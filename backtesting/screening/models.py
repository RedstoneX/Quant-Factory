"""Typed configuration and results for cheap strategy screening."""

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Literal

RuleStatus = Literal["passed", "failed"]


@dataclass(frozen=True)
class ScreeningConfig:
    """Serializable provisional thresholds for early rejection only."""

    minimum_trades: int
    minimum_total_return: float
    minimum_annualized_return: float
    minimum_sharpe_ratio: float
    maximum_drawdown: float
    minimum_win_rate: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.minimum_trades, int) or isinstance(
            self.minimum_trades, bool
        ):
            raise TypeError("minimum_trades must be int")
        if self.minimum_trades < 0:
            raise ValueError("minimum_trades must be non-negative")
        numeric = {
            "minimum_total_return": self.minimum_total_return,
            "minimum_annualized_return": self.minimum_annualized_return,
            "minimum_sharpe_ratio": self.minimum_sharpe_ratio,
            "maximum_drawdown": self.maximum_drawdown,
        }
        if any(not math.isfinite(float(value)) for value in numeric.values()):
            raise ValueError("screening thresholds must be finite")
        if self.maximum_drawdown < 0:
            raise ValueError("maximum_drawdown must be non-negative")
        if self.minimum_win_rate is not None:
            if not math.isfinite(float(self.minimum_win_rate)):
                raise ValueError("minimum_win_rate must be finite")
            if not 0 <= self.minimum_win_rate <= 1:
                raise ValueError("minimum_win_rate must be between 0 and 1")

    @classmethod
    def provisional_defaults(cls) -> "ScreeningConfig":
        return cls(
            minimum_trades=20,
            minimum_total_return=0.0,
            minimum_annualized_return=0.0,
            minimum_sharpe_ratio=0.5,
            maximum_drawdown=0.35,
            minimum_win_rate=None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScreeningRuleResult:
    rule_id: str
    metric: str
    observed_value: Any
    threshold: Any
    status: RuleStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "passed"


@dataclass(frozen=True)
class ScreeningResult:
    parameter_row_id: str
    passed: bool
    rule_results: tuple[ScreeningRuleResult, ...]
    passed_rule_count: int
    failed_rule_count: int
    strategy_id: str
    strategy_version: str
    normalized_parameters: dict[str, Any]
    execution_assumptions: dict[str, Any]
    rejection_reasons: tuple[str, ...]
