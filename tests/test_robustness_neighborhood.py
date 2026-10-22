from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from backtesting.robustness import (
    NeighborhoodConfig,
    ParameterNeighborhoodDefinition,
    build_neighborhood,
)
from strategies import get_strategy
from strategies.models import ParameterDefinition


def explicit_config() -> NeighborhoodConfig:
    return NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "window", "explicit_values", explicit_values=(7, 14, 21)
            ),
            ParameterNeighborhoodDefinition(
                "entry_threshold", "explicit_values", explicit_values=(20, 25, 30)
            ),
            ParameterNeighborhoodDefinition(
                "exit_threshold", "explicit_values", explicit_values=(50, 55, 60)
            ),
        )
    )


LOCKED = {"window": 14, "entry_threshold": 25, "exit_threshold": 55}


def test_explicit_neighborhood_includes_lock_and_is_deterministic():
    strategy = get_strategy("rsi_mean_reversion")
    locked_before = dict(LOCKED)
    first = build_neighborhood(strategy, LOCKED, explicit_config())
    second = build_neighborhood(strategy, LOCKED, explicit_config())
    assert LOCKED == locked_before
    assert first == second
    assert any(candidate.is_locked_point for candidate in first.candidates)
    assert first.requested_candidate_count == 27
    assert first.accepted_count == 27


def test_integer_offsets_and_bounds_are_recorded_without_clamping():
    strategy = get_strategy("rsi_mean_reversion")
    config = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "window", "integer_offsets", integer_offsets=(-7, 0, 7, 100)
            ),
        )
    )
    result = build_neighborhood(strategy, LOCKED, config)
    assert [candidate.normalized_parameters["window"] for candidate in result.candidates] == [7, 14, 21]
    assert result.rejected_count == 1
    assert "one of" in result.rejected_derivations[0].rejection_reason


class FloatStrategy:
    spec = SimpleNamespace(
        parameter_map={
            "alpha": ParameterDefinition(
                name="alpha",
                value_type=float,
                default=1.0,
                description="fixture",
                optimizable=True,
                minimum=0.5,
                maximum=2.0,
            )
        }
    )

    def validate_parameters(self, parameters):
        value = parameters["alpha"]
        self.spec.parameter_map["alpha"].validate(value)
        return {"alpha": value}


def test_percentage_offsets_supported_for_continuous_parameters():
    config = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "alpha", "percentage_offsets", percentage_offsets=(-0.1, 0.0, 0.1)
            ),
        )
    )
    result = build_neighborhood(FloatStrategy(), {"alpha": 1.0}, config)
    assert [candidate.normalized_parameters["alpha"] for candidate in result.candidates] == pytest.approx([0.9, 1.0, 1.1])
    assert all(candidate.derivations[0].method == "percentage_offsets" for candidate in result.candidates)


def test_nonfinite_explicit_values_are_rejected_not_evaluated():
    config = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "alpha", "explicit_values", explicit_values=(1.0, float("nan"))
            ),
        )
    )
    result = build_neighborhood(FloatStrategy(), {"alpha": 1.0}, config)
    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert "finite" in result.rejected_derivations[0].rejection_reason


def test_percentage_offsets_reject_integer_parameters():
    config = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "window", "percentage_offsets", percentage_offsets=(0.0,)
            ),
        )
    )
    with pytest.raises(TypeError, match="integer parameter"):
        build_neighborhood(get_strategy("rsi_mean_reversion"), LOCKED, config)


def test_invalid_combinations_are_recorded():
    config = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "entry_threshold", "explicit_values", explicit_values=(25, 60)
            ),
            ParameterNeighborhoodDefinition(
                "exit_threshold", "explicit_values", explicit_values=(55, 60)
            ),
        )
    )
    result = build_neighborhood(get_strategy("rsi_mean_reversion"), LOCKED, config)
    assert result.rejected_count >= 1
    assert all(item.rejection_reason for item in result.rejected_derivations)


class PairStrategy:
    spec = SimpleNamespace(
        parameter_map={
            name: ParameterDefinition(
                name=name,
                value_type=int,
                default=default,
                description="fixture",
                optimizable=True,
                allowed_values=(1, 2),
            )
            for name, default in (("low", 1), ("high", 2))
        }
    )

    def validate_parameters(self, parameters):
        normalized = dict(parameters)
        for name, definition in self.spec.parameter_map.items():
            definition.validate(normalized[name])
        if normalized["low"] >= normalized["high"]:
            raise ValueError("low must be below high")
        return normalized


def test_cross_parameter_invalid_combinations_are_recorded():
    config = NeighborhoodConfig(
        definitions=tuple(
            ParameterNeighborhoodDefinition(
                name, "explicit_values", explicit_values=(1, 2)
            )
            for name in ("low", "high")
        )
    )
    result = build_neighborhood(PairStrategy(), {"low": 1, "high": 2}, config)
    assert any(
        item.parameter_name == "__combination__"
        and "low must be below high" in item.rejection_reason
        for item in result.rejected_derivations
    )


def test_duplicate_normalization_is_recorded():
    config = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "window", "explicit_values", explicit_values=(14, 14)
            ),
        )
    )
    result = build_neighborhood(get_strategy("rsi_mean_reversion"), LOCKED, config)
    assert result.duplicate_count == 1
    assert result.accepted_count == 1


def test_locked_value_must_be_declared_and_unknown_names_rejected():
    missing_lock = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "window", "explicit_values", explicit_values=(7, 21)
            ),
        )
    )
    with pytest.raises(ValueError, match="include locked"):
        build_neighborhood(get_strategy("rsi_mean_reversion"), LOCKED, missing_lock)
    unknown = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "unknown", "explicit_values", explicit_values=(1,)
            ),
        )
    )
    with pytest.raises(ValueError, match="unsupported"):
        build_neighborhood(get_strategy("rsi_mean_reversion"), LOCKED, unknown)
