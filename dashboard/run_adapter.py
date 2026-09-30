"""Read-only dashboard adapter for saved run configurations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, TypeAlias

from dashboard.health import DatasetHealth
from market_data.catalog import DataLocations
from persistence import PersistenceService, StrategyLifecycle
from persistence.database import database_path
from persistence.models import normalized_configuration_document
from strategies import get_strategy, validate_parameter_plan


CatalogSnapshot: TypeAlias = tuple[
    DataLocations | None,
    tuple[DatasetHealth, ...],
    str | None,
]


@dataclass(frozen=True)
class ConfigurationField:
    """One immutable operator-facing configuration fact."""

    label: str
    value: str


@dataclass(frozen=True)
class ConfigurationBlocker:
    """A launch blocker with one operator-safe remedy."""

    code: str
    reason: str
    remedy: str
    remedy_href: str


@dataclass(frozen=True)
class ConfigurationReadinessView:
    """Read-only, immutable launch-readiness evidence for one saved setup."""

    configuration_id: str
    experiment_id: str
    strategy_name: str
    strategy_identity: str
    lifecycle: str
    config_hash: str
    provider: str
    dataset: str
    instrument: str
    timeframe: str
    requested_coverage: str
    actual_coverage: str
    local_availability: str
    local_validation: str
    parameters: tuple[ConfigurationField, ...]
    execution_assumptions: tuple[ConfigurationField, ...]
    blockers: tuple[ConfigurationBlocker, ...]
    state: str

    @property
    def ready(self) -> bool:
        return self.state == "ready" and not self.blockers


@dataclass(frozen=True)
class SavedConfigurationView:
    """Operator-facing saved configuration without exposing persistence records."""

    configuration_id: str
    experiment_id: str
    strategy_id: str
    strategy_version: str
    strategy_name: str
    lifecycle: str
    active: bool
    parameters: dict[str, Any]
    execution: dict[str, Any]
    market_data: dict[str, Any]
    config_hash: str

    @property
    def launchable(self) -> bool:
        return (
            self.active
            and self.lifecycle == StrategyLifecycle.INFRASTRUCTURE_FIXTURE.value
        )

    @property
    def label(self) -> str:
        return (
            f"{self.strategy_name} · "
            f"{self.experiment_id} · "
            f"{self.configuration_id[:10]}"
        )


@dataclass(frozen=True)
class IdeaDraftView:
    """Durable local operator intake without research authority."""

    draft_id: str
    title: str
    description: str
    source_url: str
    attribution: str
    notes: str
    configuration_id: str | None
    created_at: str
    updated_at: str

    def to_store(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class SetupParameterView:
    name: str
    label: str
    description: str
    allowed_values: tuple[Any, ...]
    default: Any


@dataclass(frozen=True)
class SetupStrategyView:
    """Approved persisted strategy specification available for bounded setup."""

    strategy_id: str
    strategy_version: str
    name: str
    description: str
    lifecycle: str
    parameters: tuple[SetupParameterView, ...]

    @property
    def identity(self) -> str:
        return f"{self.strategy_id}@{self.strategy_version}"


def _idea_view(record: Any) -> IdeaDraftView:
    return IdeaDraftView(**asdict(record))


def list_idea_drafts(
    database: str | Path,
) -> tuple[IdeaDraftView, ...]:
    service = PersistenceService(database_path(database))
    try:
        return tuple(_idea_view(record) for record in service.idea_drafts.list())
    finally:
        service.close()


def save_idea_draft(
    values: Mapping[str, str],
    *,
    draft_id: str | None = None,
    database: str | Path,
) -> IdeaDraftView:
    service = PersistenceService(database_path(database))
    try:
        return _idea_view(
            service.save_idea_draft(
                draft_id=draft_id,
                title=values.get("title", ""),
                description=values.get("description", ""),
                source_url=values.get("source_url", ""),
                attribution=values.get("attribution", ""),
                notes=values.get("notes", ""),
            )
        )
    finally:
        service.close()


def delete_idea_draft(
    draft_id: str,
    *,
    database: str | Path,
) -> bool:
    service = PersistenceService(database_path(database))
    try:
        return service.delete_idea_draft(draft_id)
    finally:
        service.close()


def _setup_strategies(service: PersistenceService) -> tuple[SetupStrategyView, ...]:
    available: list[SetupStrategyView] = []
    for record in service.strategies.list(active=True):
        if record.lifecycle not in {
            StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
            StrategyLifecycle.CANDIDATE,
            StrategyLifecycle.WATCHLIST,
        }:
            continue
        try:
            implementation = get_strategy(record.strategy_id)
        except KeyError:
            continue
        specification = implementation.spec
        if (
            specification.identity.version != record.strategy_version
            or specification.approval_state != "approved"
        ):
            continue
        try:
            validate_parameter_plan(specification, require_approved=True)
        except (TypeError, ValueError):
            continue
        if any(not definition.allowed_values for definition in specification.parameters):
            continue
        available.append(
            SetupStrategyView(
                strategy_id=record.strategy_id,
                strategy_version=record.strategy_version,
                name=specification.identity.name,
                description=specification.identity.description,
                lifecycle=record.lifecycle.value,
                parameters=tuple(
                    SetupParameterView(
                        name=definition.name,
                        label=_label(definition.name),
                        description=definition.description,
                        allowed_values=definition.allowed_values or (),
                        default=definition.default,
                    )
                    for definition in specification.parameters
                ),
            )
        )
    return tuple(sorted(available, key=lambda item: (item.name.casefold(), item.identity)))


def list_setup_strategies(
    database: str | Path,
) -> tuple[SetupStrategyView, ...]:
    service = PersistenceService(database_path(database))
    try:
        return _setup_strategies(service)
    finally:
        service.close()


def persist_bounded_idea_configuration(
    *,
    draft_id: str,
    strategy_identity: str,
    parameters: Mapping[str, Any],
    database: str | Path,
) -> str:
    """Persist one immutable, non-executing setup from approved specification facts."""

    service = PersistenceService(database_path(database))
    try:
        draft = service.idea_drafts.get(draft_id)
        if draft is None:
            raise ValueError("Choose a saved idea draft before creating a setup.")
        strategy_view = next(
            (
                candidate
                for candidate in _setup_strategies(service)
                if candidate.identity == strategy_identity
            ),
            None,
        )
        if strategy_view is None:
            raise ValueError("Choose an active approved strategy specification.")
        implementation = get_strategy(strategy_view.strategy_id)
        specification = implementation.spec
        expected_names = {definition.name for definition in specification.parameters}
        if set(parameters) != expected_names:
            raise ValueError("Every approved parameter must have exactly one selected value.")
        for definition in specification.parameters:
            value = parameters[definition.name]
            if definition.allowed_values is None or value not in definition.allowed_values:
                raise ValueError(
                    f"{definition.name} must use a pre-approved allowed value."
                )
            definition.validate(value)
        normalized = implementation.validate_parameters(dict(parameters))
        if set(normalized) != expected_names:
            raise ValueError("Strategy validation changed the approved parameter boundary.")

        document = normalized_configuration_document(
            experiment_id=f"operator_{draft.draft_id}_{strategy_view.strategy_id}",
            strategy_id=strategy_view.strategy_id,
            strategy_version=strategy_view.strategy_version,
            market_data={
                "kind": "strategy_specification_requirements",
                "requirements": asdict(specification.data),
            },
            parameters=normalized,
            execution=asdict(specification.assumptions),
            ranking={},
            screening={},
        )
        _linked, configuration = service.upsert_idea_configuration(
            draft_id=draft.draft_id,
            document=document,
        )
        return configuration.configuration_id
    finally:
        service.close()

def list_saved_configurations(
    database: str | Path | None = None,
) -> tuple[SavedConfigurationView, ...]:
    """Return saved configurations with resolved strategy metadata."""

    service = PersistenceService(database_path(database))
    try:
        views: list[SavedConfigurationView] = []

        for configuration in service.configurations.list():
            strategy = service.strategies.get(
                configuration.strategy_id,
                configuration.strategy_version,
            )
            if strategy is None:
                continue

            try:
                document = json.loads(configuration.canonical_config_json)
                if not isinstance(document, Mapping):
                    continue
                experiment_id = document.get("experiment_id")
                parameters = document.get("parameters", {})
                execution = document.get("execution", {})
                market_data = document.get("market_data", {})
                if not isinstance(experiment_id, str) or not experiment_id.strip():
                    continue
                if not isinstance(parameters, Mapping):
                    continue
                if not isinstance(execution, Mapping):
                    continue
                if not isinstance(market_data, Mapping):
                    continue
                view = SavedConfigurationView(
                    configuration_id=configuration.configuration_id,
                    experiment_id=experiment_id,
                    strategy_id=configuration.strategy_id,
                    strategy_version=configuration.strategy_version,
                    strategy_name=strategy.display_name,
                    lifecycle=strategy.lifecycle.value,
                    active=strategy.active,
                    parameters=dict(parameters),
                    execution=dict(execution),
                    market_data=dict(market_data),
                    config_hash=configuration.config_hash,
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            views.append(view)

        return tuple(
            sorted(
                views,
                key=lambda item: (
                    not item.launchable,
                    item.strategy_name.lower(),
                    item.experiment_id.lower(),
                    item.configuration_id,
                ),
            )
        )
    finally:
        service.close()


def configuration_readiness(
    configuration: SavedConfigurationView,
    catalog_snapshot: CatalogSnapshot | None,
) -> ConfigurationReadinessView:
    """Reconcile one persisted setup with read-only local catalog evidence."""

    market_data = configuration.market_data
    data_free = _text(market_data.get("kind")).casefold() == "none"
    parameters = _mapping_fields(configuration.parameters)
    execution = _mapping_fields(configuration.execution)
    blockers: list[ConfigurationBlocker] = []

    if not configuration.active:
        blockers.append(
            _blocker(
                "strategy_inactive",
                "This saved setup uses an inactive strategy version.",
                "Return to Set up and choose an active approved fixture.",
                "/research/setup",
            )
        )
    if configuration.lifecycle != StrategyLifecycle.INFRASTRUCTURE_FIXTURE.value:
        blockers.append(
            _blocker(
                "lifecycle_unsupported",
                "Only an infrastructure fixture can run during Milestone 23.",
                "Return to Set up and choose an approved infrastructure fixture.",
                "/research/setup",
            )
        )
    if not configuration.execution:
        blockers.append(
            _blocker(
                "missing_execution_assumptions",
                "The saved setup does not record execution assumptions.",
                "Return to Set up and choose a saved setup with explicit execution assumptions.",
                "/research/setup",
            )
        )

    if data_free:
        return ConfigurationReadinessView(
            configuration_id=configuration.configuration_id,
            experiment_id=configuration.experiment_id,
            strategy_name=configuration.strategy_name,
            strategy_identity=(
                f"{configuration.strategy_id}@{configuration.strategy_version}"
            ),
            lifecycle=configuration.lifecycle,
            config_hash=configuration.config_hash,
            provider="Not required",
            dataset="No market data",
            instrument="Not required",
            timeframe="Not required",
            requested_coverage="Not required",
            actual_coverage="Not required",
            local_availability="Not required",
            local_validation="Not required",
            parameters=parameters,
            execution_assumptions=execution,
            blockers=tuple(blockers),
            state="ready" if not blockers else "unsupported",
        )

    provider = _text(market_data.get("provider"))
    dataset_id = _text(market_data.get("dataset_id"))
    dataset = _text(market_data.get("dataset")) or dataset_id
    instrument = _text(market_data.get("symbol") or market_data.get("instrument"))
    timeframe = _text(market_data.get("timeframe") or market_data.get("interval"))

    required = (
        ("provider", provider, "provider"),
        ("dataset_id", dataset_id, "dataset identity"),
        ("instrument", instrument, "instrument"),
        ("timeframe", timeframe, "timeframe"),
    )
    for code, value, label in required:
        if not value:
            blockers.append(
                _blocker(
                    f"missing_{code}",
                    f"The saved setup does not record a {label}.",
                    f"Return to Set up and choose a saved setup with a recorded {label}.",
                    "/research/setup",
                )
            )

    manifest_health: DatasetHealth | None = None
    catalog_configured = False
    if catalog_snapshot is not None:
        locations, datasets, _catalog_error = catalog_snapshot
        catalog_configured = locations is not None
        manifest_health = next(
            (
                item
                for item in datasets
                if item.manifest.dataset_id == dataset_id
            ),
            None,
        )

    local_availability = "Not checked"
    local_validation = "Not checked"
    actual_coverage = "Not available"

    if not dataset_id:
        pass
    elif manifest_health is None:
        blockers.append(
            _blocker(
                "manifest_missing",
                f"Dataset {dataset_id} has no readable committed manifest.",
                "Inspect Market data and restore or correct the committed dataset manifest.",
                "/research/market-data",
            )
        )
    else:
        manifest = manifest_health.manifest
        actual_coverage = _actual_coverage(manifest.metadata)
        for code, label, saved, committed in (
            ("provider_mismatch", "provider", provider, manifest.provider),
            ("instrument_mismatch", "instrument", instrument, manifest.symbol),
            ("timeframe_mismatch", "timeframe", timeframe, manifest.timeframe),
        ):
            if saved and _identity(saved) != _identity(committed):
                blockers.append(
                    _blocker(
                        code,
                        (
                            f"The saved {label} ({saved}) does not match the "
                            f"committed manifest ({committed})."
                        ),
                        "Return to Set up and choose a configuration matching the committed manifest.",
                        "/research/setup",
                    )
                )
        committed_dataset = _text(manifest.metadata.get("dataset"))
        if dataset and committed_dataset and _identity(dataset) != _identity(committed_dataset):
            blockers.append(
                _blocker(
                    "dataset_mismatch",
                    (
                        f"The saved dataset ({dataset}) does not match the committed "
                        f"manifest ({committed_dataset})."
                    ),
                    "Return to Set up and choose a configuration matching the committed manifest.",
                    "/research/setup",
                )
            )
        if manifest.status != "validated":
            blockers.append(
                _blocker(
                    "manifest_not_validated",
                    (
                        f"Dataset {dataset_id} is {manifest.status}, not validated for use."
                    ),
                    "Inspect Market data and use a validated dataset.",
                    "/research/market-data",
                )
            )

        local_availability = manifest_health.availability
        local_validation = manifest_health.checksum
        if catalog_configured:
            if manifest_health.availability != "Available locally":
                blockers.append(
                    _blocker(
                        "data_unavailable",
                        (
                            f"Dataset {dataset_id} is not available locally "
                            f"({manifest_health.availability})."
                        ),
                        "Inspect Market data and restore the exact cataloged dataset file.",
                        "/research/market-data",
                    )
                )
            if manifest_health.checksum != "Verified":
                blockers.append(
                    _blocker(
                        "checksum_unverified",
                        (
                            f"Dataset {dataset_id} has not passed checksum verification "
                            f"({manifest_health.checksum})."
                        ),
                        "Inspect Market data and verify the local file against its committed checksum.",
                        "/research/market-data",
                    )
                )

    if not catalog_configured and dataset_id:
        blockers.append(
            _blocker(
                "catalog_not_checked",
                "Local dataset availability and checksum were not verified.",
                "Configure the local data catalog, then inspect Market data before launching.",
                "/research/market-data",
            )
        )

    data_blocker_codes = {
        "manifest_missing",
        "manifest_not_validated",
        "provider_mismatch",
        "dataset_mismatch",
        "instrument_mismatch",
        "timeframe_mismatch",
        "data_unavailable",
        "checksum_unverified",
        "catalog_not_checked",
    }
    state = (
        "ready"
        if not blockers
        else "data_unavailable"
        if any(blocker.code in data_blocker_codes for blocker in blockers)
        else "unsupported"
    )
    return ConfigurationReadinessView(
        configuration_id=configuration.configuration_id,
        experiment_id=configuration.experiment_id,
        strategy_name=configuration.strategy_name,
        strategy_identity=f"{configuration.strategy_id}@{configuration.strategy_version}",
        lifecycle=configuration.lifecycle,
        config_hash=configuration.config_hash,
        provider=provider or "Not recorded",
        dataset=dataset or "Not recorded",
        instrument=instrument or "Not recorded",
        timeframe=timeframe or "Not recorded",
        requested_coverage=_requested_coverage(market_data),
        actual_coverage=actual_coverage,
        local_availability=local_availability,
        local_validation=local_validation,
        parameters=parameters,
        execution_assumptions=execution,
        blockers=tuple(blockers),
        state=state,
    )


def configuration_readiness_by_id(
    configurations: tuple[SavedConfigurationView, ...],
    catalog_snapshot: CatalogSnapshot | None,
) -> dict[str, ConfigurationReadinessView]:
    """Build the single readiness snapshot shared by mounted Setup and Run pages."""

    return {
        configuration.configuration_id: configuration_readiness(
            configuration,
            catalog_snapshot,
        )
        for configuration in configurations
    }


def _mapping_fields(values: Mapping[str, Any]) -> tuple[ConfigurationField, ...]:
    return tuple(
        ConfigurationField(_label(key), _display(value))
        for key, value in sorted(values.items(), key=lambda item: str(item[0]))
    )


def _label(value: object) -> str:
    return str(value).replace("_", " ").strip().title()


def _display(value: object) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return "Not recorded"
    if isinstance(value, Mapping):
        return "; ".join(
            f"{_label(key)}: {_display(item)}"
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        ) or "None recorded"
    if isinstance(value, (list, tuple)):
        return ", ".join(_display(item) for item in value) or "None recorded"
    rendered = str(value).replace("_", " ")
    return rendered.capitalize() if "_" in str(value) else rendered


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _identity(value: object) -> str:
    return _text(value).casefold()


def _requested_coverage(market_data: Mapping[str, Any]) -> str:
    start = _text(market_data.get("coverage_start"))
    end = _text(market_data.get("coverage_end"))
    end_policy = _text(market_data.get("coverage_end_policy"))
    if start and end:
        return f"{start} to {end}"
    if start and end_policy:
        return f"From {start}; end: {_display(end_policy)}"
    if start:
        return f"From {start}"
    if end:
        return f"Through {end}"
    return "Not recorded"


def _actual_coverage(metadata: Mapping[str, Any]) -> str:
    for key in ("actual_coverage", "full_stored_coverage"):
        coverage = metadata.get(key)
        if isinstance(coverage, Mapping):
            start = _text(coverage.get("first_timestamp") or coverage.get("start"))
            end = _text(coverage.get("last_timestamp") or coverage.get("end"))
            if start and end:
                return f"{start} to {end}"
    start = _text(metadata.get("earliest_timestamp"))
    end = _text(metadata.get("latest_timestamp"))
    return f"{start} to {end}" if start and end else "Not recorded"


def _blocker(
    code: str,
    reason: str,
    remedy: str,
    remedy_href: str,
) -> ConfigurationBlocker:
    return ConfigurationBlocker(code, reason, remedy, remedy_href)
