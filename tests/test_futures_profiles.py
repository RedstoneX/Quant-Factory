"""MNQ and M2K 5m auto-campaign profiles: CME contract specs and verified-data check."""

import pytest

from market_data.catalog import DEFAULT_CONFIG_PATH
from orchestration.auto_campaign import _check_verified_data, auto_test_definition, dataset_profile

# CME Group contract specs: MNQ tick 0.25 pt = $0.50 ($2/pt); M2K tick 0.10 pt = $0.50 ($5/pt).
_SPECS = {"MNQ": (0.25, 2.0), "M2K": (0.10, 5.0)}


@pytest.mark.parametrize("symbol", sorted(_SPECS))
def test_profile_uses_cme_specs_and_mes_costs(symbol):
    profile, mes = dataset_profile(symbol, "5m"), dataset_profile("MES", "5m")
    tick, multiplier = _SPECS[symbol]
    assert (profile.tick_size, profile.price_multiplier) == (tick, multiplier)
    assert round(tick * multiplier, 6) == 0.5  # dollars per tick
    assert profile.dataset_id == f"futures_{symbol}_5m_databento"
    assert profile.dataset_end == "2026-02-13T21:55:00Z"
    for field in ("fixed_fee_per_contract_per_side", "slippage_ticks", "stress_fee_per_contract_per_side",
                  "stress_slippage_ticks", "annualization_factor", "requested_start"):
        assert getattr(profile, field) == getattr(mes, field)


@pytest.mark.skipif(not DEFAULT_CONFIG_PATH.exists(), reason="machine data configuration absent")
@pytest.mark.parametrize("symbol", sorted(_SPECS))
def test_manifest_passes_the_same_verified_data_check_as_mes(symbol):
    profile = dataset_profile(symbol, "5m")
    definition = auto_test_definition(
        candidate_id="c1", strategy_id="s", strategy_version="1", variables={}, profile=profile
    )
    _check_verified_data(definition, profile)
