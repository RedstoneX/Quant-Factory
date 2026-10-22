"""One generic strategy compiled from a validated ``qf_rules_v1`` rule spec.

A definition is immutable JSON data (never code): its ID is a hash of the
normalized rule spec, the variables and the compiler version, and the stored
definition holds exactly that content (no candidate ID, no title), so two ideas
with identical rules share one strategy.  Definitions are installed once as
``<root>/<strategy_id>.json`` and loaded lazily by ``strategies.get_strategy``.

Approval here is for BACKTESTING only (owner standing policy, see
``BACKTEST_APPROVAL_PROVENANCE``).  Paper trading is decided elsewhere and
never reads ``approval_state``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from rule_language import (
    BAR_MINUTES,
    RULE_LANGUAGE,
    RuleSpecError,
    bars_per_session,
    canonical_rule_spec_json,
    validate_rule_spec,
)
from rule_language.validation import STOP_KEYS
from strategies.mes_opening_range_breakout import _schedule
from strategies.models import (
    DataRequirements,
    ParameterDefinition,
    SignalResult,
    StrategyIdentity,
    StrategySpecification,
    TradingAssumptions,
)
from strategies.rule_spec_batch import PreparedSessions, iter_batch_signals, prepare_sessions
from strategies.rule_spec_evaluation import RuleEvaluator

RULE_COMPILER_VERSION = "1.0.0"
RULE_STRATEGY_PREFIX = "rules_"
RULE_STRATEGY_ROOT_ENV = "QF_RULE_STRATEGY_ROOT"
ARTIFACT_ROOT_ENV = "QUANT_FACTORY_ARTIFACT_ROOT"

BACKTEST_APPROVAL_PROVENANCE = (
    "Owner standing policy 2026-10-13: auto-test every valid idea; backtesting only; "
    "paper trading requires separate owner approval."
)
_DEFINITION_KEYS = frozenset({"strategy_id", "version", "rule_spec", "variables"})
_LEGACY_KEYS = ("candidate_id", "title")
_STRATEGY_ID = re.compile(r"rules_[0-9a-f]{16}")
_REQUIRED_FIELDS = ("Open", "High", "Low", "Close", "Volume")
_BAR_WORDS = {"1m": "one-minute", "5m": "five-minute"}
_LOADED: dict[str, "RuleSpecStrategy"] = {}
_LOCK = threading.Lock()


def rule_strategy_definition(
    *,
    rule_spec: Mapping[str, Any],
    variables: Mapping[str, Any],
    candidate_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Validate a rule spec (raising RuleSpecError) and return its immutable definition.

    ``candidate_id`` and ``title`` are accepted for caller compatibility but are
    deliberately not stored: the definition is exactly what the ID hashes.
    """
    normalized_variables = _normalized_variables(variables)
    spec = validate_rule_spec(rule_spec, variables=normalized_variables)
    payload = canonical_rule_spec_json(
        {"compiler_version": RULE_COMPILER_VERSION, "rule_spec": spec, "variables": normalized_variables}
    )
    return {
        "strategy_id": RULE_STRATEGY_PREFIX + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
        "version": RULE_COMPILER_VERSION,
        "rule_spec": spec,
        "variables": normalized_variables,
    }


def _normalized_variables(variables: Mapping[str, Any] | None) -> dict[str, dict[str, list[Any]]]:
    if variables is None:
        return {}
    if not isinstance(variables, Mapping):
        raise RuleSpecError("variables", 'must be an object mapping names to {"values": [...]}')
    normalized: dict[str, dict[str, list[Any]]] = {}
    for name in sorted(variables, key=str):
        definition = variables[name]
        values = definition.get("values") if isinstance(definition, Mapping) else None
        if not isinstance(name, str) or not name or not isinstance(values, (list, tuple)) or not values:
            raise RuleSpecError(f"variables.{name}", 'must be an object with a non-empty "values" list')
        normalized[name] = {"values": list(values)}
    return normalized


def _without_legacy_keys(definition: Any) -> Any:
    """Drop the candidate_id/title keys older installed files carried; the ID never covered them."""
    if isinstance(definition, Mapping):
        return {key: value for key, value in definition.items() if key not in _LEGACY_KEYS}
    return definition


