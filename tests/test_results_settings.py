from __future__ import annotations

from dashboard.ui.results_settings import (
    display_settings_rows,
    heatmap_figure,
    settings_columns,
    settings_identity,
    varying_parameters,
)

ROWS = [
    {"parameters": {"stop_atr": s, "offset_ticks": o, "mode": "fast_exit"}, "sharpe_ratio": s - o}
    for s in (1.0, 2.0, 3.0)
    for o in (0, 1)
]


def test_columns_follow_the_runs_own_parameter_names() -> None:
    fields = [column["field"] for column in settings_columns(ROWS)]
    assert fields == ["parameters.stop_atr", "parameters.offset_ticks", "parameters.mode"]
    assert settings_columns([]) == []


def test_varying_parameters_most_distinct_first_and_constants_dropped() -> None:
    assert varying_parameters(ROWS) == ["stop_atr", "offset_ticks"]
    assert varying_parameters(ROWS[:1]) == []


def test_display_formats_words_and_identity_uses_recorded_names() -> None:
    assert display_settings_rows(ROWS)[0]["parameters"]["mode"] == "Fast exit"
    assert settings_identity({"stop_atr": 1.0}) == "Stop atr 1.0"


def test_heatmap_uses_vectorbt_heatmap_over_chosen_parameters() -> None:
    figure = heatmap_figure(ROWS, "stop_atr", "offset_ticks", "sharpe_ratio")
    trace = figure.data[0]
    assert trace.type == "heatmap" and trace.z.shape == (2, 3)
