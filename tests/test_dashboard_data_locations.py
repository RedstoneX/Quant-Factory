"""The dashboard service reads market data through host paths, not the container paths."""

from pathlib import Path

from market_data.catalog import load_data_locations

HOST_CONFIG = Path("deployment/dashboard/data_locations.host.toml")
UNIT = Path("deployment/dashboard/quant-factory-dashboard.service")


def test_host_config_parses_with_host_paths() -> None:
    locations = load_data_locations(HOST_CONFIG)
    assert str(locations.root).startswith("/opt/quant-factory-research/")


def test_service_points_the_catalog_at_the_host_config() -> None:
    assert f"QUANT_FACTORY_DATA_LOCATIONS=/opt/quant-factory-dashboard/current/{HOST_CONFIG}" in UNIT.read_text()
