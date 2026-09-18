"""Fixture-only Setup draft validation and immutable persistence boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from dashboard.run_adapter import (
    CatalogSnapshot,
    ConfigurationReadinessView,
    SavedConfigurationView,
    configuration_readiness,
)
from persistence import (
    ConfigurationRecord,
    PersistenceService,
    StrategyLifecycle,
    canonical_json,
    configuration_hash,
)
from strategies import get_strategy


class SetupDraftError(ValueError):
    """Raised when an untrusted Setup draft cannot be saved safely."""


@dataclass(frozen=True)
class SetupDraftBase:
    """One immutable persisted setup plus its exact canonical document."""

    configuration: SavedConfigurationView
    document: dict[str, Any]


@dataclass(frozen=True)
class SetupDraftField:
    section: str
    path: str
    label: str
    value: object
    editable: bool
    reason: str
    options: tuple[object, ...] = ()
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class SetupDraftEvaluation:
    base: SetupDraftBase
    document: dict[str, Any]
    readiness: ConfigurationReadinessView
    errors: tuple[str, ...]
    dirty: bool

    @property
    def saveable(self) -> bool:
        return self.dirty and not self.errors and self.readiness.ready


@dataclass(frozen=True)
class SetupDraftSaveResult:
    configuration: ConfigurationRecord
    view: SavedConfigurationView
    created: bool


_MARKET_DATA_FIELDS = frozenset(
    {
        "provider",
        "dataset_id",
        "dataset",
        "symbol",
        "instrument",
        "timeframe",
        "interval",
        "coverage_start",
        "coverage_end",
        "coverage_end_policy",
    }
)
_EXECUTION_FIELDS = frozenset(
    {
        "initial_cash",
        "fees",
        "slippage",
        "order_size",
        "leverage",
        "price_multiplier",
        "fixed_fee_per_contract_per_side",
        "fixed_fee_per_order",
        "slippage_points",
        "slippage_ticks",
        "tick_size",
    }
)
_STRICTLY_POSITIVE_EXECUTION_FIELDS = frozenset(
    {"initial_cash", "order_size", "leverage", "price_multiplier"}
)
_SECTION_ORDER = ("market_data", "parameters", "execution")
_MARKET_DATA_ORDER = (
    "provider",
    "dataset_id",
    "dataset",
    "symbol",
    "instrument",
    "timeframe",
    "interval",
    "coverage_start",
    "coverage_end",
    "coverage_end_policy",
)
_EXECUTION_ORDER = (
    "initial_cash",
    "fees",
    "slippage",
    "order_size",
    "leverage",
    "price_multiplier",
    "fixed_fee_per_contract_per_side",
    "fixed_fee_per_order",
    "slippage_points",
    "slippage_ticks",
    "tick_size",
)


def base_from_view(
    configuration: SavedConfigurationView,
    document: Mapping[str, Any] | None = None,
) -> SetupDraftBase:
    """Build a safe draft base, preserving non-editable configuration sections."""

    source = (
        deepcopy(dict(document))
        if document is not None
        else {
            "experiment_id": configuration.experiment_id,
            "strategy_id": configuration.strategy_id,
            "strategy_version": configuration.strategy_version,
            "market_data": deepcopy(configuration.market_data),
            "parameters": deepcopy(configuration.parameters),
            "execution": deepcopy(configuration.execution),
            "ranking": {"columns": (), "ascending": ()},
            "screening": {"kind": "none"},
        }
    )
    _validate_document_shape(source)
    if source["strategy_id"] != configuration.strategy_id or source[
        "strategy_version"
    ] != configuration.strategy_version:
        raise SetupDraftError(
            "The saved setup strategy identity does not match its persisted record."
        )
    return SetupDraftBase(configuration=configuration, document=source)


def load_persisted_base(
    database: str | Path,
    configuration: SavedConfigurationView,
) -> SetupDraftBase:
    """Load the exact persisted document, with a test-safe view fallback."""

    service = PersistenceService(database)
    try:
        record = service.configurations.get(configuration.configuration_id)
    finally:
        service.close()
    if record is None:
        return base_from_view(configuration)
    try:
        document = json.loads(record.canonical_config_json)
    except json.JSONDecodeError as exc:
        raise SetupDraftError("The saved setup contains invalid canonical JSON.") from exc
    if not isinstance(document, Mapping):
        raise SetupDraftError("The saved setup canonical document is not an object.")
    if configuration.config_hash != record.config_hash:
        raise SetupDraftError("The saved setup checksum does not match its record.")
    return base_from_view(configuration, document)


def draft_fields(base: SetupDraftBase) -> tuple[SetupDraftField, ...]:
    """Return scalar operator controls without exposing raw configuration JSON."""

    parameter_definitions: Mapping[str, Any] = {}
    try:
        strategy = get_strategy(base.configuration.strategy_id)
    except KeyError:
        strategy = None
    if strategy is not None:
        parameter_definitions = strategy.spec.parameter_map

    fields: list[SetupDraftField] = []
    market_data = base.document["market_data"]
    data_free = (
        isinstance(market_data, Mapping)
        and str(market_data.get("kind", "")).casefold() == "none"
    )
    for section in _SECTION_ORDER:
        values = base.document[section]
        assert isinstance(values, Mapping)
        leaves = list(_scalar_leaves(values))
        leaves.sort(key=lambda item: _field_order(section, item[0]))
        for path_parts, value in leaves:
            leaf = path_parts[-1]
            editable = False
            reason = "Recorded by the immutable fixture contract."
            options: tuple[object, ...] = ()
            minimum: float | None = None
            maximum: float | None = None
            if section == "market_data" and leaf in _MARKET_DATA_FIELDS:
                editable = isinstance(value, str) and not data_free
                reason = (
                    "Not used by this data-free fixture."
                    if data_free
                    else "A changed value must match a committed, locally verified dataset."
                )
            elif section == "parameters" and leaf in parameter_definitions:
                definition = parameter_definitions[leaf]
                options = tuple(definition.allowed_values or ())
                minimum = definition.minimum
                maximum = definition.maximum
                editable = (
                    definition.approval_state == "approved"
                    and (not options or len(options) > 1)
                )
                reason = (
                    definition.description
                    if editable
                    else "This approved fixture parameter is fixed."
                )
            elif section == "execution" and leaf in _EXECUTION_FIELDS:
                editable = isinstance(value, (int, float)) and not isinstance(value, bool)
                minimum = 0.0
                reason = "A bounded fixture assumption; it does not model a live fill."
            fields.append(
                SetupDraftField(
                    section=section,
                    path=_encode_path(path_parts),
                    label=" / ".join(_label(part) for part in path_parts),
                    value=value,
                    editable=editable,
                    reason=reason,
                    options=options,
                    minimum=minimum,
                    maximum=maximum,
                )
            )
    return tuple(fields)


def evaluate_setup_draft(
    base: SetupDraftBase,
    *,
    field_ids: Sequence[Mapping[str, object]] = (),
    field_values: Sequence[object] = (),
    catalog_snapshot: CatalogSnapshot | None,
) -> SetupDraftEvaluation:
    """Apply untrusted page-local values to a copy and fail closed on any mismatch."""

    document = deepcopy(base.document)
    errors: list[str] = []
    controls = {(field.section, field.path): field for field in draft_fields(base)}
    if len(field_ids) != len(field_values):
        errors.append("The setup draft controls were incomplete. Reload Set up and try again.")
    for identity, value in zip(field_ids, field_values):
        if identity.get("configuration") != base.configuration.configuration_id:
            continue
        section = identity.get("section")
        path = identity.get("path")
        if not isinstance(section, str) or not isinstance(path, str):
            errors.append("A setup draft field identity was invalid.")
            continue
        control = controls.get((section, path))
        if control is None:
            errors.append("The setup draft contained an unsupported field.")
            continue
        try:
            current = _read_path(document[section], _decode_path(path))
            coerced = _coerce_value(value, current)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"{control.label}: {exc}")
            continue
        if not control.editable and coerced != current:
            errors.append(f"{control.label} is fixed by the approved fixture contract.")
            continue
        if control.editable:
            _write_path(document[section], _decode_path(path), coerced)

    errors.extend(_document_errors(base, document))
    view = _view_from_document(base.configuration, document)
    readiness = configuration_readiness(view, catalog_snapshot)
    return SetupDraftEvaluation(
        base=base,
        document=document,
        readiness=readiness,
        errors=tuple(dict.fromkeys(errors)),
        dirty=canonical_json(document) != canonical_json(base.document),
    )


def save_setup_draft(
    database: str | Path,
    evaluation: SetupDraftEvaluation,
) -> SetupDraftSaveResult:
    """Persist one validated immutable document without changing its base record."""

    if not evaluation.dirty:
        raise SetupDraftError("No setup changes are waiting to be saved.")
    if evaluation.errors:
        raise SetupDraftError(evaluation.errors[0])
    if not evaluation.readiness.ready:
        reason = evaluation.readiness.blockers[0].reason
        raise SetupDraftError(f"The setup draft is blocked: {reason}")

    service = PersistenceService(database)
    try:
        base_record = service.configurations.get(
            evaluation.base.configuration.configuration_id
        )
        if base_record is None:
            raise SetupDraftError("The selected saved setup no longer exists.")
        if base_record.canonical_config_json != canonical_json(
            evaluation.base.document
        ):
            raise SetupDraftError(
                "The selected saved setup changed unexpectedly; reload before saving."
            )
        strategy = service.strategies.get(
            base_record.strategy_id,
            base_record.strategy_version,
        )
        if (
            strategy is None
            or not strategy.active
            or strategy.lifecycle != StrategyLifecycle.INFRASTRUCTURE_FIXTURE
        ):
            raise SetupDraftError(
                "The selected strategy is no longer an active infrastructure fixture."
            )
        proposed_id = configuration_hash(evaluation.document)
        existing = service.configurations.get(proposed_id)
        record = service.upsert_configuration(deepcopy(evaluation.document))
        if record.configuration_id != proposed_id:
            raise SetupDraftError("The saved setup identity did not match its content.")
        view = _view_from_document(evaluation.base.configuration, evaluation.document)
        return SetupDraftSaveResult(
            configuration=record,
            view=view,
            created=existing is None,
        )
    except ValueError as exc:
        if isinstance(exc, SetupDraftError):
            raise
        raise SetupDraftError(f"The immutable setup could not be saved: {exc}") from exc
    finally:
        service.close()


def _view_from_document(
    base: SavedConfigurationView,
    document: Mapping[str, Any],
) -> SavedConfigurationView:
    _validate_document_shape(document)
    return SavedConfigurationView(
        configuration_id=configuration_hash(document),
        experiment_id=str(document["experiment_id"]),
        strategy_id=str(document["strategy_id"]),
        strategy_version=str(document["strategy_version"]),
        strategy_name=base.strategy_name,
        lifecycle=base.lifecycle,
        active=base.active,
        parameters=deepcopy(dict(document["parameters"])),
        execution=deepcopy(dict(document["execution"])),
        market_data=deepcopy(dict(document["market_data"])),
        config_hash=configuration_hash(document),
    )


def _document_errors(
    base: SetupDraftBase,
    document: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    try:
        _validate_document_shape(document)
    except SetupDraftError as exc:
        return [str(exc)]
    for key in ("strategy_id", "strategy_version", "ranking", "screening"):
        if canonical_json(document[key]) != canonical_json(base.document[key]):
            errors.append(f"{_label(key)} is immutable for this fixture draft.")
    execution = document["execution"]
    assert isinstance(execution, Mapping)
    for key in _EXECUTION_FIELDS:
        value = execution.get(key)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{_label(key)} must be numeric.")
        elif not math.isfinite(float(value)):
            errors.append(f"{_label(key)} must be finite.")
        elif key in _STRICTLY_POSITIVE_EXECUTION_FIELDS and value <= 0:
            errors.append(f"{_label(key)} must be greater than zero.")
        elif key not in _STRICTLY_POSITIVE_EXECUTION_FIELDS and value < 0:
            errors.append(f"{_label(key)} must not be negative.")

    parameters = document["parameters"]
    assert isinstance(parameters, Mapping)
    try:
        strategy = get_strategy(str(document["strategy_id"]))
    except KeyError:
        strategy = None
    if strategy is not None:
        candidate = parameters.get("strategy_parameters", parameters)
        if not isinstance(candidate, Mapping):
            errors.append("Approved strategy parameters must be an object.")
        else:
            try:
                strategy.validate_parameters(candidate)
            except (TypeError, ValueError) as exc:
                errors.append(f"Approved parameter validation failed: {exc}")
    return errors


def _validate_document_shape(document: Mapping[str, Any]) -> None:
    required = {
        "experiment_id",
        "strategy_id",
        "strategy_version",
        "market_data",
        "parameters",
        "execution",
        "ranking",
        "screening",
    }
    missing = sorted(required - set(document))
    if missing:
        raise SetupDraftError(
            "The saved setup is missing required field(s): " + ", ".join(missing)
        )
    for key in ("experiment_id", "strategy_id", "strategy_version"):
        if not isinstance(document[key], str) or not str(document[key]).strip():
            raise SetupDraftError(f"{_label(key)} must be recorded.")
    for key in ("market_data", "parameters", "execution", "ranking", "screening"):
        if not isinstance(document[key], Mapping):
            raise SetupDraftError(f"{_label(key)} must be an object.")


def _scalar_leaves(
    values: Mapping[str, Any],
    prefix: tuple[str, ...] = (),
):
    for raw_key, value in values.items():
        key = str(raw_key)
        path = (*prefix, key)
        if isinstance(value, Mapping):
            yield from _scalar_leaves(value, path)
        else:
            yield path, value


def _field_order(section: str, path: tuple[str, ...]) -> tuple[int, str]:
    leaf = path[-1]
    order = _MARKET_DATA_ORDER if section == "market_data" else _EXECUTION_ORDER
    try:
        index = order.index(leaf)
    except ValueError:
        index = len(order)
    return index, ".".join(path)


def _encode_path(parts: tuple[str, ...]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _decode_path(value: str) -> tuple[str, ...]:
    if not value.startswith("/"):
        raise ValueError("field path is invalid")
    return tuple(part.replace("~1", "/").replace("~0", "~") for part in value[1:].split("/"))


def _read_path(values: Mapping[str, Any], parts: tuple[str, ...]) -> object:
    current: object = values
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError("field no longer exists")
        current = current[part]
    return current


def _write_path(values: dict[str, Any], parts: tuple[str, ...], value: object) -> None:
    current: dict[str, Any] = values
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            raise KeyError("field no longer exists")
        current = nested
    current[parts[-1]] = value


def _coerce_value(value: object, reference: object) -> object:
    if isinstance(reference, bool):
        if not isinstance(value, bool):
            raise TypeError("must be Yes or No")
        return value
    if isinstance(reference, int):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("must be a whole number")
        if not math.isfinite(float(value)) or int(value) != value:
            raise ValueError("must be a finite whole number")
        return int(value)
    if isinstance(reference, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("must be numeric")
        if not math.isfinite(float(value)):
            raise ValueError("must be finite")
        return float(value)
    if isinstance(reference, str):
        if not isinstance(value, str):
            raise TypeError("must be text")
        return value.strip()
    if value != reference:
        raise TypeError("cannot be edited safely")
    return reference


def _label(value: str) -> str:
    return value.replace("_", " ").strip().title()


__all__ = [
    "SetupDraftBase",
    "SetupDraftError",
    "SetupDraftEvaluation",
    "SetupDraftField",
    "SetupDraftSaveResult",
    "base_from_view",
    "draft_fields",
    "evaluate_setup_draft",
    "load_persisted_base",
    "save_setup_draft",
]
