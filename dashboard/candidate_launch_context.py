"""Resolve the saved configuration and exact Candidate gate for a run request."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from dashboard.candidate_workflow import candidate_selection_blocker
from dashboard.run_adapter import (
    ConfigurationReadinessView, SavedConfigurationView,
    configuration_readiness, list_saved_configurations,
)


def resolve_launch_selection(
    *, database: str | Path, configurations: list[SavedConfigurationView],
    readiness_by_id: dict[str, ConfigurationReadinessView],
    configuration_id: str | None, draft: dict[str, Any] | None,
    is_candidate: Callable[[str | None], bool],
) -> tuple[SavedConfigurationView | None, ConfigurationReadinessView | None, str | None]:
    current = {configuration.configuration_id: configuration for configuration in configurations}
    current.update({configuration.configuration_id: configuration
                    for configuration in list_saved_configurations(database)})
    selected = current.get(configuration_id or "")
    readiness = readiness_by_id.get(selected.configuration_id) if selected else None
    candidate = bool(selected and is_candidate(selected.configuration_id))
    if candidate and readiness is None:
        readiness = configuration_readiness(selected, None)
        readiness_by_id[selected.configuration_id] = readiness
    blocker = (candidate_selection_blocker(str((draft or {}).get("draft_id") or ""), configuration_id, database=database)
               if draft is not None or candidate else None)
    return selected, readiness, blocker
