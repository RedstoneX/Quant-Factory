"""Deterministic fixtures and strict CI-lane accounting for tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from market_data.calendars import get_exchange_calendar
from market_data.models import MarketDataConfig


LICENSED_VECTORBT_NODE_IDS = frozenset(
    {
        "tests/test_deflated_sharpe.py::test_matches_library_on_fixture",
        "tests/test_performance_summary_artifact.py::test_snapshot_keeps_summary_after_portfolio_is_released",
        "tests/test_performance_summary_artifact.py::test_summary_has_all_long_short_with_json_safe_values",
        "tests/test_oos_trades_saved.py::test_oos_test_partition_portfolio_is_observed_once",
        "tests/test_walk_forward_splitter_vbt.py::test_full_history_signals_differ_from_slice_only_in_the_warm_up",
        "tests/test_walk_forward_splitter_vbt.py::test_window_result_does_not_depend_on_later_bars",
        "tests/test_walk_forward_splitter_vbt.py::test_whole_range_matches_a_plain_run",
        "tests/test_walk_forward_splitter_vbt.py::test_signals_are_generated_once_per_parameter_set",
        "tests/test_deflated_sharpe.py::test_flat_settings_are_undefined",
        "tests/test_deflated_sharpe.py::test_selected_column_alone_is_undefined",
        "tests/test_deflated_sharpe.py::test_walk_forward_counts_every_setting_tried_not_per_fold",
        "tests/test_overfitting_pbo.py::test_noise_grid_is_near_one_half",
        "tests/test_rule_language_exits.py::test_level_stop_and_target_fill_in_vectorbt",
        "tests/test_rule_language_exits.py::test_breakeven_then_trail_in_vectorbt",
        "tests/test_overfitting_pbo.py::test_dominant_setting_has_low_pbo",
        "tests/test_overfitting_pbo.py::test_single_setting_is_rejected",
        "tests/test_overfitting_pbo.py::test_experiment_records_pbo_next_to_deflated_sharpe_and_never_screens",
        "tests/test_deflated_sharpe.py::test_deflated_sharpe_is_record_only",
        "tests/test_rule_engine_vectorized.py::test_library_indicators_batch_equals_per_setting_reference",
        "tests/test_rule_engine_vectorized.py::test_core_features_batch_equals_per_setting_reference",
        "tests/test_rule_engine_vectorized.py::test_single_trade_and_no_exit_rules_batch_equals_reference",
        "tests/test_rule_language_bar_sizes.py::test_five_minute_spec_is_identical_to_main",
        "tests/test_rule_language_bar_sizes.py::test_one_minute_after_bars_and_flat_at_count_minutes",
        "tests/test_rule_language_bar_sizes.py::test_one_minute_entry_and_at_time_exit_fire_on_the_right_minute",
        "tests/test_rule_language_exits.py::test_exit_when_closes_the_trade_for_its_side_only",
        "tests/test_rule_language_exits.py::test_exit_when_exit_allows_a_new_entry",
        "tests/test_rule_language_exits.py::test_exit_when_never_fires_on_the_entry_bar_and_ignores_the_other_side",
        "tests/test_rule_language_stops.py::test_legacy_both_or_neither_specs_are_byte_identical_to_main",
        "tests/test_rule_spec_strategy.py::test_at_time_and_flat_at_exits",
        "tests/test_rule_spec_strategy.py::test_golden_mes_sma_10_30_matches_hand_written_candidate",
        "tests/test_rule_spec_strategy.py::test_max_trades_and_no_same_bar_entry_and_exit",
        "tests/test_rule_spec_strategy.py::test_opposite_signal_exit_without_same_bar_reversal",
        "tests/test_rule_spec_strategy.py::test_run_entry_with_after_bars_exit_and_dynamic_side",
        "tests/test_rule_spec_strategy.py::test_without_flat_at_positions_hold_overnight_until_the_td_stop",
        "tests/test_rule_language_indicators.py::test_across_sessions_runs_through_the_session_boundary",
        "tests/test_rule_language_indicators.py::test_guide_example_condition_is_valid_and_evaluates",
        "tests/test_rule_language_indicators.py::test_indicator_matches_hand_computation",
        "tests/test_rule_language_indicators.py::test_indicators_are_causal",
        "tests/test_rule_language_indicators.py::test_indicators_compose_with_existing_operators",
        "tests/test_rule_language_indicators.py::test_variable_parameters_equal_literals",
        "tests/test_execution_assumptions.py::test_execution_comparison_reports_metric_and_ranking_change",
        "tests/test_execution_assumptions.py::test_futures_costs_scale_with_contract_quantity",
        "tests/test_execution_assumptions.py::test_long_futures_fee_and_slippage_direction",
        "tests/test_execution_assumptions.py::test_next_bar_portfolio_uses_next_open_price",
        "tests/test_execution_assumptions.py::test_rsi_percentage_fee_and_slippage_behavior_is_unchanged",
        "tests/test_execution_assumptions.py::test_rsi_signal_prefix_is_unchanged_by_future_rows",
        "tests/test_execution_assumptions.py::test_same_bar_close_mode_preserves_unshifted_comparison",
        "tests/test_execution_assumptions.py::test_short_futures_fee_and_slippage_direction",
        "tests/test_experiment_runner.py::test_portfolio_metrics_and_result_provenance",
        "tests/test_experiment_runner.py::test_session_metrics_use_last_observation_only_when_portfolio_is_flat",
        "tests/test_experiment_runner.py::test_session_metrics_exclude_wholly_absent_exchange_session",
        "tests/test_experiment_runner.py::test_session_metrics_count_a_final_bar_ending_at_the_close_as_complete",
        "tests/test_experiment_runner.py::test_flat_session_metrics_are_truthfully_screened_out",
        "tests/test_experiment_runner.py::test_session_metrics_use_completed_exchange_sessions_not_overnight_bars",
        "tests/test_experiment_metrics_vectorized.py::test_multi_column_with_half_day_matches_frozen",
        "tests/test_experiment_metrics_vectorized.py::test_missing_closing_bar_and_absent_session_flat_matches_frozen",
        "tests/test_experiment_metrics_vectorized.py::test_flat_column_mix_in_one_frame_matches_frozen",
        "tests/test_parameter_sweep_one_pass.py::test_experiment_outputs_equal_one_simulation_per_setting",
        "tests/test_parameter_sweep_one_pass.py::test_one_pass_columns_equal_single_setting_portfolios",
        "tests/test_runner_memory.py::test_chunked_sweep_is_identical_to_one_call",
        "tests/test_runner_memory.py::test_locked_column_equals_resimulating_the_locked_setting",
        "tests/test_milestone21c_spym_fixture.py::test_spym_fixture_rerun_keeps_deterministic_metrics_and_trades",
        "tests/test_milestone21c_spym_fixture.py::test_spym_saved_configuration_launches_vectorbt_and_persists_lineage",
        "tests/test_rsi_mean_reversion.py::test_common_interface_signal_result_matches_preserved_rsi_rules",
        "tests/test_rule_language_catalog.py::test_catalogue_comes_from_the_library_metadata",
        "tests/test_rule_language_catalog.py::test_every_named_operator_is_an_alias_of_a_usable_library_indicator",
        "tests/test_rule_language_catalog.py::test_library_node_equals_the_named_operator",
        "tests/test_rule_language_catalog.py::test_library_node_restarts_each_session_and_is_causal",
        "tests/test_rule_language_catalog.py::test_library_node_parameters_accept_variables",
        "tests/test_rule_language_catalog.py::test_library_node_rejects_bad_names_params_and_outputs",
        "tests/test_rule_language_catalog.py::test_starter_kit_lists_the_library_catalogue",
        "tests/test_splitter_library_parity.py::test_chronological_split_matches_library",
        "tests/test_splitter_library_parity.py::test_walk_forward_drop_matches_library",
        "tests/test_splitter_library_parity.py::test_walk_forward_include_extends_library_with_truncated_tail",
        "tests/test_candidate_setting_rebuild.py::test_rebuilt_setting_equals_the_saved_run_exactly",
    }
)

EXTERNAL_PREFECT_NODE_IDS = frozenset(
    {
        "tests/test_prefect_spike.py::test_live_external_prefect_retry_success_path",
        "tests/test_prefect_spike.py::test_live_external_prefect_timeout_path",
    }
)

CONTROLLED_MARKET_DATA_NODE_IDS = frozenset(
    {
        "tests/test_mes_opening_range_breakout.py::test_cataloged_mes_file_matches_committed_manifest",
        "tests/test_futures_profiles.py::test_manifest_passes_the_same_verified_data_check_as_mes",
    }
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--write-test-lane-inventory",
        metavar="PATH",
        help="validate every restricted marker and write the complete lane inventory",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "licensed_vectorbt: requires the real separately licensed VectorBT Pro engine",
    )
    config.addinivalue_line(
        "markers",
        "external_prefect: requires an already-running external Prefect server",
    )
    config.addinivalue_line(
        "markers",
        "controlled_market_data: requires the configured non-repository market-data file",
    )


def _base_node_id(node_id: str) -> str:
    return node_id.split("[", 1)[0]


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    marked_licensed: set[str] = set()
    marked_external: set[str] = set()
    marked_controlled_data: set[str] = set()
    for item in items:
        node_id = _base_node_id(item.nodeid)
        licensed = item.get_closest_marker("licensed_vectorbt") is not None
        external = item.get_closest_marker("external_prefect") is not None
        controlled_data = item.get_closest_marker("controlled_market_data") is not None
        if sum((licensed, external, controlled_data)) > 1:
            raise pytest.UsageError(f"test belongs to multiple restricted lanes: {item.nodeid}")
        if licensed:
            marked_licensed.add(node_id)
            if node_id not in LICENSED_VECTORBT_NODE_IDS:
                raise pytest.UsageError(
                    f"unapproved licensed VectorBT marker: {item.nodeid}"
                )
        if external:
            marked_external.add(node_id)
            if node_id not in EXTERNAL_PREFECT_NODE_IDS:
                raise pytest.UsageError(
                    f"unapproved external Prefect marker: {item.nodeid}"
                )
        if controlled_data:
            marked_controlled_data.add(node_id)
            if node_id not in CONTROLLED_MARKET_DATA_NODE_IDS:
                raise pytest.UsageError(
                    f"unapproved controlled market-data marker: {item.nodeid}"
                )

    inventory_path = config.getoption("--write-test-lane-inventory")
    if inventory_path is None:
        return
    missing_licensed = LICENSED_VECTORBT_NODE_IDS - marked_licensed
    missing_external = EXTERNAL_PREFECT_NODE_IDS - marked_external
    missing_controlled_data = CONTROLLED_MARKET_DATA_NODE_IDS - marked_controlled_data
    if missing_licensed or missing_external or missing_controlled_data:
        raise pytest.UsageError(
            "restricted test inventory is incomplete: "
            f"missing licensed={sorted(missing_licensed)}; "
            f"missing external={sorted(missing_external)}; "
            f"missing controlled_data={sorted(missing_controlled_data)}"
        )

    lanes = {
        "portable": [],
        "licensed_vectorbt": [],
        "external_prefect": [],
        "controlled_market_data": [],
    }
    for item in items:
        if item.get_closest_marker("licensed_vectorbt") is not None:
            lane = "licensed_vectorbt"
        elif item.get_closest_marker("external_prefect") is not None:
            lane = "external_prefect"
        elif item.get_closest_marker("controlled_market_data") is not None:
            lane = "controlled_market_data"
        else:
            lane = "portable"
        lanes[lane].append(item.nodeid)
    payload = {
        "schema_version": 1,
        "total": len(items),
        "counts": {lane: len(node_ids) for lane, node_ids in lanes.items()},
        "lanes": lanes,
    }
    Path(inventory_path).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def market_config(tmp_path) -> MarketDataConfig:
    return MarketDataConfig(
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="vectorbtpro.YFData.pull",
        interval="1 day",
        requested_start="2016-01-01",
        end_date_policy="Latest completed NYSE session available from provider",
        adjusted=True,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=tmp_path / "spy.csv",
        legacy_cache_paths=(tmp_path / "legacy.csv",),
    )


@pytest.fixture
def market_frame_factory(market_config):
    def make(start: str, end: str) -> pd.DataFrame:
        sessions = get_exchange_calendar(market_config).schedule(
            start_date=start,
            end_date=end,
        ).index
        index = sessions.tz_localize(market_config.market_timezone)
        values = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "Open": values,
                "High": values + 1,
                "Low": values - 1,
                "Close": values,
                "Volume": 1_000,
            },
            index=index,
        )

    return make


@pytest.fixture
def no_licensed_luck_score(monkeypatch):
    """The record-only luck score needs the licensed engine, which portable fakes replace."""
    monkeypatch.setattr("backtesting.experiments.runner._record_luck", lambda *args: (None, None))
