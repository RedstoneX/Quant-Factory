"""One saved setting is rebuilt on demand and proven equal to the stored run, or refused."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

import backtesting.experiments.runner as experiment_runner
import strategies.rsi_mean_reversion as rsi_strategy
from market_data import load_market_data
from orchestration.candidate_setting_rebuild import (
    NOT_PROVABLE,
    SettingRebuildRefused,
    load_saved_setting,
    prove_same_data,
    rebuild_portfolio,
    rebuild_setting,
)
from backtesting.robustness import ParameterNeighborhoodDefinition
from orchestration import CandidatePipelineRuntime
from persistence import PersistenceService, StrategyLifecycle
from strategies.rsi_mean_reversion import RSI_MEAN_REVERSION_SPEC
from tests.test_candidate_pipeline_runtime import FAKE_VECTORBT, _definition, _direct_pipeline_launcher

# RSI(7) on the shared sine fixture spans 35-77, so this setting trades (the shared default never does).
TRADING_SETTING = {"window": 7, "entry_threshold": 40, "exit_threshold": 70}


def _trading_runtime(tmp_path) -> CandidatePipelineRuntime:
    base = _definition(tmp_path)
    neighborhood = replace(
        base.validation.robustness_neighborhood,
        definitions=tuple(
            ParameterNeighborhoodDefinition(name, "explicit_values", explicit_values=(value - 5, value, value + 5))
            for name, value in TRADING_SETTING.items()
        ),
    )
    definition = replace(
        base,
        experiment=replace(base.experiment, parameter_combinations=(TRADING_SETTING,)),
        validation=replace(base.validation, robustness_neighborhood=neighborhood),
    )
    database = tmp_path / "state" / "factory.sqlite3"
    persistence = PersistenceService(database)
    try:
        spec = RSI_MEAN_REVERSION_SPEC
        persistence.register_strategy(
            strategy_id=spec.identity.strategy_id,
            strategy_version=spec.identity.version,
            display_name=spec.identity.name,
            description="Setting rebuild fixture",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        configuration = persistence.upsert_configuration(definition.configuration_document())
    finally:
        persistence.close()
    return CandidatePipelineRuntime(
        database=database,
        artifact_root=tmp_path / "artifacts",
        configuration_id=configuration.configuration_id,
        definition=definition,
        pipeline_launcher=_direct_pipeline_launcher,
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )


def _launched(tmp_path):
    runtime = _trading_runtime(tmp_path)
    launched = runtime.launch(idempotency_key="setting_rebuild_fixture")
    run_id = launched.launch.claim.run.run_id
    persistence = PersistenceService(runtime.database)
    try:
        row_id = persistence.results.list_parameter_results(run_id)[0].row_id
    finally:
        persistence.close()
    return runtime, run_id, row_id


def _saved_data(runtime, saved):
    definition = saved.definition
    return load_market_data(
        definition.experiment.market_data,
        now=pd.Timestamp(definition.validation.data_as_of),
        allow_download=False,
    ).data


@pytest.mark.licensed_vectorbt
def test_rebuilt_setting_equals_the_saved_run_exactly(tmp_path) -> None:
    runtime, run_id, row_id = _launched(tmp_path)
    saved = load_saved_setting(runtime.database, run_id, row_id)

    rebuilt = rebuild_portfolio(saved, _saved_data(runtime, saved))

    assert rebuilt.exact is True
    assert saved.stored_metrics["number_of_trades"] > 0
    assert float(rebuilt.portfolio.total_return) == saved.stored_metrics["total_return"]
    assert int(rebuilt.portfolio.trades.count()) == saved.stored_metrics["number_of_trades"]
    assert rebuilt.warnings == ()
    # The fixture is Yahoo-sourced, so the cached public entry point must not claim exactness.
    assert rebuild_setting(str(runtime.database), run_id, row_id).reason == NOT_PROVABLE


def _fake_engine(monkeypatch) -> None:
    monkeypatch.setattr(experiment_runner, "require_vectorbtpro", lambda: FAKE_VECTORBT)
    monkeypatch.setattr(rsi_strategy, "require_vectorbtpro", lambda: FAKE_VECTORBT)


def test_run_without_a_data_checksum_is_not_provable(tmp_path, monkeypatch, no_licensed_luck_score) -> None:
    _fake_engine(monkeypatch)
    runtime, run_id, row_id = _launched(tmp_path)

    result = rebuild_setting(str(runtime.database), run_id, row_id)

    assert (result.exact, result.reason, result.portfolio) == (False, NOT_PROVABLE, None)


def test_changed_metrics_are_refused(tmp_path, monkeypatch, no_licensed_luck_score) -> None:
    _fake_engine(monkeypatch)
    runtime, run_id, row_id = _launched(tmp_path)
    saved = load_saved_setting(runtime.database, run_id, row_id)
    tampered = replace(saved, stored_metrics=saved.stored_metrics | {"number_of_trades": -1})

    with pytest.raises(SettingRebuildRefused, match="differs from the saved run"):
        rebuild_portfolio(tampered, _saved_data(runtime, saved))


def test_unknown_setting_is_refused(tmp_path, monkeypatch, no_licensed_luck_score) -> None:
    _fake_engine(monkeypatch)
    runtime, run_id, _ = _launched(tmp_path)

    with pytest.raises(KeyError):
        load_saved_setting(runtime.database, run_id, "no-such-row")


@pytest.mark.parametrize(("checksum", "rows"), [("other", 5), ("abc", 6)])
def test_different_market_data_is_refused(checksum, rows) -> None:
    saved = SimpleNamespace(provenance_checksum="abc", provenance_row_count=5)

    with pytest.raises(SettingRebuildRefused, match="market data differs"):
        prove_same_data(SimpleNamespace(checksum=checksum, row_count=rows), saved)


def test_identical_market_data_is_accepted() -> None:
    saved = SimpleNamespace(provenance_checksum="abc", provenance_row_count=5)

    prove_same_data(SimpleNamespace(checksum="abc", row_count=5), saved)
