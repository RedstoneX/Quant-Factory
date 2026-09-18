"""Adversarial tests for the broker-neutral execution evidence boundary."""

from datetime import datetime, timedelta, timezone
from dataclasses import FrozenInstanceError
from decimal import Decimal
import json

import pytest

from execution import (
    AccountSnapshot,
    Cancellation,
    ExecutionContractError,
    ExecutionDomain,
    ExecutionScope,
    Fill,
    Instrument,
    OrderIntent,
    OrderAcknowledgement,
    OrderSide,
    OrderType,
    PositionSnapshot,
    QuantityUnit,
    ReconciliationStatus,
    Rejection,
    RiskMetadata,
    TimeInForce,
    reconcile_snapshots,
    to_primitive,
)


NOW = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc)


def _scope(domain: ExecutionDomain = ExecutionDomain.PAPER) -> ExecutionScope:
    return ExecutionScope(domain, "strategy-1", "run-1", "deployment-1", "account-1", "idempotency-1")


def _instrument(*, whole_unit_only: bool = True) -> Instrument:
    return Instrument("SCHX", "etf", "USD", QuantityUnit.SHARES, whole_unit_only)


def _intent(**overrides: object) -> OrderIntent:
    values: dict[str, object] = {
        "intent_id": "intent-1",
        "scope": _scope(),
        "risk": RiskMetadata("risk-policy-1", "risk-decision-1", NOW),
        "instrument": _instrument(),
        "side": OrderSide.BUY,
        "quantity": Decimal("2"),
        "order_type": OrderType.LIMIT,
        "time_in_force": TimeInForce.DAY,
        "created_at": NOW,
        "limit_price": Decimal("23.45"),
    }
    values.update(overrides)
    return OrderIntent(**values)  # type: ignore[arg-type]


def _account(snapshot_id: str, **overrides: object) -> AccountSnapshot:
    values: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "execution_domain": ExecutionDomain.PAPER,
        "account_id": "account-1",
        "currency": "USD",
        "captured_at": NOW,
        "cash": Decimal("1000.00"),
        "equity": Decimal("1023.45"),
        "buying_power": Decimal("2000.00"),
        "positions_complete": True,
    }
    values.update(overrides)
    return AccountSnapshot(**values)  # type: ignore[arg-type]


def _position(snapshot_id: str, **overrides: object) -> PositionSnapshot:
    values: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "execution_domain": ExecutionDomain.PAPER,
        "account_id": "account-1",
        "instrument": _instrument(),
        "captured_at": NOW,
        "quantity": Decimal("2"),
        "average_entry_price": Decimal("23.45"),
        "market_price": Decimal("23.45"),
        "market_value": Decimal("46.90"),
    }
    values.update(overrides)
    return PositionSnapshot(**values)  # type: ignore[arg-type]


def test_intent_serializes_to_json_without_float_or_sdk_values() -> None:
    intent = _intent()
    serialized = to_primitive(intent)
    assert serialized["quantity"] == "2"
    assert serialized["created_at"] == "2026-09-03T14:00:00Z"
    assert serialized["scope"]["execution_domain"] == "paper"
    assert json.loads(json.dumps(serialized))["risk"]["evaluated_at"].endswith("Z")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", 2.0),
        ("quantity", True),
        ("quantity", Decimal("NaN")),
        ("quantity", Decimal("Infinity")),
        ("created_at", datetime(2026, 9, 3, 14, 0)),
    ],
)
def test_intent_rejects_ambiguous_numeric_and_timestamp_inputs(field: str, value: object) -> None:
    with pytest.raises(ExecutionContractError):
        _intent(**{field: value})


@pytest.mark.parametrize(
    ("order_type", "limit_price", "stop_price"),
    [
        (OrderType.MARKET, Decimal("1"), None),
        (OrderType.LIMIT, None, None),
        (OrderType.STOP, Decimal("1"), Decimal("1")),
        (OrderType.STOP_LIMIT, Decimal("1"), None),
    ],
)
def test_intent_rejects_prices_inconsistent_with_order_type(
    order_type: OrderType, limit_price: Decimal | None, stop_price: Decimal | None
) -> None:
    with pytest.raises(ExecutionContractError):
        _intent(order_type=order_type, limit_price=limit_price, stop_price=stop_price)


