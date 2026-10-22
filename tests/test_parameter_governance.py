"""Deterministic tests for parameter governance and grid summaries."""

from dataclasses import replace

import pytest

from strategies.models import ParameterDefinition
from strategies.parameter_governance import (
    PROVISIONAL_GRID_WARNING_THRESHOLD,
    summarize_parameter_plan,
    validate_parameter_definition,
    validate_parameter_plan,
)
from strategies.rsi_mean_reversion import RSI_MEAN_REVERSION_SPEC


def _definition(
    classification: str,
    *,
    optimized: bool = False,
    structural: bool = False,
    values: tuple[object, ...] | None = None,
    reference: object = 14,
) -> ParameterDefinition:
    return ParameterDefinition(
        name="example",
        value_type=type(reference),
        default=reference,
        description="Governance fixture.",
        optimizable=optimized,
        allowed_values=values,
        classification=classification,  # type: ignore[arg-type]
        reference_value=reference,
        source="approved fixture source",
        rationale="Exercise one governed parameter classification.",
        structural=structural,
        expected_grid_contribution=len(values or ()) if optimized else 1,
        approval_state="approved",
    )


@pytest.mark.parametrize(
    "definition",
    [
        _definition("fixed"),
        _definition("source_defined", optimized=True, values=(14,)),
        _definition("bounded_discrete", optimized=True, values=(7, 14, 21)),
        _definition("local_sensitivity", optimized=True, values=(12, 14, 16)),
        _definition(
            "structural_choice",
            structural=True,
            values=("rsi_recovery", "moving_average_exit"),
            reference="rsi_recovery",
        ),
    ],
)
def test_each_parameter_classification_accepts_valid_metadata(
    definition: ParameterDefinition,
) -> None:
    validate_parameter_definition(definition, require_approved=True)
    assert definition.optimized is definition.optimizable


def test_optimized_parameter_requires_rationale() -> None:
    definition = replace(
        _definition("local_sensitivity", optimized=True, values=(12, 14, 16)),
        rationale="",
    )
    with pytest.raises(ValueError, match="rationale is required"):
        validate_parameter_definition(definition)


def test_source_defined_and_local_sensitivity_require_source() -> None:
    definition = replace(
        _definition("source_defined", optimized=True, values=(14,)), source=""
    )
    with pytest.raises(ValueError, match="source is required"):
        validate_parameter_definition(definition)


def test_duplicate_candidates_are_rejected() -> None:
    definition = _definition(
        "local_sensitivity", optimized=True, values=(12, 14, 14)
    )
    with pytest.raises(ValueError, match="must be unique"):
        validate_parameter_definition(definition)


def test_reference_must_be_in_optimized_candidates() -> None:
    definition = _definition(
        "bounded_discrete", optimized=True, values=(7, 21)
    )
    with pytest.raises(ValueError, match="reference value must be included"):
        validate_parameter_definition(definition)


def test_empty_candidates_and_inconsistent_contribution_are_rejected() -> None:
    with pytest.raises(ValueError, match="requires candidate values"):
        validate_parameter_definition(
            _definition("bounded_discrete", optimized=True, values=None)
        )
    definition = replace(
        _definition("bounded_discrete", optimized=True, values=(7, 14, 21)),
        expected_grid_contribution=4,
    )
    with pytest.raises(ValueError, match="must equal candidate count"):
        validate_parameter_definition(definition)


def test_structural_choices_cannot_be_disguised_or_optimized() -> None:
    disguised = replace(
        _definition("local_sensitivity", optimized=True, values=(12, 14, 16)),
        structural=True,
    )
    with pytest.raises(ValueError, match="must use structural_choice"):
        validate_parameter_definition(disguised)

    structural = _definition(
        "structural_choice",
        optimized=True,
        structural=True,
        values=("rsi_recovery", "moving_average_exit"),
        reference="rsi_recovery",
    )
    with pytest.raises(ValueError, match="cannot enter an ordinary grid"):
        validate_parameter_definition(structural)


def test_invalid_classification_and_unapproved_plan_are_rejected() -> None:
    invalid = replace(_definition("fixed"), classification="invented")
    with pytest.raises(ValueError, match="invalid classification"):
        validate_parameter_definition(invalid)

    draft = replace(_definition("fixed"), approval_state="draft")
    with pytest.raises(ValueError, match="not approved for execution"):
        validate_parameter_definition(draft, require_approved=True)


def test_grid_summary_is_deterministic_and_warns_above_threshold() -> None:
    first = summarize_parameter_plan(
        RSI_MEAN_REVERSION_SPEC, warning_threshold=20, require_approved=True
    )
    second = summarize_parameter_plan(
        RSI_MEAN_REVERSION_SPEC, warning_threshold=20, require_approved=True
    )
    assert first == second
    assert first.total_combinations == 27
    assert [item.candidate_count for item in first.optimized_parameters] == [3, 3, 3]
    assert first.fixed_parameters == ()
    assert first.fixed_parameter_count == 0
    assert first.structural_choice_parameters == ()
    assert first.warnings == (
        "Grid has 27 combinations, exceeding the provisional warning threshold of 20.",
    )


def test_provisional_default_threshold_is_adjustable() -> None:
    summary = summarize_parameter_plan(RSI_MEAN_REVERSION_SPEC)
    assert summary.warning_threshold == PROVISIONAL_GRID_WARNING_THRESHOLD
    assert summary.warnings == ()
    with pytest.raises(ValueError, match="must be positive"):
        summarize_parameter_plan(RSI_MEAN_REVERSION_SPEC, warning_threshold=0)


def test_rsi_reference_and_approved_metadata_preserve_current_grid() -> None:
    validate_parameter_plan(RSI_MEAN_REVERSION_SPEC, require_approved=True)
    assert RSI_MEAN_REVERSION_SPEC.reference_configuration == {
        "window": 14,
        "entry_threshold": 30,
        "exit_threshold": 55,
    }
    assert all(
        definition.approval_state == "approved"
        for definition in RSI_MEAN_REVERSION_SPEC.parameters
    )
