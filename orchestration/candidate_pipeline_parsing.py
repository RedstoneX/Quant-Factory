"""Strict parsing of persisted Candidate configuration and robustness bounds."""

from __future__ import annotations

from typing import Any

from backtesting.robustness import FixedRuleCostStressPlan, NeighborhoodConfig, ParameterNeighborhoodDefinition, RegimeConfig

VALIDATION_RUNTIME_KEY = "candidate_validation_runtime"

def _strict_object(
    value: Any,
    *,
    path: str,
    keys: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    actual = set(value)
    missing = sorted(keys - actual)
    extra = sorted(actual - keys)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {missing}")
        if extra:
            details.append(f"unexpected {extra}")
        raise ValueError(f"{path} has invalid fields: {', '.join(details)}")
    return value


def _strict_list(value: Any, *, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _strict_text(value: Any, *, path: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be text")
    return value


def _strict_bool(value: Any, *, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _strict_int(value: Any, *, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{path} must be an integer")
    return value


def _strict_number(value: Any, *, path: str) -> float | int:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be numeric")
    return value


def _optional_number(value: Any, *, path: str) -> float | int | None:
    return None if value is None else _strict_number(value, path=path)


def _optional_int(value: Any, *, path: str) -> int | None:
    return None if value is None else _strict_int(value, path=path)


def _optional_text(value: Any, *, path: str) -> str | None:
    return None if value is None else _strict_text(value, path=path)


def parse_robustness_contract(robustness_document: dict[str, Any], installed_strategy: Any, parameters: tuple[dict[str, Any], ...]) -> tuple[NeighborhoodConfig | None, FixedRuleCostStressPlan | None, RegimeConfig]:
    neighborhood_document = (
        None
        if robustness_document["neighborhood"] is None
        else _strict_object(
            robustness_document["neighborhood"],
            path=f"{VALIDATION_RUNTIME_KEY}.robustness.neighborhood",
            keys=set(NeighborhoodConfig.__dataclass_fields__),
        )
    )
    definitions = []
    for index, item in enumerate(
        [] if neighborhood_document is None else _strict_list(
            neighborhood_document["definitions"],
            path="robustness.neighborhood.definitions",
        )
    ):
        definition_document = _strict_object(
            item,
            path=f"robustness.neighborhood.definitions[{index}]",
            keys=set(ParameterNeighborhoodDefinition.__dataclass_fields__),
        )
        definitions.append(
            ParameterNeighborhoodDefinition(
                parameter_name=_strict_text(
                    definition_document["parameter_name"],
                    path=f"robustness.neighborhood.definitions[{index}].parameter_name",
                ),
                method=_strict_text(
                    definition_document["method"],
                    path=f"robustness.neighborhood.definitions[{index}].method",
                ),
                explicit_values=tuple(
                    _strict_list(
                        definition_document["explicit_values"],
                        path=f"robustness.neighborhood.definitions[{index}].explicit_values",
                    )
                ),
                integer_offsets=tuple(
                    _strict_int(
                        value,
                        path=f"robustness.neighborhood.definitions[{index}].integer_offsets[{offset_index}]",
                    )
                    for offset_index, value in enumerate(
                        _strict_list(
                            definition_document["integer_offsets"],
                            path=f"robustness.neighborhood.definitions[{index}].integer_offsets",
                        )
                    )
                ),
                percentage_offsets=tuple(
                    _strict_number(
                        value,
                        path=f"robustness.neighborhood.definitions[{index}].percentage_offsets[{offset_index}]",
                    )
                    for offset_index, value in enumerate(
                        _strict_list(
                            definition_document["percentage_offsets"],
                            path=f"robustness.neighborhood.definitions[{index}].percentage_offsets",
                        )
                    )
                ),
            )
        )
    neighborhood = None if neighborhood_document is None else NeighborhoodConfig(
        definitions=tuple(definitions),
        minimum_valid_neighbors=_strict_int(
            neighborhood_document["minimum_valid_neighbors"],
            path="robustness.neighborhood.minimum_valid_neighbors",
        ),
        required_pass_proportion=_strict_number(
            neighborhood_document["required_pass_proportion"],
            path="robustness.neighborhood.required_pass_proportion",
        ),
        degradation_mode=_strict_text(
            neighborhood_document["degradation_mode"],
            path="robustness.neighborhood.degradation_mode",
        ),
        maximum_absolute_degradation=_strict_number(
            neighborhood_document["maximum_absolute_degradation"],
            path="robustness.neighborhood.maximum_absolute_degradation",
        ),
        maximum_relative_degradation=_strict_number(
            neighborhood_document["maximum_relative_degradation"],
            path="robustness.neighborhood.maximum_relative_degradation",
        ),
    )
    stress_document = robustness_document.get("fixed_rule_cost_stress")
    stress = None if stress_document is None else FixedRuleCostStressPlan(**_strict_object(
        stress_document,
        path="robustness.fixed_rule_cost_stress",
        keys=set(FixedRuleCostStressPlan.__dataclass_fields__),
    ))
    if stress is not None and (installed_strategy.spec.parameters or parameters != ({},)):
        raise ValueError("fixed-rule cost stress requires one parameter-free Candidate")
    regimes_document = _strict_object(
        robustness_document["regimes"],
        path=f"{VALIDATION_RUNTIME_KEY}.robustness.regimes",
        keys=set(RegimeConfig.__dataclass_fields__),
    )
    regimes = RegimeConfig(
        trend_window=_strict_int(
            regimes_document["trend_window"], path="robustness.regimes.trend_window"
        ),
        trend_neutral_tolerance=_strict_number(
            regimes_document["trend_neutral_tolerance"],
            path="robustness.regimes.trend_neutral_tolerance",
        ),
        volatility_window=_strict_int(
            regimes_document["volatility_window"],
            path="robustness.regimes.volatility_window",
        ),
        volatility_threshold=_strict_number(
            regimes_document["volatility_threshold"],
            path="robustness.regimes.volatility_threshold",
        ),
        annualization_factor=_strict_number(
            regimes_document["annualization_factor"],
            path="robustness.regimes.annualization_factor",
        ),
        minimum_observations=_strict_int(
            regimes_document["minimum_observations"],
            path="robustness.regimes.minimum_observations",
        ),
        minimum_trades=_optional_int(
            regimes_document["minimum_trades"],
            path="robustness.regimes.minimum_trades",
        ),
    )

    return neighborhood, stress, regimes