def _checked_definition(definition: Any) -> dict[str, Any]:
    definition = _without_legacy_keys(definition)
    if not isinstance(definition, Mapping) or set(definition) != _DEFINITION_KEYS:
        raise ValueError(f"A rule strategy definition must have exactly the keys {sorted(_DEFINITION_KEYS)}")
    if definition["version"] != RULE_COMPILER_VERSION:
        raise ValueError(
            f"Rule strategy {definition['strategy_id']} was built for rule compiler "
            f"{definition['version']!r}; this compiler is {RULE_COMPILER_VERSION}"
        )
    rebuilt = rule_strategy_definition(
        rule_spec=definition["rule_spec"],
        variables=definition["variables"],
    )
    if canonical_rule_spec_json(rebuilt) != canonical_rule_spec_json(dict(definition)):
        raise ValueError(
            f"Rule strategy definition {definition['strategy_id']!r} does not match its normalized content; "
            "rebuild it with rule_strategy_definition"
        )
    return rebuilt


def _parameter_definition(name: str, values: list[Any]) -> ParameterDefinition:
    integers = all(isinstance(value, int) and not isinstance(value, bool) for value in values)
    candidates = tuple(values) if integers else tuple(float(value) for value in values)
    grid = len(candidates) > 1
    return ParameterDefinition(
        name=name,
        value_type=int if integers else float,
        default=candidates[0],
        description=f"Candidate variable {name} referenced by the rule spec.",
        optimizable=grid,
        allowed_values=candidates,
        classification="bounded_discrete" if grid else "fixed",
        reference_value=candidates[0],
        source=BACKTEST_APPROVAL_PROVENANCE,
        rationale="Bounded values declared by the Candidate packet; the compiler never tunes them.",
        expected_grid_contribution=len(candidates) if grid else None,
        approval_state="approved",
    )


def _describe(distance: Any) -> str | None:
    return None if distance is None else canonical_rule_spec_json(distance)


def _describe_stop(exit_rules: Mapping[str, Any]) -> str | None:
    """Fixed stop-loss distance, plus the trailing stop distance when one is set."""
    fixed = _describe(exit_rules.get("stop_loss"))
    if "trailing_stop" not in exit_rules:
        return fixed
    trailing = f"trailing {canonical_rule_spec_json(exit_rules['trailing_stop'])}"
    return trailing if fixed is None else f"{fixed}; {trailing}"


def _specification(definition: Mapping[str, Any]) -> StrategySpecification:
    spec = definition["rule_spec"]
    exit_rules = spec["exit"]
    bar = spec["bar"]
    sides = {signal["side"] if isinstance(signal["side"], str) else "both" for signal in spec["signals"]}
    after_bars = exit_rules.get("after_bars")
    strategy_id = definition["strategy_id"]
    return StrategySpecification(
        identity=StrategyIdentity(
            strategy_id=strategy_id,
            name=f"Rule strategy {strategy_id}",
            family="rule_spec",  # type: ignore[arg-type]
            version=definition["version"],
            description=f"{RULE_LANGUAGE} rules compiled by rule compiler {RULE_COMPILER_VERSION}.",
            direction=next(iter(sides)) if len(sides) == 1 else "both",  # type: ignore[arg-type]
        ),
        data=DataRequirements(
            required_fields=_REQUIRED_FIELDS,
            supported_intervals=(bar,),
            asset_classes=("futures", "equity", "etf"),
            minimum_history_bars=bars_per_session(bar),
            adjusted_prices=None,
        ),
        parameters=tuple(
            _parameter_definition(name, variable["values"])
            for name, variable in definition["variables"].items()
        ),
        assumptions=TradingAssumptions(
            signal_timing=f"Completed {_BAR_WORDS[bar]} regular-session bars; the first firing signal in list order wins",
            execution_timing=f"Next contiguous {_BAR_WORDS[bar]} bar open",
            position_sizing=f"One contract; at most {spec['max_trades_per_session']} entries per session",
            fee_rate=0.0,
            slippage_rate=0.0,
            stop_loss=_describe_stop(exit_rules),
            profit_target=_describe(exit_rules.get("take_profit")),
            maximum_holding_period=after_bars if isinstance(after_bars, int) else None,  # bars, VectorBT td_stop
            pyramiding=False,
            same_bar_limitation="No same-bar entry and exit and no same-bar reversal; signals fill at the next open.",
        ),
        hypothesis=f"Declarative {RULE_LANGUAGE} rules of strategy {strategy_id}, backtested as submitted; no edge is claimed.",
        source=BACKTEST_APPROVAL_PROVENANCE,
        approval_state="approved",
    )