def test_whole_share_fixture_is_explicit_and_never_silently_rounded() -> None:
    with pytest.raises(ExecutionContractError, match="integral share"):
        _intent(quantity=Decimal("1.5"))
    fractional = _intent(instrument=_instrument(whole_unit_only=False), quantity=Decimal("1.5"))
    assert fractional.quantity == Decimal("1.5")


def test_scope_requires_every_cross_domain_identity_field() -> None:
    with pytest.raises(ExecutionContractError, match="deployment_id"):
        ExecutionScope(ExecutionDomain.PAPER, "strategy", "run", "", "account", "key")
    with pytest.raises(ExecutionContractError, match="execution_domain"):
        ExecutionScope("paper", "strategy", "run", "deployment", "account", "key")  # type: ignore[arg-type]


def test_intent_rejects_untyped_mutable_adapter_values() -> None:
    with pytest.raises(ExecutionContractError, match="scope"):
        _intent(scope={"broker": object()})
    with pytest.raises(TypeError, match="unsupported"):
        to_primitive({"broker": object()})
    with pytest.raises(ExecutionContractError, match="remain distinct"):
        to_primitive({1: "one", "1": "string-one"})


def test_lifecycle_records_keep_intent_and_scope_without_broker_objects() -> None:
    scope = _scope()
    acknowledgement = OrderAcknowledgement("ack-1", "intent-1", scope, "broker-order-1", NOW)
    fill = Fill("fill-1", "intent-1", scope, "broker-order-1", Decimal("1"), Decimal("23.45"), NOW, None)
    cancellation = Cancellation("cancel-1", "intent-1", scope, "broker-order-1", NOW, "operator request")
    rejection = Rejection("reject-1", "intent-1", scope, NOW, "RISK_BLOCK", "risk policy denied")
    assert [to_primitive(record)["intent_id"] for record in (acknowledgement, fill, cancellation, rejection)] == [
        "intent-1",
        "intent-1",
        "intent-1",
        "intent-1",
    ]
    with pytest.raises(ExecutionContractError, match="broker_order_id"):
        OrderAcknowledgement("ack-1", "intent-1", scope, "", NOW)
    assert to_primitive(fill)["fee"] is None
    rebate = Fill("fill-2", "intent-1", scope, "broker-order-1", Decimal("1"), Decimal("23.45"), NOW, Decimal("-0.01"))
    assert to_primitive(rebate)["fee"] == "-0.01"
    with pytest.raises(ExecutionContractError, match="fee"):
        Fill("fill-1", "intent-1", scope, "broker-order-1", Decimal("1"), Decimal("23.45"), NOW, 0.0)  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        acknowledgement.broker_order_id = "different"  # type: ignore[misc]


def test_reconciliation_matches_only_complete_compatible_snapshots() -> None:
    expected_account = _account("expected-snapshot")
    actual_account = _account("actual-snapshot")
    result = reconcile_snapshots(
        expected_account,
        actual_account,
        (_position("expected-snapshot"),),
        (_position("actual-snapshot"),),
        maximum_snapshot_age=timedelta(seconds=1),
        compared_at=NOW,
    )
    assert result.status is ReconciliationStatus.MATCHED
    assert result.reasons == ()


