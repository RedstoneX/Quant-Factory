from dataclasses import replace
import math

import pytest

from backtesting.robustness import (
    NeighborhoodConfig,
    ParameterNeighborhoodDefinition,
    RegimeConfig,
    RobustnessConfig,
    combine_statuses,
)


def neighborhood() -> NeighborhoodConfig:
    return NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "window", "explicit_values", explicit_values=(7, 14, 21)
            ),
        )
    )


def config() -> RobustnessConfig:
    return RobustnessConfig(
        strategy_id="rsi_mean_reversion",
        strategy_version="1.0.0",
        locked_parameters={"window": 14, "entry_threshold": 25, "exit_threshold": 55},
        experiment_id="experiment",
        source_artifact_id="artifact",
        source_start="2020-01-01",
        source_end="2024-01-01",
        data_provenance={"provider": "fixture"},
        execution_assumptions={"execution_mode": "next_bar_open"},
        neighborhood=neighborhood(),
        regimes=RegimeConfig(),
    )


@pytest.mark.parametrize("field", ["strategy_id", "strategy_version", "experiment_id", "source_artifact_id"])
def test_blank_identities_rejected(field):
    with pytest.raises(ValueError, match="blank"):
        replace(config(), **{field: " "})


@pytest.mark.parametrize(
    "start,end",
    [("bad", "2024-01-01"), ("2025-01-01", "2024-01-01")],
)
def test_invalid_source_dates_rejected(start, end):
    with pytest.raises(ValueError):
        replace(config(), source_start=start, source_end=end)


@pytest.mark.parametrize(
    "field,value",
    [
        ("maximum_drawdown", float("nan")),
        ("minimum_return", float("inf")),
        ("maximum_drawdown", True),
        ("maximum_drawdown", 1.1),
    ],
)
def test_invalid_robustness_thresholds_rejected(field, value):
    with pytest.raises((TypeError, ValueError)):
        replace(config(), **{field: value})


def test_malformed_provenance_and_assumptions_rejected():
    with pytest.raises(TypeError):
        replace(config(), data_provenance=[])
    with pytest.raises(TypeError):
        replace(config(), execution_assumptions=[])


@pytest.mark.parametrize("field,value", [("trend_window", 0), ("volatility_window", True), ("minimum_observations", -1)])
def test_invalid_regime_counts_rejected(field, value):
    with pytest.raises((TypeError, ValueError)):
        replace(RegimeConfig(), **{field: value})


@pytest.mark.parametrize("field,value", [("volatility_threshold", float("nan")), ("annualization_factor", 0), ("trend_neutral_tolerance", True)])
def test_invalid_regime_numeric_values_rejected(field, value):
    with pytest.raises((TypeError, ValueError)):
        replace(RegimeConfig(), **{field: value})


def test_conflicting_and_duplicate_neighborhood_methods_rejected():
    with pytest.raises(ValueError, match="exactly"):
        ParameterNeighborhoodDefinition(
            "window",
            "explicit_values",
            explicit_values=(14,),
            integer_offsets=(0,),
        )
    definition = ParameterNeighborhoodDefinition(
        "window", "integer_offsets", integer_offsets=(0,)
    )
    with pytest.raises(ValueError, match="duplicate"):
        NeighborhoodConfig(definitions=(definition, definition))


def test_boolean_integer_offset_and_nonfinite_percentage_rejected():
    with pytest.raises(TypeError):
        ParameterNeighborhoodDefinition(
            "window", "integer_offsets", integer_offsets=(False,)
        )
    with pytest.raises(ValueError):
        ParameterNeighborhoodDefinition(
            "x", "percentage_offsets", percentage_offsets=(float("inf"),)
        )


def test_combined_status_precedence_exact():
    assert combine_statuses(("passed", "invalid_input", "failed")) == "invalid_input"
    assert combine_statuses(("failed", "insufficient_evidence")) == "failed"
    assert combine_statuses(("passed", "insufficient_evidence")) == "insufficient_evidence"
    assert combine_statuses(("passed", "passed")) == "passed"
