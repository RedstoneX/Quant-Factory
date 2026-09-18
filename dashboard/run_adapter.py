"""Read-only dashboard adapter for saved run configurations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from persistence import PersistenceService, StrategyLifecycle
from persistence.database import database_path


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
