"""Validation and summaries for approved strategy parameter plans."""

from dataclasses import dataclass
from math import prod

from strategies.models import ParameterDefinition, StrategySpecification

PARAMETER_CLASSIFICATIONS = frozenset(
    {
        "fixed",
        "source_defined",
        "bounded_discrete",
        "local_sensitivity",
        "structural_choice",
    }
)
APPROVAL_STATES = frozenset({"draft", "approved", "rejected"})
PROVISIONAL_GRID_WARNING_THRESHOLD = 100


@dataclass(frozen=True)
class ParameterGridContribution:
    name: str
    classification: str
    candidate_count: int


@dataclass(frozen=True)
class ParameterPlanSummary:
    optimized_parameters: tuple[ParameterGridContribution, ...]
    total_combinations: int
    fixed_parameters: tuple[str, ...]
    fixed_parameter_count: int
    structural_choice_parameters: tuple[str, ...]
    warning_threshold: int
    warnings: tuple[str, ...]


def validate_parameter_definition(
    definition: ParameterDefinition, *, require_approved: bool = False
) -> None:
    """Reject parameter metadata that violates governance policy."""
    if definition.classification not in PARAMETER_CLASSIFICATIONS:
        raise ValueError(
            f"{definition.name}: invalid classification "
            f"{definition.classification!r}"
        )
    if not definition.name.strip():
        raise ValueError("Parameter name is required")
    if definition.approval_state not in APPROVAL_STATES:
        raise ValueError(
            f"{definition.name}: invalid approval state "
            f"{definition.approval_state!r}"
        )
    if not definition.source.strip():
        raise ValueError(f"{definition.name}: source is required")
    if not definition.rationale.strip():
        raise ValueError(f"{definition.name}: rationale is required")
    if definition.reference_value != definition.default:
        raise ValueError(
            f"{definition.name}: default must equal the reference value"
        )
    if require_approved and definition.approval_state != "approved":
        raise ValueError(
            f"{definition.name}: parameter plan is not approved for execution"
        )

    candidates = definition.candidate_values
    if definition.optimizable:
        if not candidates:
            raise ValueError(
                f"{definition.name}: optimized parameter requires candidate values"
            )
        if len(candidates) != len(set(candidates)):
            raise ValueError(f"{definition.name}: candidate values must be unique")
        if definition.reference_value not in candidates:
            raise ValueError(
                f"{definition.name}: reference value must be included in candidate values"
            )
        if definition.expected_grid_contribution != len(candidates):
            raise ValueError(
                f"{definition.name}: expected grid contribution must equal "
                "candidate count"
            )
    elif definition.expected_grid_contribution not in {None, 1}:
        raise ValueError(
            f"{definition.name}: non-optimized parameter grid contribution must be 1"
        )

    if definition.classification == "fixed" and definition.optimizable:
        raise ValueError(f"{definition.name}: fixed parameter cannot be optimized")
    if definition.classification == "structural_choice":
        if not definition.structural:
            raise ValueError(
                f"{definition.name}: structural choice must be marked structural"
            )
        if definition.optimizable:
            raise ValueError(
                f"{definition.name}: structural choice cannot enter an ordinary grid"
            )
    elif definition.structural:
        raise ValueError(
            f"{definition.name}: structural parameter must use structural_choice"
        )


def validate_parameter_plan(
    specification: StrategySpecification, *, require_approved: bool = False
) -> None:
    """Validate strategy-level approval and every parameter definition."""
    if not specification.hypothesis.strip():
        raise ValueError("Strategy hypothesis is required")
    if not specification.source.strip():
        raise ValueError("Strategy source is required")
    if specification.approval_state not in APPROVAL_STATES:
        raise ValueError(
            f"Invalid strategy approval state: {specification.approval_state!r}"
        )
    if require_approved and specification.approval_state != "approved":
        raise ValueError("Strategy parameter plan is not approved for execution")
    names = [definition.name for definition in specification.parameters]
    if len(names) != len(set(names)):
        raise ValueError("Parameter names must be unique")
    for definition in specification.parameters:
        validate_parameter_definition(
            definition, require_approved=require_approved
        )


def summarize_parameter_plan(
    specification: StrategySpecification,
    *,
    warning_threshold: int = PROVISIONAL_GRID_WARNING_THRESHOLD,
    require_approved: bool = False,
) -> ParameterPlanSummary:
    """Validate and summarize a plan without running a backtest."""
    if warning_threshold < 1:
        raise ValueError("warning_threshold must be positive")
    validate_parameter_plan(specification, require_approved=require_approved)
    contributions = tuple(
        ParameterGridContribution(
            name=definition.name,
            classification=definition.classification,
            candidate_count=len(definition.candidate_values),
        )
        for definition in specification.parameters
        if definition.optimizable
    )
    total = prod(item.candidate_count for item in contributions)
    structural = tuple(
        definition.name
        for definition in specification.parameters
        if definition.classification == "structural_choice"
    )
    warnings: list[str] = []
    if total > warning_threshold:
        warnings.append(
            f"Grid has {total} combinations, exceeding the provisional "
            f"warning threshold of {warning_threshold}."
        )
    if structural:
        warnings.append(
            "Structural choices are excluded from the ordinary parameter grid: "
            + ", ".join(structural)
        )
    return ParameterPlanSummary(
        optimized_parameters=contributions,
        total_combinations=total,
        fixed_parameters=tuple(
            definition.name
            for definition in specification.parameters
            if definition.classification == "fixed"
        ),
        fixed_parameter_count=sum(
            definition.classification == "fixed"
            for definition in specification.parameters
        ),
        structural_choice_parameters=structural,
        warning_threshold=warning_threshold,
        warnings=tuple(warnings),
    )