class RuleSpecStrategy:
    """An installed rule-spec definition exposed through the Strategy protocol."""

    def __init__(self, definition: Mapping[str, Any]) -> None:
        self._definition = _checked_definition(definition)
        self._spec = _specification(self._definition)

    @property
    def spec(self) -> StrategySpecification:
        return self._spec

    @property
    def definition(self) -> dict[str, Any]:
        return copy.deepcopy(self._definition)

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        definitions = self._spec.parameter_map
        strategy_id = self._spec.identity.strategy_id
        unsupported = sorted(set(parameters) - set(definitions))
        if unsupported:
            raise ValueError(f"Unsupported parameter(s) for {strategy_id}: {', '.join(unsupported)}")
        missing = sorted(set(definitions) - set(parameters))
        if missing:
            raise ValueError(f"Missing parameter(s) for {strategy_id}: {', '.join(missing)}")
        normalized: dict[str, Any] = {}
        for name, definition in definitions.items():
            normalized[name] = definition.normalize(parameters[name])
        return normalized

    def generate_signals(self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]) -> SignalResult:
        return self.generate_signals_batch(data, [parameters])[0]

    def iter_signals_batch(self, data: pd.DataFrame | pd.Series, settings: Sequence[Mapping[str, Any]]) -> Iterator[SignalResult]:
        """Signals of every setting in order, from one pass over the data (see ``strategies.rule_spec_batch``)."""
        if not isinstance(data, pd.DataFrame):
            raise TypeError("Rule strategies require OHLCV market data")
        normalized = [self.validate_parameters(parameters) for parameters in settings]
        return iter_rule_signals(self._definition, data, normalized)

    def generate_signals_batch(self, data: pd.DataFrame | pd.Series, settings: Sequence[Mapping[str, Any]]) -> list[SignalResult]:
        return list(self.iter_signals_batch(data, settings))


def _checked_frame(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data.index, pd.DatetimeIndex) or data.index.tz is None:
        raise ValueError("Rule strategies require a timezone-aware DatetimeIndex")
    if not data.index.is_unique or not data.index.is_monotonic_increasing:
        raise ValueError("Rule strategy timestamps must be unique and chronological")
    missing = sorted(set(_REQUIRED_FIELDS) - set(data.columns))
    if missing:
        raise ValueError(f"Rule strategy data is missing columns: {missing}")
    frame = data.copy()
    frame.index = frame.index.tz_convert("UTC")
    return frame


def _check_data_frequency(frame: pd.DataFrame, bar: str) -> None:
    """Refuse data whose bar length differs from the spec's bar; there is no resampling."""
    if len(frame.index) < 2:
        return
    step = int(np.diff(frame.index.asi8).min()) // 60_000_000_000
    if step != BAR_MINUTES[bar]:
        raise ValueError(
            f"Rule spec bar is {bar!r} but the data has {step}-minute bars; "
            f"{RULE_LANGUAGE} never resamples, so supply {bar} data or change the spec's bar"
        )