@pytest.mark.parametrize(
    ("actual_account", "actual_position", "expected_age", "status"),
    [
        (_account("actual", account_id="other-account"), _position("actual"), timedelta(seconds=1), ReconciliationStatus.INDETERMINATE),
        (_account("actual", currency="CAD"), _position("actual"), timedelta(seconds=1), ReconciliationStatus.INDETERMINATE),
        (_account("actual", captured_at=NOW - timedelta(minutes=2)), _position("actual", captured_at=NOW - timedelta(minutes=2)), timedelta(seconds=1), ReconciliationStatus.INDETERMINATE),
        (_account("actual"), _position("actual", quantity=Decimal("3")), timedelta(seconds=1), ReconciliationStatus.MISMATCHED),
    ],
)
def test_reconciliation_never_calls_identity_or_stale_inputs_matched(
    actual_account: AccountSnapshot,
    actual_position: PositionSnapshot,
    expected_age: timedelta,
    status: ReconciliationStatus,
) -> None:
    result = reconcile_snapshots(
        _account("expected"),
        actual_account,
        (_position("expected"),),
        (actual_position,),
        maximum_snapshot_age=expected_age,
        compared_at=NOW,
    )
    assert result.status is status
    assert result.reasons


def test_reconciliation_rejects_negative_staleness_window() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        reconcile_snapshots(
            _account("expected"), _account("actual"), (), (),
            maximum_snapshot_age=timedelta(seconds=-1), compared_at=NOW,
        )


def test_reconciliation_rejects_naive_comparison_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        reconcile_snapshots(
            _account("expected"), _account("actual"), (), (),
            maximum_snapshot_age=timedelta(seconds=1),
            compared_at=datetime(2026, 9, 3, 14, 0),
        )


def test_reconciliation_rejects_incomplete_position_list() -> None:
    result = reconcile_snapshots(
        _account("expected", positions_complete=False), _account("actual"), (), (),
        maximum_snapshot_age=timedelta(seconds=1), compared_at=NOW,
    )
    assert result.status is ReconciliationStatus.INDETERMINATE


@pytest.mark.parametrize(
    ("expected_position", "actual_position", "actual_account"),
    [
        (_position("expected", account_id="wrong"), _position("actual", account_id="wrong"), _account("actual")),
        (_position("expected", captured_at=NOW - timedelta(days=1)), _position("actual", captured_at=NOW - timedelta(days=1)), _account("actual")),
        (_position("expected"), _position("actual"), _account("actual", captured_at=NOW + timedelta(days=1))),
    ],
)
def test_reconciliation_never_matches_positions_or_accounts_with_invalid_own_snapshot_context(
    expected_position: PositionSnapshot,
    actual_position: PositionSnapshot,
    actual_account: AccountSnapshot,
) -> None:
    result = reconcile_snapshots(
        _account("expected"), actual_account, (expected_position,), (actual_position,),
        maximum_snapshot_age=timedelta(seconds=1), compared_at=NOW,
    )
    assert result.status is ReconciliationStatus.INDETERMINATE
    assert result.reasons


@pytest.mark.parametrize(
    "actual_position",
    [
        _position("actual", account_id="wrong"),
        _position("wrong-snapshot"),
        _position("actual", instrument=Instrument("SCHX", "etf", "CAD", QuantityUnit.SHARES, True)),
    ],
)
def test_reconciliation_rejects_position_identity_currency_and_snapshot_mismatches(
    actual_position: PositionSnapshot,
) -> None:
    result = reconcile_snapshots(
        _account("expected"), _account("actual"), (_position("expected"),), (actual_position,),
        maximum_snapshot_age=timedelta(seconds=1), compared_at=NOW,
    )
    assert result.status is ReconciliationStatus.INDETERMINATE


def test_reconciliation_never_matches_nonzero_position_with_unknown_valuation() -> None:
    unknown_valuation = _position(
        "actual", average_entry_price=None, market_price=None, market_value=None
    )
    result = reconcile_snapshots(
        _account("expected"), _account("actual"), (_position("expected"),), (unknown_valuation,),
        maximum_snapshot_age=timedelta(seconds=1), compared_at=NOW,
    )
    assert result.status is ReconciliationStatus.INDETERMINATE
    assert "unknown valuation" in result.reasons[0]


def test_instrument_and_position_enforce_whole_share_constraint() -> None:
    with pytest.raises(ExecutionContractError, match="only supported"):
        Instrument("MES", "future", "USD", QuantityUnit.CONTRACTS, whole_unit_only=True)
    with pytest.raises(ExecutionContractError, match="integral share"):
        _position("snapshot", quantity=Decimal("0.5"))
