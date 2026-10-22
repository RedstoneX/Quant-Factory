"""Focused regression coverage for Milestone 19B run lineage manifests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from persistence import (
    ArtifactAvailability,
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    RuntimeLineage,
    StrategyLifecycle,
    canonical_json,
    initialize_database,
)
import persistence.database as database_module
import persistence.service as service_module
from persistence.database import transaction
from persistence.models import normalized_configuration_document


def _runtime(
    *,
    runtime_identity: str | None = None,
    git_commit_sha: str | None = "a" * 40,
    git_commit_available: bool = True,
    git_dirty_state: str = "clean",
    git_dirty_available: bool = True,
    git_dirty_entry_count: int | None = 0,
    git_dirty_fingerprint: str | None = "clean-fingerprint",
    python_implementation: str = "CPython",
    python_version: str = "3.12.0",
    python_cache_tag: str | None = "cpython-312",
    vectorbtpro_version: str | None = "2026.1.0",
    vectorbtpro_available: bool = True,
    package_fingerprint: str = "package-fingerprint",
    package_count: int = 3,
    platform_system: str = "Linux",
    platform_machine: str = "x86_64",
) -> RuntimeLineage:
    runtime = RuntimeLineage(
        runtime_identity="",
        git_commit_sha=git_commit_sha,
        git_commit_available=git_commit_available,
        git_dirty_state=git_dirty_state,
        git_dirty_available=git_dirty_available,
        git_dirty_entry_count=git_dirty_entry_count,
        git_dirty_fingerprint=git_dirty_fingerprint,
        python_implementation=python_implementation,
        python_version=python_version,
        python_cache_tag=python_cache_tag,
        vectorbtpro_version=vectorbtpro_version,
        vectorbtpro_available=vectorbtpro_available,
        package_fingerprint=package_fingerprint,
        package_count=package_count,
        platform_system=platform_system,
        platform_machine=platform_machine,
    )
    document = service_module.runtime_lineage_document(runtime)
    computed_identity = service_module._identity(
        {
            key: value
            for key, value in document.items()
            if key != "runtime_identity"
        }
    )
    return RuntimeLineage(
        **{
            **runtime.__dict__,
            "runtime_identity": runtime_identity or computed_identity,
        }
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "fixture@example.test")
    _git(repo, "config", "user.name", "Fixture User")
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "base")
    return repo


def _validation_summary(**overrides):
    summary = {
        "duplicate_timestamp_count": 0,
        "missing_open_count": 0,
        "missing_high_count": 0,
        "missing_low_count": 0,
        "missing_close_count": 0,
        "missing_volume_count": 0,
        "expected_session_gap_count": 0,
        "unexpected_session_gaps": [],
    }
    summary.update(overrides)
    return canonical_json(summary)


def _document(*, strategy_version: str = "1.0.0", execution=None, symbol: str = "SPY"):
    return normalized_configuration_document(
        experiment_id="lineage-fixture",
        strategy_id="fixture_strategy",
        strategy_version=strategy_version,
        market_data={"symbol": symbol, "provider": "fixture"},
        parameters={"window": 10},
        execution=execution or {"fees": 0.01, "slippage": 0.02, "mode": "fixture"},
        ranking={"columns": ("total_return",), "ascending": (False,)},
        screening={"minimum_trades": 1},
    )


def _provenance(run_id: str, **overrides) -> DataProvenanceRecord:
    values = {
        "run_id": run_id,
        "provider": "fixture",
        "provider_implementation": "fixture-provider",
        "symbol": "SPY",
        "interval": "1 day",
        "timezone": "America/New_York",
        "requested_coverage": "2020-01-01..2020-01-10",
        "actual_coverage": "2020-01-02..2020-01-10",
        "adjusted": True,
        "row_count": 7,
        "cache_action": "reused",
        "validation_summary_json": _validation_summary(),
        "manifest_reference": "data/manifests/fixture.json",
        "checksum": "dataset-checksum",
    }
    values.update(overrides)
    return DataProvenanceRecord(**values)


def _service_with_lineage_run(
    tmp_path: Path,
    *,
    run_id: str = "lineage-run",
    execution=None,
    provenance: DataProvenanceRecord | None = None,
    runtime_lineage: RuntimeLineage | None = None,
    runtime_lineage_provider=None,
) -> tuple[PersistenceService, str]:
    service = PersistenceService(
        tmp_path / "state" / f"{run_id}.sqlite3",
        runtime_lineage_provider=runtime_lineage_provider
        or (lambda: runtime_lineage or _runtime()),
    )
    service.register_strategy(
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        display_name="Fixture Strategy",
        description="Synthetic lineage fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        _document(execution=execution)
    )
    service.create_run(
        configuration_id=configuration.configuration_id,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        stage=RunStage.FIXTURE,
        run_id=run_id,
    )
    with transaction(service.connection):
        service.results.set_data_provenance(provenance or _provenance(run_id))
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=run_id,
                assumptions_json=canonical_json(
                    execution or {"fees": 0.01, "slippage": 0.02, "mode": "fixture"}
                ),
            )
        )
    service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.METRICS,
        logical_name="metrics",
        media_type="application/json",
        format="json",
        location=f"artifacts/{run_id}/metrics.json",
        content=b'{"total_return":0.1}',
    )
    return service, configuration.configuration_id


def test_manifest_references_exact_configuration_strategy_and_provenance(tmp_path: Path) -> None:
    service, configuration_id = _service_with_lineage_run(tmp_path)
    try:
        configuration = service.configurations.get(configuration_id)
        assert configuration is not None

        manifest = service.build_run_manifest("lineage-run", created_at="2026-07-13T00:00:00Z")
        assert manifest.schema_version == 3
        assert manifest.lineage is not None
        assert manifest.lineage.configuration.configuration_id == configuration_id
        assert manifest.lineage.configuration.config_hash == configuration.config_hash
        assert manifest.lineage.strategy.strategy_id == "fixture_strategy"
        assert manifest.lineage.strategy.strategy_version == "1.0.0"
        assert manifest.lineage.runtime.runtime_identity == _runtime().runtime_identity

        document = json.loads(service.serialize_run_manifest(manifest))
        assert document["lineage"]["configuration"]["config_hash"] == configuration.config_hash
        assert (
            document["lineage"]["data"]["provenance_record_identity"]
            == manifest.lineage.data.provenance_record_identity
        )
        assert document["lineage"]["data"]["dataset_manifest_reference"] == (
            "data/manifests/fixture.json"
        )
        assert document["lineage"]["runtime"]["git"]["commit_sha"] == "a" * 40
        assert document["lineage"]["runtime"]["git"]["dirty_fingerprint"] == "clean-fingerprint"
        assert document["lineage"]["runtime"]["packages"]["fingerprint"] == "package-fingerprint"
    finally:
        service.close()


def test_run_configuration_and_strategy_mismatches_are_rejected(tmp_path: Path) -> None:
    service, configuration_id = _service_with_lineage_run(tmp_path)
    try:
        service.connection.execute("PRAGMA foreign_keys = OFF")
        service.connection.execute(
            "UPDATE experiment_runs SET strategy_version='9.9.9' WHERE run_id=?",
            ("lineage-run",),
        )
        service.connection.commit()
        with pytest.raises(RuntimeError, match="missing strategy"):
            service.build_run_manifest("lineage-run")

        service.connection.execute(
            "UPDATE experiment_runs SET strategy_version='1.0.0' WHERE run_id=?",
            ("lineage-run",),
        )
        service.connection.execute(
            "UPDATE experiment_configurations SET strategy_version='9.9.9' WHERE configuration_id=?",
            (configuration_id,),
        )
        service.connection.commit()
        with pytest.raises(ValueError, match="disagree"):
            service.build_run_manifest("lineage-run")
    finally:
        service.close()


def test_dataset_and_normalization_identities_are_stable_and_distinguishable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, _ = _service_with_lineage_run(tmp_path / "first", run_id="first-run")
    second, _ = _service_with_lineage_run(tmp_path / "second", run_id="second-run")
    changed_counts = _provenance(
        "changed-counts-run",
        validation_summary_json=_validation_summary(missing_close_count=1),
    )
    changed_source = _provenance("changed-source-run", checksum="different-checksum")
    third, _ = _service_with_lineage_run(
        tmp_path / "third", run_id="changed-counts-run", provenance=changed_counts
    )
    fourth, _ = _service_with_lineage_run(
        tmp_path / "third", run_id="changed-source-run", provenance=changed_source
    )
    try:
        first_lineage = first.get_run_lineage("first-run")
        second_lineage = second.get_run_lineage("second-run")
        counts_lineage = third.get_run_lineage("changed-counts-run")
        source_lineage = fourth.get_run_lineage("changed-source-run")

        assert first_lineage.data.dataset_identity == second_lineage.data.dataset_identity
        assert first_lineage.normalization.normalization_identity == (
            second_lineage.normalization.normalization_identity
        )
        assert first_lineage.data.provenance_record_identity != (
            counts_lineage.data.provenance_record_identity
        )
        assert first_lineage.data.dataset_identity == counts_lineage.data.dataset_identity
        assert first_lineage.normalization.normalization_identity == (
            counts_lineage.normalization.normalization_identity
        )
        assert first_lineage.data.dataset_identity != source_lineage.data.dataset_identity
        assert first_lineage.data.provenance_record_identity != (
            source_lineage.data.provenance_record_identity
        )
        assert first_lineage.normalization.normalization_identity == (
            source_lineage.normalization.normalization_identity
        )

        monkeypatch.setattr(
            service_module,
            "NORMALIZATION_CONTRACT_VERSION",
            "data_provenance.normalization.v2",
        )
        changed_contract = first.get_run_lineage("first-run")
        assert first_lineage.normalization.normalization_identity != (
            changed_contract.normalization.normalization_identity
        )
        assert first_lineage.data.dataset_identity != changed_contract.data.dataset_identity
    finally:
        first.close()
        second.close()
        third.close()
        fourth.close()


def test_execution_assumption_identity_is_exact_and_mismatch_is_rejected(tmp_path: Path) -> None:
    execution = {"fees": 0.02, "slippage": 0.01, "mode": "fixture"}
    service, _ = _service_with_lineage_run(tmp_path, execution=execution)
    try:
        lineage = service.get_run_lineage("lineage-run")
        assert lineage.execution_assumptions.execution_assumptions_identity
        with transaction(service.connection):
            service.connection.execute(
                "UPDATE execution_assumptions SET assumptions_json=? WHERE run_id=?",
                (canonical_json({"fees": 999}), "lineage-run"),
            )
        with pytest.raises(ValueError, match="execution assumptions disagree"):
            service.build_run_manifest("lineage-run")
    finally:
        service.close()


def test_manifest_checksum_includes_lineage_but_excludes_mutable_state(tmp_path: Path) -> None:
    service, _ = _service_with_lineage_run(tmp_path)
    try:
        manifest = service.build_run_manifest("lineage-run", created_at="2026-07-13T00:00:00Z")
        checksum = service.run_manifest_checksum(manifest)
        service.update_artifact_availability(manifest.artifacts[0].artifact_id, ArtifactAvailability.MISSING)
        availability_manifest = service.build_run_manifest(
            "lineage-run", created_at="2026-07-14T00:00:00Z"
        )
        assert service.run_manifest_checksum(availability_manifest) == checksum

        service.update_strategy_lifecycle(
            "fixture_strategy",
            "1.0.0",
            lifecycle=StrategyLifecycle.WATCHLIST,
            active=False,
        )
        strategy_manifest = service.build_run_manifest(
            "lineage-run", created_at="2026-07-15T00:00:00Z"
        )
        assert service.run_manifest_checksum(strategy_manifest) == checksum

        with transaction(service.connection):
            service.connection.execute(
                "UPDATE data_provenance SET checksum=? WHERE run_id=?",
                ("changed-dataset", "lineage-run"),
            )
        changed_manifest = service.build_run_manifest(
            "lineage-run", created_at="2026-07-16T00:00:00Z"
        )
        assert service.run_manifest_checksum(changed_manifest) != checksum
    finally:
        service.close()


def test_package_fingerprint_is_independent_of_order() -> None:
    first = service_module.installed_package_fingerprint(
        (("Pandas", "2.2.0"), ("vectorbtpro", "2026.1.0"), ("my_pkg", "1"))
    )
    second = service_module.installed_package_fingerprint(
        (("my-pkg", "1"), ("VectorBTPro", "2026.1.0"), ("pandas", "2.2.0"))
    )
    assert first == second


def test_package_version_change_alters_runtime_identity() -> None:
    first_packages, _ = service_module.installed_package_fingerprint(
        (("pandas", "2.2.0"),)
    )
    second_packages, _ = service_module.installed_package_fingerprint(
        (("pandas", "2.2.1"),)
    )
    first = _runtime(
        runtime_identity=service_module._identity({"package_fingerprint": first_packages}),
        package_fingerprint=first_packages,
    )
    second = _runtime(
        runtime_identity=service_module._identity({"package_fingerprint": second_packages}),
        package_fingerprint=second_packages,
    )
    assert first.package_fingerprint != second.package_fingerprint
    assert first.runtime_identity != second.runtime_identity


def test_git_commit_change_alters_runtime_identity() -> None:
    first = _runtime(
        runtime_identity=service_module._identity({"git_commit_sha": "a" * 40}),
        git_commit_sha="a" * 40,
    )
    second = _runtime(
        runtime_identity=service_module._identity({"git_commit_sha": "b" * 40}),
        git_commit_sha="b" * 40,
    )
    assert first.git_commit_sha != second.git_commit_sha
    assert first.runtime_identity != second.runtime_identity


def test_git_lineage_prefers_real_git_commit_over_build_revision(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    (repo / ".qf-build-revision").write_text("b" * 40, encoding="ascii")

    lineage = service_module._git_lineage(repo)

    assert lineage["commit_sha"] != "b" * 40
    assert len(lineage["commit_sha"]) == 40
    assert lineage["commit_available"] is True


@pytest.mark.parametrize("contents", [None, "not-a-revision\n", "A" * 40])
def test_git_lineage_rejects_missing_or_malformed_build_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str | None
) -> None:
    repo = tmp_path / "image-root"
    repo.mkdir()
    if contents is not None:
        (repo / ".qf-build-revision").write_text(contents, encoding="ascii")
    monkeypatch.setattr(service_module, "_git_output", lambda *args, **kwargs: None)

    lineage = service_module._git_lineage(repo)

    assert lineage["commit_sha"] is None
    assert lineage["commit_available"] is False
    assert lineage["dirty_state"] == "unavailable"
    assert lineage["dirty_available"] is False


def test_valid_build_revision_changes_runtime_lineage_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / ".qf-build-revision").write_text("a" * 40, encoding="ascii")
    (second / ".qf-build-revision").write_text("b" * 40, encoding="ascii")
    monkeypatch.setattr(service_module, "_git_output", lambda *args, **kwargs: None)

    first_lineage = service_module._git_lineage(first)
    second_lineage = service_module._git_lineage(second)

    assert first_lineage["commit_sha"] == "a" * 40
    assert second_lineage["commit_sha"] == "b" * 40
    assert first_lineage["dirty_state"] == second_lineage["dirty_state"] == "unavailable"
    assert service_module._identity(first_lineage) != service_module._identity(second_lineage)


def test_dirty_fingerprint_changes_for_different_tracked_contents(tmp_path: Path) -> None:
    first_repo = _git_repo(tmp_path / "first")
    second_repo = _git_repo(tmp_path / "second")
    (first_repo / "tracked.txt").write_text("first dirty content\n", encoding="utf-8")
    (second_repo / "tracked.txt").write_text("second dirty content\n", encoding="utf-8")

    first = service_module._git_lineage(first_repo)
    second = service_module._git_lineage(second_repo)

    assert first["dirty_state"] == "dirty"
    assert second["dirty_state"] == "dirty"
    assert first["dirty_entry_count"] == second["dirty_entry_count"] == 1
    assert first["dirty_fingerprint"] != second["dirty_fingerprint"]


def test_dirty_fingerprint_is_independent_of_file_order(tmp_path: Path) -> None:
    first_repo = _git_repo(tmp_path / "first")
    second_repo = _git_repo(tmp_path / "second")

    (first_repo / "a.txt").write_text("a\n", encoding="utf-8")
    (first_repo / "b.txt").write_text("b\n", encoding="utf-8")
    (second_repo / "b.txt").write_text("b\n", encoding="utf-8")
    (second_repo / "a.txt").write_text("a\n", encoding="utf-8")

    first = service_module._git_lineage(first_repo)
    second = service_module._git_lineage(second_repo)

    assert first["dirty_entry_count"] == second["dirty_entry_count"] == 2
    assert first["dirty_fingerprint"] == second["dirty_fingerprint"]


def test_untracked_file_contents_affect_dirty_fingerprint(tmp_path: Path) -> None:
    first_repo = _git_repo(tmp_path / "first")
    second_repo = _git_repo(tmp_path / "second")
    (first_repo / "untracked.txt").write_text("alpha\n", encoding="utf-8")
    (second_repo / "untracked.txt").write_text("beta\n", encoding="utf-8")

    first = service_module._git_lineage(first_repo)
    second = service_module._git_lineage(second_repo)

    assert first["dirty_entry_count"] == second["dirty_entry_count"] == 1
    assert first["dirty_fingerprint"] != second["dirty_fingerprint"]


def test_dirty_fingerprint_lineage_excludes_absolute_repository_paths(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    (repo / "untracked.txt").write_text("alpha\n", encoding="utf-8")

    lineage = service_module._git_lineage(repo)
    serialized = json.dumps(lineage, sort_keys=True)

    assert str(repo) not in serialized
    assert lineage["dirty_fingerprint"]


def test_clean_worktree_dirty_fingerprint_is_deterministic(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)

    first = service_module._git_lineage(repo)
    second = service_module._git_lineage(repo)

    assert first["dirty_state"] == "clean"
    assert first["dirty_entry_count"] == 0
    assert first["dirty_fingerprint"] == second["dirty_fingerprint"]


def test_dirty_worktree_state_is_represented_deterministically(tmp_path: Path) -> None:
    service, _ = _service_with_lineage_run(
        tmp_path,
        runtime_lineage=_runtime(
            git_dirty_state="dirty",
            git_dirty_entry_count=2,
            git_dirty_fingerprint="dirty-fingerprint",
        ),
    )
    try:
        document = json.loads(service.serialize_run_manifest(service.build_run_manifest("lineage-run")))
        assert document["lineage"]["runtime"]["git"]["dirty_state"] == "dirty"
        assert document["lineage"]["runtime"]["git"]["dirty_available"] is True
        assert document["lineage"]["runtime"]["git"]["dirty_entry_count"] == 2
        assert document["lineage"]["runtime"]["git"]["dirty_fingerprint"] == "dirty-fingerprint"
    finally:
        service.close()


def test_runtime_lineage_omits_timestamps_and_prohibited_machine_values(tmp_path: Path) -> None:
    prohibited = {
        "2026-07-13T00:00:00Z",
        "machine-user",
        "/home/machine-user",
        "hostname-fixture",
        "127.0.0.1",
        "process_id",
        "SECRET_TOKEN",
    }
    service, _ = _service_with_lineage_run(tmp_path)
    try:
        document = json.loads(
            service.serialize_run_manifest(
                service.build_run_manifest("lineage-run", created_at="2026-07-13T00:00:00Z")
            )
        )
        runtime_text = json.dumps(document["lineage"]["runtime"], sort_keys=True)
        for value in prohibited:
            assert value not in runtime_text
    finally:
        service.close()


def test_missing_git_or_vectorbtpro_information_is_deterministic(tmp_path: Path) -> None:
    missing = _runtime(
        git_commit_sha=None,
        git_commit_available=False,
        git_dirty_state="unavailable",
        git_dirty_available=False,
        git_dirty_entry_count=None,
        git_dirty_fingerprint=None,
        vectorbtpro_version=None,
        vectorbtpro_available=False,
    )
    service, _ = _service_with_lineage_run(tmp_path, runtime_lineage=missing)
    try:
        document = json.loads(service.serialize_run_manifest(service.build_run_manifest("lineage-run")))
        runtime = document["lineage"]["runtime"]
        assert runtime["git"] == {
            "commit_sha": None,
            "commit_available": False,
            "dirty_state": "unavailable",
            "dirty_available": False,
            "dirty_entry_count": None,
            "dirty_fingerprint": None,
        }
        assert runtime["vectorbtpro"] == {
            "version": None,
            "available": False,
        }
    finally:
        service.close()


def test_runtime_lineage_is_frozen_at_run_creation(tmp_path: Path) -> None:
    current = {
        "value": _runtime(
            git_commit_sha="a" * 40,
            package_fingerprint="packages-created",
            python_version="3.12.0",
        )
    }

    service, _ = _service_with_lineage_run(
        tmp_path,
        runtime_lineage_provider=lambda: current["value"],
    )
    current["value"] = _runtime(
        git_commit_sha="b" * 40,
        package_fingerprint="packages-later",
        python_version="3.13.0",
    )
    try:
        manifest = service.build_run_manifest("lineage-run")
        assert manifest.lineage is not None
        assert len(manifest.lineage.runtime.runtime_identity) == 64
        assert all(character in '0123456789abcdef' for character in manifest.lineage.runtime.runtime_identity)
        assert manifest.lineage.runtime.git_commit_sha == "a" * 40
        assert manifest.lineage.runtime.package_fingerprint == "packages-created"
        assert manifest.lineage.runtime.python_version == "3.12.0"
    finally:
        service.close()


def test_reconstructed_manifest_after_restart_uses_frozen_runtime_lineage(tmp_path: Path) -> None:
    database = tmp_path / "state" / "runtime-restart.sqlite3"
    source, _ = _service_with_lineage_run(
        tmp_path,
        run_id="lineage-run",
        runtime_lineage=_runtime(),
    )
    source_database = tmp_path / "state" / "lineage-run.sqlite3"
    source.close()
    source_database.replace(database)

    restarted = PersistenceService(
        database,
        runtime_lineage_provider=lambda: _runtime(
            git_commit_sha="b" * 40,
            package_fingerprint="packages-after-restart",
            python_version="3.13.0",
        ),
    )
    try:
        manifest = restarted.build_run_manifest("lineage-run")
        assert manifest.lineage is not None
        assert len(manifest.lineage.runtime.runtime_identity) == 64
        assert all(character in '0123456789abcdef' for character in manifest.lineage.runtime.runtime_identity)
    finally:
        restarted.close()


def test_runtime_lineage_changes_manifest_checksum(tmp_path: Path) -> None:
    first, _ = _service_with_lineage_run(
        tmp_path / "first",
        runtime_lineage=_runtime(),
    )
    second, _ = _service_with_lineage_run(
        tmp_path / "second",
        runtime_lineage=_runtime(git_commit_sha="b" * 40),
    )
    try:
        assert first.run_manifest_checksum(first.build_run_manifest("lineage-run")) != (
            second.run_manifest_checksum(second.build_run_manifest("lineage-run"))
        )
    finally:
        first.close()
        second.close()


def test_persisted_lineage_survives_restart_and_conflicts_fail(tmp_path: Path) -> None:
    database = tmp_path / "state" / "lineage.sqlite3"
    service, _ = _service_with_lineage_run(tmp_path, run_id="lineage-run")
    source_database = tmp_path / "state" / "lineage-run.sqlite3"
    service.close()
    source_database.replace(database)

    service = PersistenceService(database, runtime_lineage_provider=lambda: _runtime())
    try:
        manifest = service.build_run_manifest("lineage-run", created_at="2026-07-13T00:00:00Z")
        service.persist_run_manifest(manifest)
        service.persist_run_manifest(manifest)
        expected = service.read_persisted_run_manifest("lineage-run")
        assert expected is not None
    finally:
        service.close()

    restarted = PersistenceService(database, runtime_lineage_provider=lambda: _runtime())
    try:
        document = restarted.read_persisted_run_manifest_document("lineage-run")
        assert document is not None
        assert document["lineage"]["configuration"]["configuration_id"]
        assert document["lineage"]["runtime"]["runtime_identity"] == _runtime().runtime_identity
        reconstructed = restarted.build_run_manifest(
            "lineage-run", created_at="2026-07-14T00:00:00Z"
        )
        assert restarted.run_manifest_checksum(reconstructed) == expected[1]

        with transaction(restarted.connection):
            restarted.connection.execute(
                "UPDATE data_provenance SET checksum=? WHERE run_id=?",
                ("conflicting-dataset", "lineage-run"),
            )
        with pytest.raises(ValueError, match="conflicts"):
            restarted.persist_run_manifest(restarted.build_run_manifest("lineage-run"))
    finally:
        restarted.close()


def test_v3_database_migrates_and_version_one_and_two_manifest_rows_remain_readable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state" / "v3.sqlite3"
    connection = database_module.connect(path)
    try:
        database_module._migrate_empty_to_v1(connection)
        database_module._migrate_v1_to_v2(connection)
        database_module._migrate_v2_to_v3(connection)
        connection.execute(
            "INSERT INTO strategies VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy",
                "1",
                "Legacy",
                "legacy",
                "infrastructure_fixture",
                1,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO strategies VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-v2",
                "2",
                "Legacy V2",
                "legacy v2",
                "infrastructure_fixture",
                1,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO experiment_configurations VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy-config", "legacy", "legacy", "1", "{}", "legacy-hash", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO experiment_configurations VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-v2-config",
                "legacy-v2",
                "legacy-v2",
                "2",
                "{}",
                "legacy-v2-hash",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO experiment_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-run", "legacy-config", "legacy", "1", "fixture", "created", None, None, None, "{}", "2026-01-01T00:00:00Z", 0),
        )
        connection.execute(
            "INSERT INTO experiment_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-v2-run",
                "legacy-v2-config",
                "legacy-v2",
                "2",
                "fixture",
                "created",
                None,
                None,
                None,
                "{}",
                "2026-01-01T00:00:00Z",
                0,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    migrated = initialize_database(path)
    try:
        migrated.execute(
            """
            INSERT INTO run_manifests
            (run_id, schema_version, manifest_json, content_checksum, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "legacy-run",
                1,
                canonical_json(
                    {
                        "manifest_schema_version": 1,
                        "run_id": "legacy-run",
                        "configuration_id": "legacy-config",
                        "strategy_id": "legacy",
                        "strategy_version": "1",
                        "artifacts": [],
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ),
                "legacy-checksum",
                "2026-01-01T00:00:00Z",
            ),
        )
        migrated.execute(
            """
            INSERT INTO run_manifests
            (run_id, schema_version, manifest_json, content_checksum, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "legacy-v2-run",
                2,
                canonical_json(
                    {
                        "manifest_schema_version": 2,
                        "run_id": "legacy-v2-run",
                        "configuration_id": "legacy-v2-config",
                        "strategy_id": "legacy-v2",
                        "strategy_version": "2",
                        "lineage": {
                            "configuration": {
                                "configuration_id": "legacy-v2-config",
                                "config_hash": "legacy-v2-hash",
                            },
                            "strategy": {
                                "strategy_id": "legacy-v2",
                                "strategy_version": "2",
                            },
                            "data": {},
                            "normalization": {},
                            "execution_assumptions": {},
                        },
                        "artifacts": [],
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ),
                "legacy-v2-checksum",
                "2026-01-01T00:00:00Z",
            ),
        )
        migrated.commit()
        assert migrated.execute("SELECT schema_version FROM schema_metadata").fetchone()[
            "schema_version"
        ] == database_module.LATEST_SCHEMA_VERSION
    finally:
        migrated.close()

    service = PersistenceService(path)
    try:
        persisted = service.read_persisted_run_manifest_document("legacy-run")
        assert persisted is not None
        assert persisted["manifest_schema_version"] == 1
        assert "lineage" not in persisted
        persisted_v2 = service.read_persisted_run_manifest_document("legacy-v2-run")
        assert persisted_v2 is not None
        assert persisted_v2["manifest_schema_version"] == 2
        assert "runtime" not in persisted_v2["lineage"]
    finally:
        service.close()


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    (
        ("git", "commit_sha", "b" * 40),
        ("packages", "fingerprint", "tampered-package-fingerprint"),
        ("python", "version", "9.9.9"),
    ),
)
def test_stored_runtime_lineage_rejects_tampered_fields(
    section: str,
    field: str,
    replacement: object,
) -> None:
    document = service_module.runtime_lineage_document(_runtime())
    document[section][field] = replacement

    with pytest.raises(
        ValueError,
        match="runtime lineage identity does not match canonical content",
    ):
        service_module._runtime_lineage_from_document(document)


def test_stored_runtime_lineage_rejects_tampered_identity() -> None:
    document = service_module.runtime_lineage_document(_runtime())
    document["runtime_identity"] = "0" * 64

    with pytest.raises(
        ValueError,
        match="runtime lineage identity does not match canonical content",
    ):
        service_module._runtime_lineage_from_document(document)


def test_valid_stored_runtime_lineage_identity_is_accepted() -> None:
    expected = _runtime()
    document = service_module.runtime_lineage_document(expected)

    reconstructed = service_module._runtime_lineage_from_document(document)

    assert reconstructed == expected
