"""Immutable, broker-neutral records for the future execution boundary.

These records model evidence exchanged with an execution adapter.  They do not
submit orders, select an endpoint, authorize a deployment, or persist state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import math
from typing import Any, Mapping


class ExecutionContractError(ValueError):
    """Raised when an execution record is ambiguous or unsafe to retain."""


class ExecutionDomain(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    DAY = "day"
    GOOD_TIL_CANCELLED = "good_til_cancelled"


class QuantityUnit(str, Enum):
    SHARES = "shares"
    CONTRACTS = "contracts"
    BASE_UNITS = "base_units"


class ReconciliationStatus(str, Enum):
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    INDETERMINATE = "indeterminate"


def _required_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionContractError(f"{field} must be a non-empty string")
    return value


def _aware_timestamp(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ExecutionContractError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _decimal(value: Decimal, field: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ExecutionContractError(f"{field} must be a Decimal; floats and booleans are not accepted")
    if not value.is_finite():
        raise ExecutionContractError(f"{field} must be finite")
    if positive and value <= 0:
        raise ExecutionContractError(f"{field} must be positive")
    if nonnegative and value < 0:
        raise ExecutionContractError(f"{field} must be non-negative")
    return value


def _optional_decimal(value: Decimal | None, field: str) -> Decimal | None:
    return None if value is None else _decimal(value, field, positive=True)


def _enum(value: Any, enum_type: type[Enum], field: str) -> None:
    if not isinstance(value, enum_type):
        raise ExecutionContractError(f"{field} must be {enum_type.__name__}")


def _whole_unit(quantity: Decimal, unit: QuantityUnit, whole_unit_only: bool) -> None:
    if whole_unit_only and unit is not QuantityUnit.SHARES:
        raise ExecutionContractError("whole_unit_only is only supported for share quantities")
    if whole_unit_only and quantity != quantity.to_integral_value():
        raise ExecutionContractError("whole_unit_only requires an integral share quantity")


@dataclass(frozen=True)
class ExecutionScope:
    """Identity carried by order lifecycle records; domain is descriptive only."""

    execution_domain: ExecutionDomain
    strategy_id: str
    run_id: str
    deployment_id: str
    account_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        _enum(self.execution_domain, ExecutionDomain, "execution_domain")
        for field in ("strategy_id", "run_id", "deployment_id", "account_id", "idempotency_key"):
            _required_identifier(getattr(self, field), field)


@dataclass(frozen=True)
class RiskMetadata:
    policy_id: str
    decision_id: str
    evaluated_at: datetime

    def __post_init__(self) -> None:
        _required_identifier(self.policy_id, "policy_id")
        _required_identifier(self.decision_id, "decision_id")
        object.__setattr__(self, "evaluated_at", _aware_timestamp(self.evaluated_at, "evaluated_at"))


@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: str
    currency: str
    quantity_unit: QuantityUnit
    whole_unit_only: bool = False

    def __post_init__(self) -> None:
        for field in ("symbol", "asset_class", "currency"):
            _required_identifier(getattr(self, field), field)
        _enum(self.quantity_unit, QuantityUnit, "quantity_unit")
        if not isinstance(self.whole_unit_only, bool):
            raise ExecutionContractError("whole_unit_only must be a bool")
        if self.whole_unit_only and self.quantity_unit is not QuantityUnit.SHARES:
            raise ExecutionContractError("whole_unit_only is only supported for share quantities")


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    scope: ExecutionScope
    risk: RiskMetadata
    instrument: Instrument
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    time_in_force: TimeInForce
    created_at: datetime
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None

    def __post_init__(self) -> None:
        _required_identifier(self.intent_id, "intent_id")
        if not isinstance(self.scope, ExecutionScope):
            raise ExecutionContractError("scope must be ExecutionScope")
        if not isinstance(self.risk, RiskMetadata):
            raise ExecutionContractError("risk must be RiskMetadata")
        if not isinstance(self.instrument, Instrument):
            raise ExecutionContractError("instrument must be Instrument")
        _enum(self.side, OrderSide, "side")
        _enum(self.order_type, OrderType, "order_type")
        _enum(self.time_in_force, TimeInForce, "time_in_force")
        quantity = _decimal(self.quantity, "quantity", positive=True)
        _whole_unit(quantity, self.instrument.quantity_unit, self.instrument.whole_unit_only)
        object.__setattr__(self, "created_at", _aware_timestamp(self.created_at, "created_at"))
        limit_price = _optional_decimal(self.limit_price, "limit_price")
        stop_price = _optional_decimal(self.stop_price, "stop_price")
        if self.order_type is OrderType.MARKET and (limit_price is not None or stop_price is not None):
            raise ExecutionContractError("market orders cannot have limit_price or stop_price")
        if self.order_type is OrderType.LIMIT and (limit_price is None or stop_price is not None):
            raise ExecutionContractError("limit orders require only limit_price")
        if self.order_type is OrderType.STOP and (stop_price is None or limit_price is not None):
            raise ExecutionContractError("stop orders require only stop_price")
        if self.order_type is OrderType.STOP_LIMIT and (stop_price is None or limit_price is None):
            raise ExecutionContractError("stop_limit orders require stop_price and limit_price")


@dataclass(frozen=True)
class OrderAcknowledgement:
    acknowledgement_id: str
    intent_id: str
    scope: ExecutionScope
    broker_order_id: str
    acknowledged_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise ExecutionContractError("scope must be ExecutionScope")
        for field in ("acknowledgement_id", "intent_id", "broker_order_id"):
            _required_identifier(getattr(self, field), field)
        object.__setattr__(self, "acknowledged_at", _aware_timestamp(self.acknowledged_at, "acknowledged_at"))


@dataclass(frozen=True)
class Fill:
    fill_id: str
    intent_id: str
    scope: ExecutionScope
    broker_order_id: str
    quantity: Decimal
    price: Decimal
    occurred_at: datetime
    fee: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise ExecutionContractError("scope must be ExecutionScope")
        for field in ("fill_id", "intent_id", "broker_order_id"):
            _required_identifier(getattr(self, field), field)
        _decimal(self.quantity, "quantity", positive=True)
        _decimal(self.price, "price", positive=True)
        if self.fee is not None:
            _decimal(self.fee, "fee")
        object.__setattr__(self, "occurred_at", _aware_timestamp(self.occurred_at, "occurred_at"))


@dataclass(frozen=True)
class Cancellation:
    cancellation_id: str
    intent_id: str
    scope: ExecutionScope
    broker_order_id: str
    cancelled_at: datetime
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise ExecutionContractError("scope must be ExecutionScope")
        for field in ("cancellation_id", "intent_id", "broker_order_id", "reason"):
            _required_identifier(getattr(self, field), field)
        object.__setattr__(self, "cancelled_at", _aware_timestamp(self.cancelled_at, "cancelled_at"))


@dataclass(frozen=True)
class Rejection:
    rejection_id: str
    intent_id: str
    scope: ExecutionScope
    rejected_at: datetime
    reason_code: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise ExecutionContractError("scope must be ExecutionScope")
        for field in ("rejection_id", "intent_id", "reason_code", "reason"):
            _required_identifier(getattr(self, field), field)
        object.__setattr__(self, "rejected_at", _aware_timestamp(self.rejected_at, "rejected_at"))


@dataclass(frozen=True)
class AccountSnapshot:
    snapshot_id: str
    execution_domain: ExecutionDomain
    account_id: str
    currency: str
    captured_at: datetime
    cash: Decimal
    equity: Decimal
    buying_power: Decimal
    positions_complete: bool

    def __post_init__(self) -> None:
        for field in ("snapshot_id", "account_id", "currency"):
            _required_identifier(getattr(self, field), field)
        _enum(self.execution_domain, ExecutionDomain, "execution_domain")
        object.__setattr__(self, "captured_at", _aware_timestamp(self.captured_at, "captured_at"))
        for field in ("cash", "equity", "buying_power"):
            _decimal(getattr(self, field), field)
        if not isinstance(self.positions_complete, bool):
            raise ExecutionContractError("positions_complete must be a bool")


@dataclass(frozen=True)
class PositionSnapshot:
    snapshot_id: str
    execution_domain: ExecutionDomain
    account_id: str
    instrument: Instrument
    captured_at: datetime
    quantity: Decimal
    average_entry_price: Decimal | None
    market_price: Decimal | None
    market_value: Decimal | None

    def __post_init__(self) -> None:
        for field in ("snapshot_id", "account_id"):
            _required_identifier(getattr(self, field), field)
        _enum(self.execution_domain, ExecutionDomain, "execution_domain")
        if not isinstance(self.instrument, Instrument):
            raise ExecutionContractError("instrument must be Instrument")
        object.__setattr__(self, "captured_at", _aware_timestamp(self.captured_at, "captured_at"))
        quantity = _decimal(self.quantity, "quantity")
        _whole_unit(quantity, self.instrument.quantity_unit, self.instrument.whole_unit_only)
        for field in ("average_entry_price", "market_price", "market_value"):
            value = getattr(self, field)
            if value is not None:
                _decimal(value, field, positive=field != "market_value")


@dataclass(frozen=True)
class ReconciliationResult:
    status: ReconciliationStatus
    expected_snapshot_id: str
    actual_snapshot_id: str
    compared_at: datetime
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _enum(self.status, ReconciliationStatus, "status")
        _required_identifier(self.expected_snapshot_id, "expected_snapshot_id")
        _required_identifier(self.actual_snapshot_id, "actual_snapshot_id")
        object.__setattr__(self, "compared_at", _aware_timestamp(self.compared_at, "compared_at"))
        if not isinstance(self.reasons, tuple) or any(not isinstance(reason, str) or not reason for reason in self.reasons):
            raise ExecutionContractError("reasons must be a tuple of non-empty strings")
        if self.status is ReconciliationStatus.MATCHED and self.reasons:
            raise ExecutionContractError("matched reconciliation cannot include mismatch reasons")
        if self.status is not ReconciliationStatus.MATCHED and not self.reasons:
            raise ExecutionContractError("non-matched reconciliation requires reasons")


def to_primitive(value: Any) -> Any:
    """Return JSON-native values without silently coercing Decimal or timestamps."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        _decimal(value, "decimal")
        return str(value)
    if isinstance(value, datetime):
        return _aware_timestamp(value, "timestamp").isoformat().replace("+00:00", "Z")
    if hasattr(value, "__dataclass_fields__"):
        return {field: to_primitive(getattr(value, field)) for field in value.__dataclass_fields__}
    if isinstance(value, tuple):
        return [to_primitive(item) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            if normalized_key in normalized:
                raise ExecutionContractError("mapping keys must remain distinct after serialization")
            normalized[normalized_key] = to_primitive(item)
        return normalized
    if isinstance(value, list):
        return [to_primitive(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExecutionContractError("non-finite floats cannot be serialized")
        raise ExecutionContractError("floats cannot be serialized in execution contracts")
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"unsupported execution contract value: {type(value).__name__}")
