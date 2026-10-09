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
        "tests/test_execution_assumptions.py::test_execution_comparison_reports_metric_and_ranking_change",
        "tests/test_execution_assumptions.py::test_futures_costs_scale_with_contract_quantity",
        "tests/test_execution_assumptions.py::test_long_futures_fee_and_slippage_direction",
        "tests/test_execution_assumptions.py::test_next_bar_portfolio_uses_next_open_price",
        "tests/test_execution_assumptions.py::test_rsi_percentage_fee_and_slippage_behavior_is_unchanged",
        "tests/test_execution_assumptions.py::test_rsi_signal_prefix_is_unchanged_by_future_rows",
        "tests/test_execution_assumptions.py::test_same_bar_close_mode_preserves_unshifted_comparison",
        "tests/test_execution_assumptions.py::test_short_futures_fee_and_slippage_direction",
        "tests/test_experiment_runner.py::test_portfolio_metrics_and_result_provenance",
        "tests/test_milestone21c_spym_fixture.py::test_spym_fixture_rerun_keeps_deterministic_metrics_and_trades",
        "tests/test_milestone21c_spym_fixture.py::test_spym_saved_configuration_launches_vectorbt_and_persists_lineage",
        "tests/test_rsi_mean_reversion.py::test_common_interface_signal_result_matches_preserved_rsi_rules",
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
