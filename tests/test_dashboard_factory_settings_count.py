from __future__ import annotations

from dashboard.factory_overview import ONE_AT_A_TIME, passes_line, settings_count


def test_passes_line_wording() -> None:
    assert passes_line(72) == "Testing 72 settings"
    assert passes_line(24) == "Testing 24 settings"
    assert passes_line(None) is None


def test_settings_count_is_product_of_value_counts() -> None:
    assert settings_count('{"a": {"values": [1, 2, 3, 4, 5, 6]}, "b": {"values": [1, 2, 3, 4]}}') == 24
    assert settings_count({"a": {"values": [1, 2]}, "b": {"values": list(range(36))}}) == 72
    assert settings_count(None) is None
    assert settings_count("{}") is None


def test_wording_replaces_one_test_at_a_time() -> None:
    assert ONE_AT_A_TIME == "One idea at a time · every setting tested"
