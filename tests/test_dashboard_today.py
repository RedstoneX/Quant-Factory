"""Today home screen data: funnel counts, who needs the owner, the heatmap and the per-day count, all from fixture ideas."""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard import today_projection as today

G, A, R, N = "green", "amber", "red", "grey"


def _ideas() -> pd.DataFrame:
    rows = [
        ("a", "Alpha", "SPY", "Orb", 1.4, "Passed", [G, G, G, G, G]),
        ("b", "Beta", "SPY", "Orb", 0.9, "Passed", [G, G, G, G, G]),
        ("c", "Gamma", "MES", "Momentum", 0.6, "Close call", [G, G, G, A, G]),
        ("d", "Delta", "MES", "Orb", -0.3, "Failed: costs", [R, N, N, N, N]),
        ("e", "Eps", "QQQ", "Momentum", 0.2, "Failed: unseen", [G, R, N, N, N]),
        ("f", "Zeta", "QQQ", "Momentum", None, "No trades", [N, N, N, N, N]),
        ("g", "Eta", "SPY", "Momentum", 0.1, "Failed: costs", [R, N, N, N, N]),
    ]
    return pd.DataFrame([{"candidate_id": i, "title": t, "market": m, "family": f, "sharpe": s, "result": r, "dots": d, "total_return": s, "worst_drop": -1.0 if s is not None else None}
                         for i, t, m, f, s, r, d in rows])


def test_funnel_counts_ideas_standing_after_each_test() -> None:
    steps = today.funnel(_ideas())
    assert [(step["label"], step["count"]) for step in steps] == [("Submitted", 7), ("Survives costs", 4), ("Unseen data", 3), ("Holds over time", 3), ("Stress test", 2), ("Luck test", 2)]
    assert steps[1]["share"] == pytest.approx(4 / 7)  # bars are drawn to true scale from this share


def test_biggest_failure_is_the_test_that_failed_most_ideas() -> None:
    assert today.biggest_failure(_ideas()) == {"label": "Survives costs", "count": 2, "total": 7}
    assert today.biggest_failure(_ideas().iloc[0:3]) is None
    assert today.biggest_failure(pd.DataFrame()) is None


def test_needs_owner_selects_passed_and_close_calls_best_sharpe_first() -> None:
    waiting = today.needs_owner(_ideas())
    assert list(waiting["passed"]["candidate_id"]) == ["a", "b"] and list(waiting["close"]["candidate_id"]) == ["c"]
    assert today.best_idea(_ideas()) == "a"
    assert today.best_idea(_ideas().iloc[2:]) == "c"  # no pass: the best close call
    assert today.best_idea(_ideas().iloc[3:]) == "e"  # neither: highest Sharpe of any idea
    assert today.best_idea(pd.DataFrame()) is None


def test_heatmap_is_best_sharpe_by_market_and_type_and_skips_no_trade_ideas() -> None:
    table = today.heatmap(_ideas())
    assert table.loc["SPY", "Orb"] == pytest.approx(1.4) and table.loc["SPY", "Momentum"] == pytest.approx(0.1)
    assert table.loc["QQQ", "Momentum"] == pytest.approx(0.2)  # the no-trade idea has no Sharpe and is left out
    assert pd.isna(table.loc["QQQ", "Orb"]) and today.heatmap(pd.DataFrame()).empty


def test_scatter_keeps_only_ideas_with_return_and_drop() -> None:
    assert len(today.scatter_points(_ideas())) == 6
    zero = _ideas().assign(total_return=1.0, worst_drop=-1.0)
    assert "f" not in set(today.scatter_points(zero)["candidate_id"])  # a no-trade idea is never plotted, even with stray numbers


def test_daily_counts_cover_last_14_days_zero_filled() -> None:
    stamps = pd.to_datetime(["2026-10-18T01:00:00Z", "2026-10-18T23:00:00Z", "2026-10-10T12:00:00Z", "2026-09-01T12:00:00Z"], utc=True)
    series = today.daily_counts(stamps, today=pd.Timestamp("2026-10-18T12:00:00Z"))
    assert len(series) == 14 and series.iloc[-1] == 2 and series.sum() == 3 and series.iloc[0] == 0  # the September run is outside the window
    assert today.daily_counts(pd.to_datetime([], utc=True), today=pd.Timestamp("2026-10-18", tz="UTC")).empty


def test_heatmap_rows_sorted_by_best_cell_and_zero_prints_without_minus() -> None:
    ui = pytest.importorskip("dashboard.ui.today")
    rows = ui.heat_rows(today.heatmap(_ideas()))
    assert list(rows.index) == ["SPY", "MES", "QQQ"]  # best cell first; the longer list (3 markets vs 2 types) runs down
    assert ui.heat_text(-0.04) == "0.0" and ui.heat_text(-1.04) == "-1.0" and ui.heat_text(float("nan")) == ""
    assert ui.short_label("Late session volatility reacceleration", True).endswith("…") and len(ui.short_label("Late session volatility reacceleration", True)) == 18
    assert ui.short_label("Late session volatility reacceleration", False) == "Late session volatility reacceleration"


def test_section_title_is_closest_so_far_until_an_idea_passes() -> None:
    ui = pytest.importorskip("dashboard.ui.today")
    ideas = _ideas()
    assert ui.best_title({"waiting": today.needs_owner(ideas)}) == "Best idea"
    assert ui.best_title({"waiting": today.needs_owner(ideas.iloc[2:])}) == "Closest so far"
