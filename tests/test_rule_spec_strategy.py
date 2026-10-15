"""Semantics, golden equivalence and registry behaviour of the qf_rules_v1 compiler."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from rule_language import RuleSpecError
from tests.rule_trades import trades
from strategies import get_strategy
from strategies.mes_sma_crossover_candidate import generate_candidate_signals
from strategies.parameter_governance import summarize_parameter_plan
from strategies.rule_spec_evaluation import RuleEvaluator, SessionBars
from strategies.rule_spec_strategy import (
    RULE_COMPILER_VERSION,
    RuleSpecStrategy,
    install_rule_strategy,
    rule_strategy_definition,
)

SESSION = {"timezone": "America/New_York", "open": "09:30", "close": "16:00"}
DAYS = pd.bdate_range("2026-10-05", periods=10)  # NYSE full sessions, no holidays


def _spec(signals, **extra) -> dict:
    spec = {
        "language": "qf_rules_v1",
        "bar": "5m",
        "tick_size": 0.25,
        "session": dict(SESSION),
        "flat_at": "15:55",
        "signals": signals,
        "max_trades_per_session": 1,
    }
    spec.update(extra)
    return spec


def _frame(closes_by_day, *, drop=()) -> pd.DataFrame:
    frames = []
    for day, closes in zip(DAYS, closes_by_day):
        closes = np.asarray(closes, dtype=float)
        start = pd.Timestamp(f"{day.date()} 09:30", tz="America/New_York").tz_convert("UTC")
        index = pd.date_range(start, periods=78, freq="5min")
        frames.append(
            pd.DataFrame(
                {"Open": closes, "High": closes + 0.5, "Low": closes - 0.5, "Close": closes, "Volume": 10.0},
                index=index,
            )
        )
    frame = pd.concat(frames)
    return frame.drop(frame.index[list(drop)])


def _run(spec, frame, *, variables=None, parameters=None):
    definition = rule_strategy_definition(candidate_id="cand-test", title="Test rules", rule_spec=spec, variables=variables or {})
    return RuleSpecStrategy(definition).generate_signals(frame, parameters or {})


def _ends(series: pd.Series) -> list[str]:
    stamps = series[series].index + pd.Timedelta(minutes=5)
    return [stamp.tz_convert("America/New_York").strftime("%d %H:%M") for stamp in stamps]


def _bars(closes) -> SessionBars:
    closes = np.asarray(closes, dtype=float)[:, None]
    return SessionBars(open=closes, high=closes + 0.5, low=closes - 0.5, close=closes, volume=np.ones_like(closes), tick_size=0.25, parameters={})


def test_same_sign_run_range_high_and_value_at_series() -> None:
    closes = np.full(78, 100.0)
    closes[1:6] = [101, 102, 101, 101, 102]
    closes[2] = 105  # bar ending 09:45: inside the 09:30-09:45 range
    evaluator = RuleEvaluator(_bars(closes))
    runs = evaluator.series({"same_sign_run": {"change": "close"}})[:7, 0]
    assert runs.tolist() == [0, 1, 2, 1, 0, 1, 1]
    high = evaluator.series({"range_high": {"from": "09:30", "to": "09:45"}})[:, 0]
    assert np.isnan(high[:2]).all() and (high[2:] == 105.5).all()
    at_ten = evaluator.series({"value_at": "close", "time": "10:00"})[:, 0]
    assert np.isnan(at_ten[:5]).all() and (at_ten[5:] == closes[5]).all()


def test_run_entry_with_after_bars_exit_and_dynamic_side() -> None:
    closes = np.full(78, 100.0)
    closes[10:14] = [101, 102, 103, 104]
    spec = _spec(
        [{"when": {"gte": [{"same_sign_run": {"change": "close"}}, 3]}, "side": {"opposite_sign_of": {"change": "close"}}}],
        exit={"after_bars": 2},
    )
    frame = _frame([closes])
    signals = _run(spec, frame)
    assert trades(signals, frame) == [("short", "05 10:35", "05 10:45")]  # after_bars -> VectorBT td_stop
    assert signals.td_stop.eq(2 * 5 * 60 * 10**9).all()


def test_at_time_and_flat_at_exits() -> None:
    frame = _frame([np.full(78, 100.0)])
    timed = _run(_spec([{"when": {"time_is": "10:00"}, "side": "long"}], exit={"at_time": "11:00"}), frame)
    assert trades(timed, frame) == [("long", "05 10:00", "05 11:00")]
    late = _run(_spec([{"when": {"time_is": "12:00"}, "side": "long"}], exit={"at_time": "11:00"}, flat_at="15:30"), frame)
    assert trades(late, frame) == [("long", "05 12:00", "05 15:30")]


def test_without_flat_at_positions_hold_overnight_until_the_td_stop() -> None:
    spec = _spec([{"when": {"time_is": "10:00"}, "side": "long"}], exit={"after_bars": 100})
    del spec["flat_at"]
    frame = _frame([np.full(78, 100.0)] * 3)
    # 100 bars of 5 minutes from the 10:00 fill: the first bar at or after 18:20 is the next day's 09:30 open.
    assert trades(_run(spec, frame), frame) == [
        ("long", "05 10:00", "06 09:30"), ("long", "06 10:00", "07 09:30"), ("long", "07 10:00", "open"),
    ]


def test_max_trades_and_no_same_bar_entry_and_exit() -> None:
    spec = _spec([{"when": {"gt": ["close", 0]}, "side": "long"}], exit={"after_bars": 1}, max_trades_per_session=3)
    frame = _frame([np.full(78, 100.0)] * 2)
    held = [("09:35", "09:40"), ("09:45", "09:50"), ("09:55", "10:00")]  # three entry fills, then the session cap holds
    assert trades(_run(spec, frame), frame) == [("long", f"{day} {a}", f"{day} {b}") for day in ("05", "06") for a, b in held]


def test_opposite_signal_exit_without_same_bar_reversal() -> None:
    spec = _spec(
        [
            {"when": {"time_is": "10:00"}, "side": "long"},
            {"when": {"time_between": ["11:00", "11:05"]}, "side": "short"},
        ],
        exit={"on_opposite_signal": True},
        max_trades_per_session=2,
    )
    frame = _frame([np.full(78, 100.0)])
    assert trades(_run(spec, frame), frame) == [("long", "05 10:00", "05 11:00"), ("short", "05 11:05", "05 15:55")]


def test_incomplete_session_is_ignored_and_stops_are_fractions() -> None:
    spec = _spec(
        [{"when": {"time_is": "10:00"}, "side": "long"}],
        exit={"stop_loss": {"ticks": 8}, "take_profit": {"percent": 1}},
    )
    signals = _run(spec, _frame([np.full(78, 100.0), np.full(78, 200.0)], drop=[78 + 40]))
    assert _ends(signals.entries) == ["05 10:00"]
    entry = signals.entries[signals.entries].index[0]
    assert signals.stop_loss[entry] == pytest.approx(8 * 0.25 / 100.0)
    assert signals.take_profit[entry] == pytest.approx(0.01)
    assert signals.stop_loss.drop(entry).isna().all()
    assert signals.metadata["sessions_traded"] == 1
    assert "entry fills" in signals.metadata["max_trades_counting"]
    assert "signal-bar close" in signals.metadata["stop_distance_approximation"]


def test_golden_mes_sma_10_30_matches_hand_written_candidate() -> None:
    rng = np.random.default_rng(20261006)
    days = []
    for phase in np.linspace(0.0, 2 * np.pi, 8, endpoint=False):
        bars = np.arange(78)
        days.append(5000 + 12 * np.sin(2 * np.pi * bars / 70 + phase) + np.cumsum(rng.normal(0, 0.6, 78)))
    frame = _frame(days, drop=[78 * 7 + 50])  # the eighth session is incomplete
    extra = pd.date_range(frame.index[0] - pd.Timedelta(hours=2), periods=6, freq="5min")
    frame = pd.concat([pd.DataFrame({column: 5000.0 for column in frame.columns}, index=extra), frame])
    sma = {"sma": "close", "length": 10}, {"sma": "close", "length": 30}
    spec = _spec(
        [
            {"when": {"all": [{"crosses_above": list(sma)}, {"time_between": ["09:35", "15:50"]}]}, "side": "long"},
            {"when": {"all": [{"crosses_below": list(sma)}, {"time_between": ["09:35", "15:50"]}]}, "side": "short"},
        ]
    )
    compiled = _run(spec, frame)
    golden = generate_candidate_signals(frame)
    assert golden.entries.any() and golden.short_entries.any()
    assert not golden.entries[golden.entries.index.normalize() == DAYS[7].tz_localize("UTC")].any()
    assert trades(compiled, frame) == trades(golden, frame) != []
    assert compiled.parameters == golden.parameters == {}
    assert compiled.stop_loss is None and compiled.take_profit is None


def test_definition_is_exactly_the_hashed_content_and_approved_for_backtests_only() -> None:
    spec = _spec([{"when": {"gt": ["close", {"sma": "close", "length": {"param": "fast"}}]}, "side": "long"}])
    definition = rule_strategy_definition(candidate_id="c1", title="T", rule_spec=spec, variables={"fast": {"values": [5, 10]}})
    assert set(definition) == {"strategy_id", "version", "rule_spec", "variables"}
    assert definition["strategy_id"].startswith("rules_") and len(definition["strategy_id"]) == 22
    assert definition["version"] == RULE_COMPILER_VERSION
    strategy = RuleSpecStrategy(definition)
    assert strategy.spec.approval_state == "approved"
    assert [p.allowed_values for p in strategy.spec.parameters] == [(5, 10)]
    assert summarize_parameter_plan(strategy.spec).total_combinations == 2
    assert summarize_parameter_plan(strategy.spec, require_approved=True).total_combinations == 2
    assert strategy.validate_parameters({"fast": 10}) == {"fast": 10}
    for bad in ({}, {"fast": 7}, {"fast": 5, "slow": 1}):
        with pytest.raises((TypeError, ValueError)):
            strategy.validate_parameters(bad)
    with pytest.raises(RuleSpecError):
        rule_strategy_definition(candidate_id="c1", title="T", rule_spec=_spec([]), variables={})


def test_install_writes_once_refuses_changes_and_get_strategy_loads_lazily(tmp_path, monkeypatch) -> None:
    spec = _spec([{"when": {"time_is": "10:10"}, "side": "short"}], tick_size=0.125, max_trades_per_session=2)
    definition = rule_strategy_definition(candidate_id="c2", title="Install", rule_spec=spec, variables={})
    strategy_id = definition["strategy_id"]
    installed = install_rule_strategy(definition, root=tmp_path)
    path = tmp_path / f"{strategy_id}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == definition
    assert install_rule_strategy(definition, root=tmp_path) is installed
    changed = dict(definition, rule_spec=dict(definition["rule_spec"], max_trades_per_session=3))
    with pytest.raises(ValueError):
        install_rule_strategy(changed, root=tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == definition
    assert get_strategy(strategy_id) is installed

    lazy_spec = _spec([{"when": {"time_is": "10:15"}, "side": "long"}], tick_size=0.125, max_trades_per_session=3)
    lazy = rule_strategy_definition(candidate_id="c3", title="Lazy", rule_spec=lazy_spec, variables={})
    (tmp_path / f"{lazy['strategy_id']}.json").write_text(json.dumps(lazy), encoding="utf-8")
    monkeypatch.setenv("QF_RULE_STRATEGY_ROOT", str(tmp_path))
    loaded = get_strategy(lazy["strategy_id"])
    assert loaded.spec.identity.strategy_id == lazy["strategy_id"]
    assert get_strategy(lazy["strategy_id"]) is loaded
    for unknown in ("rules_0000000000000000", "rules_../../etc", "not_a_strategy"):
        with pytest.raises(KeyError):
            get_strategy(unknown)
