"""Pure, conservative comparison of execution snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from execution.contracts import (
    AccountSnapshot,
    PositionSnapshot,
    ReconciliationResult,
    ReconciliationStatus,
)


def reconcile_snapshots(
    expected_account: AccountSnapshot,
    actual_account: AccountSnapshot,
    expected_positions: tuple[PositionSnapshot, ...],
    actual_positions: tuple[PositionSnapshot, ...],
    *,
    maximum_snapshot_age: timedelta,
    compared_at: datetime | None = None,
) -> ReconciliationResult:
    """Compare complete same-account snapshots without inferring missing state.

    This deliberately returns ``indeterminate`` for stale or incompatible
    evidence.  It does not calculate P&L, infer currency conversion, tolerate
    quantities, or make an execution decision.
    """
    if maximum_snapshot_age.total_seconds() < 0:
        raise ValueError("maximum_snapshot_age cannot be negative")
    compared_at = compared_at or datetime.now(timezone.utc)
    if compared_at.tzinfo is None or compared_at.utcoffset() is None:
        raise ValueError("compared_at must be timezone-aware")
    compared_at = compared_at.astimezone(timezone.utc)
    indeterminate_reasons: list[str] = []
    mismatch_reasons: list[str] = []
    if not expected_account.positions_complete or not actual_account.positions_complete:
        indeterminate_reasons.append("position snapshot completeness is not confirmed")
    if (expected_account.execution_domain, expected_account.account_id) != (
        actual_account.execution_domain,
        actual_account.account_id,
    ):
        indeterminate_reasons.append("account identity or execution domain differs")
    if expected_account.currency != actual_account.currency:
        indeterminate_reasons.append("account currency differs")
    if abs(expected_account.captured_at - actual_account.captured_at) > maximum_snapshot_age:
        indeterminate_reasons.append("account snapshot timestamps exceed maximum age")
    for label, account in (("expected", expected_account), ("actual", actual_account)):
        age = compared_at - account.captured_at
        if age < timedelta(0):
            indeterminate_reasons.append(f"{label} account snapshot is from the future")
        elif age > maximum_snapshot_age:
            indeterminate_reasons.append(f"{label} account snapshot is stale")
    expected_by_symbol = {position.instrument.symbol: position for position in expected_positions}
    actual_by_symbol = {position.instrument.symbol: position for position in actual_positions}
    if len(expected_by_symbol) != len(expected_positions) or len(actual_by_symbol) != len(actual_positions):
        indeterminate_reasons.append("duplicate instrument positions are ambiguous")
    if set(expected_by_symbol) != set(actual_by_symbol):
        mismatch_reasons.append("position instrument sets differ")
    for label, positions, account in (
        ("expected", expected_positions, expected_account),
        ("actual", actual_positions, actual_account),
    ):
        for position in positions:
            if (position.execution_domain, position.account_id) != (
                account.execution_domain,
                account.account_id,
            ):
                indeterminate_reasons.append(f"{label} position identity differs from its account snapshot")
            if position.snapshot_id != account.snapshot_id:
                indeterminate_reasons.append(f"{label} position snapshot identity differs from its account snapshot")
            if position.instrument.currency != account.currency:
                indeterminate_reasons.append(f"{label} position currency differs from its account snapshot")
            if position.quantity != 0 and any(
                value is None
                for value in (
                    position.average_entry_price,
                    position.market_price,
                    position.market_value,
                )
            ):
                indeterminate_reasons.append(f"{label} nonzero position has unknown valuation")
            timestamp_gap = abs(position.captured_at - account.captured_at)
            if timestamp_gap > maximum_snapshot_age:
                indeterminate_reasons.append(f"{label} position timestamp differs from its account snapshot")
            age = compared_at - position.captured_at
            if age < timedelta(0):
                indeterminate_reasons.append(f"{label} position snapshot is from the future")
            elif age > maximum_snapshot_age:
                indeterminate_reasons.append(f"{label} position snapshot is stale")
    for symbol in sorted(set(expected_by_symbol) & set(actual_by_symbol)):
        expected = expected_by_symbol[symbol]
        actual = actual_by_symbol[symbol]
        if (expected.execution_domain, expected.account_id) != (actual.execution_domain, actual.account_id):
            indeterminate_reasons.append(f"position identity differs for {symbol}")
        if expected.instrument != actual.instrument:
            mismatch_reasons.append(f"instrument contract differs for {symbol}")
        if (expected.quantity, expected.average_entry_price, expected.market_price, expected.market_value) != (
            actual.quantity,
            actual.average_entry_price,
            actual.market_price,
            actual.market_value,
        ):
            mismatch_reasons.append(f"position values differ for {symbol}")
        if abs(expected.captured_at - actual.captured_at) > maximum_snapshot_age:
            indeterminate_reasons.append(f"position timestamps exceed maximum age for {symbol}")
    if (expected_account.cash, expected_account.equity, expected_account.buying_power) != (
        actual_account.cash,
        actual_account.equity,
        actual_account.buying_power,
    ):
        mismatch_reasons.append("account balances differ")
    reasons = tuple(indeterminate_reasons + mismatch_reasons)
    status = (
        ReconciliationStatus.INDETERMINATE
        if indeterminate_reasons
        else ReconciliationStatus.MISMATCHED
        if mismatch_reasons
        else ReconciliationStatus.MATCHED
    )
    return ReconciliationResult(
        status=status,
        expected_snapshot_id=expected_account.snapshot_id,
        actual_snapshot_id=actual_account.snapshot_id,
        compared_at=compared_at,
        reasons=reasons,
    )