def _metadata(definition: Mapping[str, Any], prepared: PreparedSessions, skipped: int, present: list[str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "rule_language": RULE_LANGUAGE,
        "rule_compiler_version": RULE_COMPILER_VERSION,
        "strategy_id": definition["strategy_id"],
        "sessions_traded": int(prepared.positions.shape[1]) if prepared.bars is not None else 0,
        "sessions_in_schedule": prepared.sessions_in_schedule,
        "entries_skipped_without_valid_stop_distance": skipped,
        "max_trades_counting": (
            "max_trades_per_session counts entry fills per session in the VectorBT simulation; a position closed by "
            "a stop frees no slot, and a later signal may enter again while the count is below the limit."
        ),
        "holding": (
            "VectorBT holds positions on the continuous bar history: overnight unless flat_at is set "
            "(flat_at and at_time -> an exit signal on that bar of every session; after_bars -> from_signals td_stop, "
            "a duration from the fill)."
        ),
    }
    if "trailing_stop" in present:
        metadata["trailing_stop_distance"] = (
            "the trailing stop's fraction is fixed at entry; the engine trails it behind the best price since entry."
        )
    if "trail_after" in present:
        metadata["trail_after"] = "the trailing stop switches on once price gains trail_after from the entry (from_signals tsl_th)."
    if present:
        metadata["stop_distance_approximation"] = (
            "points, ticks and ATR distances are divided by the signal-bar close to give the engine's fractional "
            "stop and target; the engine applies that fraction to the next-bar open fill."
        )
    return metadata


def iter_rule_signals(
    definition: Mapping[str, Any],
    data: pd.DataFrame,
    settings: Sequence[Mapping[str, Any]],
    *,
    schedule: pd.DataFrame | None = None,
) -> Iterator[SignalResult]:
    """Completed-bar signals of every validated setting, in order; the data is split into sessions once."""
    spec = definition["rule_spec"]
    frame = _checked_frame(data)
    _check_data_frequency(frame, spec["bar"])
    if schedule is None and len(frame.index):
        schedule = _schedule(frame.index)
    prepared = prepare_sessions(frame, schedule, _REQUIRED_FIELDS, tick_size=spec["tick_size"], bar=spec["bar"])
    present = [key for key in STOP_KEYS if key in spec["exit"]]
    batches = iter_batch_signals(spec, prepared, settings)
    session_ids = _session_ids(prepared)
    for parameters, (flags, levels, time_stops, skipped) in zip(settings, batches):
        # Each stop's distance is fixed at entry: the fraction measured on the signal bar is written on the entry row.
        dropped = _engine_exit_inputs(spec, prepared, parameters, flags, levels)
        metadata = _metadata(definition, prepared, skipped, present)
        if "level" in spec["exit"].get("stop_loss", {}):
            metadata["entries_dropped_level_stop_on_wrong_side"] = dropped
        if "exit_when" in spec["exit"]:
            metadata["exit_when"] = (
                "exit_when is a rule exit (from_signals exits/short_exits): a held position exits on that bar, and a "
                "later signal can enter again within max_trades_per_session."
            )
        yield SignalResult(
            entries=flags["entry"],
            exits=flags["exit"],
            short_entries=flags["short_entry"],
            short_exits=flags["short_exit"],
            parameters=dict(parameters),
            metadata=metadata,
            stop_loss=levels.get("stop_loss"),
            take_profit=levels.get("take_profit"),
            trailing_stop=levels.get("trailing_stop"),
            trailing_threshold=levels.get("trail_after"),
            td_stop=time_stops["td_stop"] if "after_bars" in spec["exit"] else None,
            # An opposite signal never reverses a position; on_opposite_signal closes it through exits/short_exits.
            upon_opposite_entry="Ignore",
            session_entry_cap=spec["max_trades_per_session"],
            session_id=session_ids,
        )


def _session_ids(prepared: PreparedSessions) -> pd.Series:
    """One id per bar: the column number of its full regular session, -1 for every other bar."""
    ids = np.full(len(prepared.index), -1, dtype=np.int64)
    ids[prepared.positions] = np.arange(prepared.positions.shape[1])[None, :]
    return pd.Series(ids, index=prepared.index)


def _engine_exit_inputs(
    spec: Mapping[str, Any],
    prepared: PreparedSessions,
    parameters: Mapping[str, Any],
    flags: dict[str, pd.Series],
    levels: dict[str, pd.Series],
) -> int:
    """Translate level stops and R-multiples into Portfolio.from_signals stop inputs.

    (``exit_when`` is a from_signals exit written by ``strategies.rule_spec_batch`` like any other rule exit.)
    - ``stop_loss.level`` -> ``sl_stop`` as the fraction from the entry open to the level (the runner passes
      ``delta_format="Percent"``, ``stop_entry_price="Open"``, so the engine's stop sits on the level; a bar
      opening beyond it fills at that open). An entry whose open is already through its level is dropped.
    - ``take_profit.r_multiple`` -> ``tp_stop`` and ``trail_after.r_multiple`` -> ``tsl_th``, each R x that entry's
      ``sl_stop`` fraction.
    Returns the number of entries dropped for a level on the wrong side of the entry open.
    """
    exit_rules = spec["exit"]
    level = exit_rules.get("stop_loss", {}).get("level")
    multiples = [key for key in ("take_profit", "trail_after") if "r_multiple" in exit_rules.get(key, {})]
    if prepared.bars is None or (level is None and not multiples):
        return 0
    evaluator = RuleEvaluator(replace(prepared.bars, parameters=dict(parameters)))

    def on_index(values: np.ndarray, fill: Any) -> np.ndarray:
        result = np.full(len(prepared.index), fill, dtype=values.dtype)
        result[prepared.positions] = values
        return result

    dropped = 0
    if level is not None:
        signed = on_index(evaluator.level_fraction(level), np.nan)
        with np.errstate(invalid="ignore"):
            wrong = (flags["entry"].to_numpy() & ~(signed > 0)) | (flags["short_entry"].to_numpy() & ~(signed < 0))
        dropped = int(wrong.sum())
        for name in ("entry", "short_entry"):
            flags[name] = flags[name] & ~wrong
        for key in levels:
            levels[key] = levels[key].mask(wrong)
    for key in multiples:
        levels[key] = levels[key] * levels["stop_loss"]
    return dropped


def compile_rule_signals(
    definition: Mapping[str, Any],
    data: pd.DataFrame,
    parameters: Mapping[str, Any],
    *,
    schedule: pd.DataFrame | None = None,
) -> SignalResult:
    """Turn a checked definition and validated parameters into completed-bar signals."""
    return next(iter_rule_signals(definition, data, [parameters], schedule=schedule))


def rule_strategy_root(root: str | os.PathLike[str] | None = None) -> Path | None:
    """Directory of installed definitions: ``root``, $QF_RULE_STRATEGY_ROOT, or the artifact root."""
    if root is not None:
        return Path(root)
    configured = os.environ.get(RULE_STRATEGY_ROOT_ENV, "").strip()
    if configured:
        return Path(configured)
    artifacts = os.environ.get(ARTIFACT_ROOT_ENV, "").strip()
    return Path(artifacts) / "rule_strategies" if artifacts else None


def _remember(strategy: RuleSpecStrategy) -> RuleSpecStrategy:
    with _LOCK:
        return _LOADED.setdefault(strategy.spec.identity.strategy_id, strategy)


def _definition_text(definition: Mapping[str, Any]) -> str:
    return json.dumps(definition, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def install_rule_strategy(
    definition: Mapping[str, Any], root: str | os.PathLike[str] | None = None
) -> RuleSpecStrategy:
    """Write ``<root>/<strategy_id>.json`` once (atomically) and register the strategy.

    An existing file with different content is never overwritten.
    """
    strategy = RuleSpecStrategy(definition)
    directory = rule_strategy_root(root)
    if directory is None:
        raise ValueError(f"Set {RULE_STRATEGY_ROOT_ENV} or {ARTIFACT_ROOT_ENV}, or pass root, to install rule strategies")
    strategy_id = strategy.spec.identity.strategy_id
    path = directory / f"{strategy_id}.json"
    text = _definition_text(strategy.definition)
    if path.exists():
        try:
            existing = canonical_rule_spec_json(_without_legacy_keys(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Installed rule strategy {path} is unreadable; it is never overwritten") from exc
        if existing != canonical_rule_spec_json(strategy.definition):
            raise ValueError(f"Rule strategy {strategy_id} is already installed with different content; it is immutable")
        return _remember(strategy)
    directory.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{strategy_id}.", suffix=".tmp", dir=directory)
    try:
        # mkstemp creates 0600; group-readable so the Dashboard (same group) can rebuild tested ideas.
        os.fchmod(handle, 0o640)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return _remember(strategy)


def load_rule_strategy(strategy_id: str, root: str | os.PathLike[str] | None = None) -> RuleSpecStrategy:
    """Return a registered rule strategy, loading it from its definition file on first use."""
    with _LOCK:
        loaded = _LOADED.get(strategy_id)
    if loaded is not None:
        return loaded
    directory = rule_strategy_root(root)
    path = directory / f"{strategy_id}.json" if directory is not None else None
    if not isinstance(strategy_id, str) or not _STRATEGY_ID.fullmatch(strategy_id) or path is None or not path.is_file():
        raise KeyError(f"Unknown strategy ID: {strategy_id}")
    strategy = RuleSpecStrategy(json.loads(path.read_text(encoding="utf-8")))
    if strategy.spec.identity.strategy_id != strategy_id:
        raise ValueError(f"Rule strategy file {path} holds {strategy.spec.identity.strategy_id}, not {strategy_id}")
    return _remember(strategy)
