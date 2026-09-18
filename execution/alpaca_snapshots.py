"""Pure normalization of decoded Alpaca paper observations into execution snapshots.

This module has no transport, persistence, worker, or order-submission capability.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
import re
from uuid import UUID

from execution.contracts import (
    AccountSnapshot,
    ExecutionDomain,
    Instrument,
    PositionSnapshot,
    QuantityUnit,
)
from execution.paper_binding import PaperDeploymentBinding, PaperDeploymentBindingError


_DECIMAL = re.compile(r"-?[0-9]+(?:\.[0-9]+)?", re.ASCII)
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.]{0,31}", re.ASCII)


class AlpacaSnapshotError(ValueError):
    """Decoded broker observation is unsuitable for a reconciliation snapshot."""

    def __init__(self) -> None:
        super().__init__("Alpaca snapshot normalization rejected")


def _reject() -> None:
    raise AlpacaSnapshotError() from None


def _uuid(value: object) -> str:
    if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
        _reject()
    return value


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if type(value) is not str or len(value) > 64 or not _DECIMAL.fullmatch(value):
        _reject()
    parsed = Decimal(value)
    if not parsed.is_finite() or (positive and parsed <= 0):
        _reject()
    return parsed


def _instrument_registry(value: object) -> Mapping[str, Instrument]:
    if not isinstance(value, Mapping):
        _reject()
    for symbol, instrument in value.items():
        if (type(symbol) is not str or not isinstance(instrument, Instrument)
                or symbol != instrument.symbol
                or instrument.asset_class not in {"equity", "etf"}
                or instrument.currency != "USD"
                or instrument.quantity_unit is not QuantityUnit.SHARES
                or not instrument.whole_unit_only):
            _reject()
    return value


def normalize_snapshots(
    account: object,
    positions: object,
    *,
    binding: PaperDeploymentBinding,
    observed_at: datetime,
    snapshot_id: str,
    instruments: Mapping[str, Instrument],
    positions_complete: bool,
) -> tuple[AccountSnapshot, tuple[PositionSnapshot, ...]]:
    """Return a complete paper snapshot from already-decoded broker responses.

    ``observed_at`` is supplied by the caller. It records observation timing only;
    it does not make the separate account and positions responses atomic or prove
    market-data freshness.
    """
    try:
        if not isinstance(binding, PaperDeploymentBinding):
            _reject()
        expected = binding.account_id
        if (not isinstance(observed_at, datetime) or observed_at.tzinfo is None
                or observed_at.utcoffset() is None or type(snapshot_id) is not str
                or not snapshot_id.strip() or positions_complete is not True
                or type(account) is not dict or type(positions) is not list):
            _reject()
        registry = _instrument_registry(instruments)
        observed_account_id = _uuid(account.get("id"))
        try:
            binding.require_match(
                account_id=observed_account_id, deployment_id=binding.deployment_id,
            )
        except PaperDeploymentBindingError:
            _reject()
        if (account.get("status") != "ACTIVE" or account.get("currency") != "USD"):
            _reject()
        for field in ("trading_blocked", "account_blocked", "trade_suspended_by_user"):
            if account.get(field) is not False:
                _reject()
        snapshot = AccountSnapshot(
            snapshot_id=snapshot_id,
            execution_domain=ExecutionDomain.PAPER,
            account_id=expected,
            currency="USD",
            captured_at=observed_at,
            cash=_decimal(account.get("cash")),
            equity=_decimal(account.get("equity")),
            buying_power=_decimal(account.get("buying_power")),
            positions_complete=True,
        )
        asset_ids: set[str] = set()
        symbols: set[str] = set()
        normalized: list[PositionSnapshot] = []
        for position in positions:
            if type(position) is not dict:
                _reject()
            asset_id = _uuid(position.get("asset_id"))
            symbol = position.get("symbol")
            if (type(symbol) is not str or not _SYMBOL.fullmatch(symbol)
                    or asset_id in asset_ids or symbol in symbols
                    or position.get("asset_class") != "us_equity"):
                _reject()
            instrument = registry.get(symbol)
            if instrument is None:
                _reject()
            quantity = _decimal(position.get("qty"))
            side = position.get("side")
            if ((side == "long" and quantity <= 0) or (side == "short" and quantity >= 0)
                    or side not in {"long", "short"}
                    or quantity != quantity.to_integral_value()):
                _reject()
            average_entry_price = _decimal(position.get("avg_entry_price"), positive=True)
            market_price = _decimal(position.get("current_price"), positive=True)
            market_value = _decimal(position.get("market_value"))
            if market_value == 0 or (quantity > 0 and market_value < 0) or (quantity < 0 and market_value > 0):
                _reject()
            asset_ids.add(asset_id)
            symbols.add(symbol)
            normalized.append(PositionSnapshot(
                snapshot_id=snapshot_id,
                execution_domain=ExecutionDomain.PAPER,
                account_id=expected,
                instrument=instrument,
                captured_at=observed_at,
                quantity=quantity,
                average_entry_price=average_entry_price,
                market_price=market_price,
                market_value=market_value,
            ))
        return snapshot, tuple(normalized)
    except AlpacaSnapshotError:
        raise
    except Exception:
        _reject()
