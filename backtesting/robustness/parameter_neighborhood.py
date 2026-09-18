"""Performance-blind construction of bounded parameter neighborhoods."""

from __future__ import annotations

from itertools import product
import math
from typing import Any

from backtesting.robustness.models import (
    CandidateDerivation,
    NeighborhoodCandidate,
    NeighborhoodConfig,
    NeighborhoodConstructionResult,
    ParameterNeighborhoodDefinition,
)


def _derive_values(
    definition: ParameterNeighborhoodDefinition,
    parameter_definition: Any,
    locked_value: Any,
) -> tuple[tuple[Any, CandidateDerivation], ...]:
    """Derive raw values without consulting any performance evidence."""
    derived: list[tuple[Any, CandidateDerivation]] = []
    if definition.method == "explicit_values":
        sources = definition.explicit_values
        raw_values = definition.explicit_values
    elif definition.method == "integer_offsets":
        if parameter_definition.value_type is not int:
            raise TypeError(
                f"integer offsets require integer parameter {definition.parameter_name}"
            )
        sources = definition.integer_offsets
        raw_values = tuple(locked_value + offset for offset in sources)
    else:
        if parameter_definition.value_type not in {float, int}:
            raise TypeError(
                f"percentage offsets require numeric parameter {definition.parameter_name}"
            )
        if parameter_definition.value_type is int:
            raise TypeError(
                f"percentage offsets are not supported for integer parameter {definition.parameter_name}"
            )
        sources = definition.percentage_offsets
        raw_values = tuple(locked_value * (1.0 + offset) for offset in sources)

    for source, raw_value in zip(sources, raw_values, strict=True):
        try:
            if (
                isinstance(raw_value, (int, float))
                and not isinstance(raw_value, bool)
                and not math.isfinite(float(raw_value))
            ):
                raise ValueError(
                    f"{definition.parameter_name} candidate must be finite"
                )
            parameter_definition.validate(raw_value)
        except (TypeError, ValueError) as exc:
            derivation = CandidateDerivation(
                parameter_name=definition.parameter_name,
                locked_value=locked_value,
                method=definition.method,
                source_value=source,
                raw_value=raw_value,
                normalized_value=None,
                status="rejected",
                rejection_reason=str(exc),
            )
        else:
            derivation = CandidateDerivation(
                parameter_name=definition.parameter_name,
                locked_value=locked_value,
                method=definition.method,
                source_value=source,
                raw_value=raw_value,
                normalized_value=raw_value,
                status="accepted",
            )
        derived.append((raw_value, derivation))
    return tuple(derived)


def build_neighborhood(
    strategy: Any,
    locked_parameters: dict[str, Any],
    config: NeighborhoodConfig,
) -> NeighborhoodConstructionResult:
    """Build a deterministic neighborhood using strategy metadata only."""
    locked_snapshot = dict(locked_parameters)
    for name, value in locked_snapshot.items():
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and not math.isfinite(float(value))
        ):
            raise ValueError(f"locked parameter {name} must be finite")
    normalized_locked = strategy.validate_parameters(locked_snapshot)
    if normalized_locked != locked_snapshot:
        raise ValueError("locked parameters must already be normalized")

    parameter_map = strategy.spec.parameter_map
    definition_map = {item.parameter_name: item for item in config.definitions}
    unsupported = set(definition_map) - set(parameter_map)
    if unsupported:
        raise ValueError(f"unsupported neighborhood parameters: {sorted(unsupported)}")

    choices: list[tuple[tuple[Any, CandidateDerivation], ...]] = []
    requested_dimension_counts: list[int] = []
    rejected_derivations: list[CandidateDerivation] = []
    raw_derived_count = 0
    for name, parameter_definition in parameter_map.items():
        if name in definition_map:
            values = _derive_values(
                definition_map[name], parameter_definition, normalized_locked[name]
            )
            accepted = tuple(item for item in values if item[1].status == "accepted")
            rejected_derivations.extend(
                item[1] for item in values if item[1].status == "rejected"
            )
            raw_derived_count += len(values)
            requested_dimension_counts.append(len(values))
            if not any(value == normalized_locked[name] for value, _ in accepted):
                raise ValueError(f"neighborhood for {name} must include locked value")
            choices.append(accepted)
        else:
            derivation = CandidateDerivation(
                parameter_name=name,
                locked_value=normalized_locked[name],
                method="locked",
                source_value=normalized_locked[name],
                raw_value=normalized_locked[name],
                normalized_value=normalized_locked[name],
                status="accepted",
            )
            choices.append(((normalized_locked[name], derivation),))
            raw_derived_count += 1
            requested_dimension_counts.append(1)

    if any(not values for values in choices):
        raise ValueError("neighborhood derived no valid values")

    parameter_names = tuple(parameter_map)
    requested_count = 1
    for count in requested_dimension_counts:
        requested_count *= count

    candidates: list[NeighborhoodCandidate] = []
    seen: set[tuple[tuple[str, Any], ...]] = set()
    duplicate_count = 0
    combination_rejections: list[CandidateDerivation] = []
    for combination in product(*choices):
        candidate = {
            name: value_and_derivation[0]
            for name, value_and_derivation in zip(
                parameter_names, combination, strict=True
            )
        }
        derivations = tuple(item[1] for item in combination)
        try:
            normalized = strategy.validate_parameters(candidate)
        except (TypeError, ValueError) as exc:
            combination_rejections.append(
                CandidateDerivation(
                    parameter_name="__combination__",
                    locked_value=dict(normalized_locked),
                    method="strategy_validation",
                    source_value=dict(candidate),
                    raw_value=dict(candidate),
                    normalized_value=None,
                    status="rejected",
                    rejection_reason=str(exc),
                )
            )
            continue
        key = tuple(sorted(normalized.items()))
        if key in seen:
            duplicate_count += 1
            combination_rejections.append(
                CandidateDerivation(
                    parameter_name="__combination__",
                    locked_value=dict(normalized_locked),
                    method="normalization",
                    source_value=dict(candidate),
                    raw_value=dict(candidate),
                    normalized_value=dict(normalized),
                    status="duplicate",
                    rejection_reason="normalized candidate duplicates an earlier candidate",
                    normalization_created_duplicate=True,
                )
            )
            continue
        seen.add(key)
        candidates.append(
            NeighborhoodCandidate(
                normalized_parameters=dict(normalized),
                derivations=derivations,
                is_locked_point=normalized == normalized_locked,
            )
        )

    candidates.sort(
        key=lambda item: tuple(
            item.normalized_parameters[name] for name in parameter_names
        )
    )
    if not any(candidate.is_locked_point for candidate in candidates):
        raise ValueError("valid neighborhood does not contain locked point")
    if not candidates:
        raise ValueError("neighborhood contains no valid candidates")

    all_rejections = tuple(rejected_derivations + combination_rejections)
    return NeighborhoodConstructionResult(
        requested_candidate_count=requested_count,
        raw_derived_count=raw_derived_count,
        unique_normalized_count=len(candidates),
        accepted_count=len(candidates),
        rejected_count=sum(item.status == "rejected" for item in all_rejections),
        duplicate_count=duplicate_count,
        candidates=tuple(candidates),
        rejected_derivations=all_rejections,
    )
