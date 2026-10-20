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
        "tests/test_luck_score_undefined.py::test_single_setting_grid_records_null_luck_and_persists",
        "tests/test_luck_score_undefined.py::test_single_session_dataset_records_undefined_luck_without_failing",
        "tests/test_data_as_of_session_clip.py::test_clipped_mid_session_window_passes_session_metrics",
        "tests/test_data_as_of_session_clip.py::test_early_close_window_passes_session_metrics",
        "tests/test_market_data_vbt.py::test_vbt_top_up_stores_exactly_what_legacy_stores",
        "tests/test_market_data_vbt.py::test_moved_last_bar_triggers_full_refetch",
        "tests/test_market_data_vbt.py::test_saved_vbt_file_holds_no_api_keys",
        "tests/test_market_data_vbt.py::test_pull_or_update_equals_a_fresh_full_pull",
        "tests/test_market_data_vbt.py::test_first_vbt_run_over_legacy_store_seeds_from_stored_bars_without_a_history_pull",
        "tests/test_market_data_vbt.py::test_changed_bar_two_sessions_back_is_rejected_after_seeding",
        "tests/test_market_data_vbt.py::test_newest_session_is_refetched_so_vendor_gap_fills_and_corrections_land",
        "tests/test_market_data_vbt.py::test_changed_bar_two_sessions_back_is_still_rejected",
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
        "tests/test_luck_daily_returns.py::test_daily_bars_score_bit_identically_to_the_bar_level_method",
        "tests/test_luck_daily_returns.py::test_minute_bars_score_on_each_days_closing_value",
        "tests/test_rule_language_exits.py::test_level_stop_and_target_fill_in_vectorbt",
        "tests/test_rule_signal_bar_stop.py::test_signal_bar_stop_fills_at_the_signal_bar_extreme_in_vectorbt",
        "tests/test_rule_signal_bar_stop.py::test_signal_bar_stop_sets_r_for_the_target_in_vectorbt",
        "tests/test_rule_flat_at_time.py::test_flat_at_closes_the_trade_at_that_time_at_the_open_in_vectorbt",
        "tests/test_rule_flat_at_time.py::test_flat_at_blocks_entries_from_that_time_but_at_time_does_not",
        "tests/test_rule_language_exits.py::test_breakeven_then_trail_in_vectorbt",
        "tests/test_overfitting_pbo.py::test_dominant_setting_has_low_pbo",
        "tests/test_overfitting_pbo.py::test_single_setting_is_rejected",
        "tests/test_overfitting_pbo.py::test_executor_memory_options_do_not_change_the_result",
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
        "tests/test_sweep_memory_parity.py::test_chunked_sweep_equals_one_all_settings_simulation",
        "tests/test_sweep_memory_parity.py::test_chunked_window_equals_one_all_settings_simulation",
        "tests/test_sweep_memory_parity.py::test_many_chunks_merge_in_settings_order",
        "tests/test_sweep_memory_parity.py::test_chunk_size_follows_bar_count",
        "tests/test_sweep_memory_parity.py::test_evicting_signal_cache_changes_nothing",
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
        "tests/test_auto_campaign_stock_profiles.py::test_whole_share_sizing_orders_whole_shares_with_all_cash",
        "tests/test_candidate_pipeline_runtime.py::test_real_runtime_path_reaches_protected_ready_and_replays_without_work",
        "tests/test_candidate_pipeline_runtime.py::test_persisted_robustness_merit_failure_is_scored_and_continues",
        "tests/test_candidate_pipeline_runtime.py::test_post_ack_stage_failure_is_terminal_and_never_reinvoked",
        "tests/test_candidate_screening_artifacts.py::test_metrics_artifact_persists_candidate_annualization",
        "tests/test_candidate_setting_rebuild.py::test_run_without_a_data_checksum_is_not_provable",
        "tests/test_candidate_setting_rebuild.py::test_changed_metrics_are_refused",
        "tests/test_candidate_setting_rebuild.py::test_unknown_setting_is_refused",
        "tests/test_execution_assumptions.py::test_result_records_actual_execution_assumptions",
        "tests/test_experiment_metrics_vectorized.py::test_missing_closing_bar_with_exposure_raises_same_error",
        "tests/test_experiment_runner.py::test_session_metrics_fail_closed_without_exact_closing_bar",
        "tests/test_experiment_runner.py::test_session_metrics_fail_closed_on_partial_final_session",
        "tests/test_experiment_runner.py::test_strategy_lookup_and_grid_execution",
        "tests/test_experiment_runner.py::test_invalid_parameters_are_recorded",
        "tests/test_experiment_runner.py::test_ranking_is_deterministic_on_ties",
        "tests/test_fixed_rule_cost_stress.py::test_fixed_rule_cost_stress_uses_higher_costs_as_gate",
        "tests/test_fixed_rule_cost_stress.py::test_mes_fixed_rule_stress_costs_are_unchanged",
        "tests/test_fixed_rule_cost_stress.py::test_whole_share_stress_doubles_slippage_and_keeps_fees",
        "tests/test_hygiene_gates.py::test_valid_inputs_pass_and_results_record_gate_status",
        "tests/test_low_frequency_walk_forward.py::test_fold_chronology_non_overlap_and_fixed_parameters",
        "tests/test_low_frequency_walk_forward.py::test_trade_floor_marks_insufficient_not_passed",
        "tests/test_low_frequency_walk_forward.py::test_failed_performance_is_distinct_from_insufficient_evidence",
        "tests/test_mes_overnight_gap_reversal.py::test_vectorbt_call_and_manual_cross_check_are_exact_and_fail_closed",
        "tests/test_mes_overnight_gap_reversal.py::test_execute_produces_one_screened_row_from_authoritative_daily_metrics",
        "tests/test_mes_overnight_gap_reversal_durable.py::test_preflight_saves_exact_configuration_without_persisting_secret",
        "tests/test_mes_overnight_gap_reversal_durable.py::test_screened_out_launch_persists_one_successful_screen_and_replay_is_noop",
        "tests/test_mes_vwap_orb_candidate.py::test_stop_orders_use_ohlc_and_conservative_stop_fill",
        "tests/test_out_of_sample.py::test_selection_excludes_test_and_lock_precedes_single_test_evaluation",
        "tests/test_out_of_sample.py::test_only_passing_training_shortlist_reaches_selection",
        "tests/test_out_of_sample.py::test_stable_tie_breaking_controls_shortlist_membership",
        "tests/test_out_of_sample.py::test_no_training_survivor_reason_leads_with_screen_rejection",
        "tests/test_out_of_sample.py::test_no_training_survivor_stops_before_selection_and_test",
        "tests/test_out_of_sample.py::test_no_selection_survivor_stops_before_lock_and_test",
        "tests/test_out_of_sample.py::test_held_out_values_cannot_change_selected_parameters",
        "tests/test_out_of_sample.py::test_report_records_split_lock_and_test_only_metrics",
        "tests/test_out_of_sample.py::test_unseen_gate_passes_on_net_return_without_a_sharpe_minimum",
        "tests/test_out_of_sample.py::test_unseen_gate_fails_when_test_net_return_is_not_positive",
        "tests/test_out_of_sample.py::test_unseen_gate_fails_when_every_setting_lost_money_on_training",
        "tests/test_robustness_evaluation.py::test_pipeline_adapter_evaluates_only_valid_candidates_with_same_assumptions",
        "tests/test_robustness_evaluation.py::test_zero_locked_return_marks_relative_degradation_unavailable",
        "tests/test_rsi_mean_reversion.py::test_signal_arrays_align_with_price_index",
        "tests/test_screening.py::test_experiment_preserves_passing_and_screened_rows",
        "tests/test_screening.py::test_invalid_parameters_remain_distinct_from_screening_failures",
        "tests/test_screening.py::test_screening_occurs_after_simulation_and_metrics",
        "tests/test_screening.py::test_complete_output_contains_screening_columns",
        "tests/test_spy_donchian_oos.py::test_training_failure_stops_before_selection_and_test",
        "tests/test_spy_donchian_oos.py::test_selection_failure_stops_before_lock_and_test",
        "tests/test_spy_donchian_oos.py::test_selection_failure_writes_no_lock_failure_artifact",
        "tests/test_spy_donchian_oos.py::test_lock_precedes_exactly_one_test_candidate_and_test_cannot_reselect",
        "tests/test_spy_donchian_oos.py::test_test_partition_values_cannot_change_shortlist_or_lock",
        "tests/test_spy_donchian_oos.py::test_schema_compatible_artifact_loads_for_robustness",
        "tests/test_spy_donchian_trend_breakout.py::test_baseline_runner_produces_exact_six_rows",
        "tests/test_spym_intraday_momentum.py::test_mixed_price_adapter_uses_entry_open_exit_close_and_conservative_costs",
        "tests/test_spym_intraday_momentum.py::test_completed_trade_validation_requires_one_closed_trade_per_eligible_session",
        "tests/test_spym_intraday_momentum.py::test_annualization_uses_only_eligible_daily_equity_and_252_zero_risk_free",
        "tests/test_spym_intraday_momentum_durable.py::test_durable_success_persists_one_dashboard_readable_row_and_integrity_manifest",
        "tests/test_spym_intraday_momentum_durable.py::test_durable_run_fails_before_artifacts_when_ranked_trade_metric_disagrees_with_ledger",
        "tests/test_spym_intraday_momentum_durable.py::test_artifact_write_failure_rolls_back_success_evidence",
        "tests/test_walk_forward.py::test_training_shortlist_and_locked_test_parameters",
        "tests/test_walk_forward.py::test_failed_training_fold_continues_without_selection_or_test",
        "tests/test_walk_forward.py::test_failed_selection_fold_never_evaluates_test",
        "tests/test_walk_forward.py::test_test_and_future_mutations_do_not_change_first_fold_selection",
        "tests/test_walk_forward.py::test_optional_selection_locks_best_passing_training_row",
        "tests/test_walk_forward.py::test_stability_and_aggregate_calculations_are_deterministic",
        "tests/test_walk_forward.py::test_report_contains_fold_provenance_and_failures",
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

