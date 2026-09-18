"""Offline Alpaca paper mapping and recovery; no concrete network transport."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import Protocol
from uuid import UUID

from execution.contracts import (
    ExecutionDomain, OrderAcknowledgement, OrderIntent, OrderType, QuantityUnit, TimeInForce,
)
from execution.paper_journal import (
    JournalConflictError, JournalEntry, JournalState, PaperOrderJournal,
)
from execution.paper_binding import PaperDeploymentBinding, PaperDeploymentBindingError

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
ORDERS_URL = PAPER_BASE_URL + "/v2/orders"
LOOKUP_URL = PAPER_BASE_URL + "/v2/orders:by_client_order_id"
_ACKNOWLEDGED_STATUSES = frozenset({"accepted", "new"})
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?", re.ASCII)
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", re.ASCII)


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: object = field(repr=False)


class PaperTransport(Protocol):
    """Injected capability, not proof of network/account/credential isolation.

    Each method must perform at most one request to the exact supplied full URL,
    without hidden retries, redirects, endpoint rewriting or environment-based
    overrides. The future worker must enforce this contract and verify its actual
    paper account and credential boundary. No concrete transport is supplied here.
    """

    def post(self, url: str, body: Mapping[str, object]) -> TransportResponse: ...
    def get(self, url: str) -> TransportResponse: ...


class AlpacaPaperBoundaryError(ValueError):
    """The request is outside this offline boundary's supported capability."""


class AlpacaPaperPersistenceError(RuntimeError):
    """Durable state could not be verified or updated; never authorizes retrying POST."""


def client_order_id(intent: OrderIntent) -> str:
    """Pinned v1 mapping; component boundaries and scope survive process restarts."""
    scope = intent.scope
    identity = {
        "version": 1, "execution_domain": scope.execution_domain.value,
        "intent_id": intent.intent_id, "strategy_id": scope.strategy_id,
        "run_id": scope.run_id, "deployment_id": scope.deployment_id,
        "account_id": scope.account_id, "idempotency_key": scope.idempotency_key,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "qf1-" + hashlib.sha256(encoded).hexdigest()[:44]


def _decimal_parts(value: Decimal) -> tuple[tuple[int, ...], int]:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise AlpacaPaperBoundaryError("order quantities and prices must be positive finite decimals")
    _, digits, exponent = value.as_tuple()
    while len(digits) > 1 and digits[-1] == 0:
        digits, exponent = digits[:-1], exponent + 1
    return digits, exponent


def _decimal_text(value: Decimal) -> str:
    digits, exponent = _decimal_parts(value)
    length = max(1, len(digits) + exponent) + (1 - exponent if exponent < 0 else 0)
    if length > 64:
        raise AlpacaPaperBoundaryError("order numeric value exceeds the supported representation bound")
    # Constructing from the tuple and fixed formatting do not round to context.prec.
    return format(Decimal((0, digits, exponent)), "f")


def request_for(intent: OrderIntent) -> dict[str, object]:
    """Validate the conservative subset before any enqueue or submission claim."""
    if not isinstance(intent, OrderIntent):
        raise AlpacaPaperBoundaryError("an OrderIntent is required")
    if (intent.scope.execution_domain is not ExecutionDomain.PAPER
            or intent.instrument.asset_class not in {"equity", "etf"}
            or intent.instrument.currency != "USD"
            or intent.instrument.quantity_unit is not QuantityUnit.SHARES
            or not intent.instrument.whole_unit_only
            or intent.time_in_force is not TimeInForce.DAY
            or intent.order_type not in {OrderType.MARKET, OrderType.LIMIT}):
        raise AlpacaPaperBoundaryError("intent is outside the offline whole-share paper equity subset")
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,14}", intent.instrument.symbol, re.ASCII):
        raise AlpacaPaperBoundaryError("symbol is outside the supported equity spelling subset")
    _, quantity_exponent = _decimal_parts(intent.quantity)
    if quantity_exponent < 0:
        raise AlpacaPaperBoundaryError("only whole-share quantities are supported")
    body: dict[str, object] = {
        "symbol": intent.instrument.symbol, "side": intent.side.value,
        "qty": _decimal_text(intent.quantity), "type": intent.order_type.value,
        "time_in_force": "day", "order_class": "simple",
        "client_order_id": client_order_id(intent), "extended_hours": False,
    }
    if intent.order_type is OrderType.LIMIT:
        _, exponent = _decimal_parts(intent.limit_price)
        if exponent < (-2 if intent.limit_price >= 1 else -4):
            raise AlpacaPaperBoundaryError("limit price exceeds the supported equity tick precision")
        body["limit_price"] = _decimal_text(intent.limit_price)
    return body


def _response_decimal(value: object) -> Decimal:
    if type(value) is not str or len(value) > 64 or not _NUMBER.fullmatch(value):
        raise ValueError("invalid numeric response field")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("invalid numeric response field")
    return number


def _acknowledgement(response: TransportResponse, intent: OrderIntent) -> OrderAcknowledgement:
    """Validate an actual order-shaped response, independently of the request body."""
    if not isinstance(response, TransportResponse) or type(response.status) is not int or not 200 <= response.status < 300:
        raise ValueError("ambiguous transport outcome")
    value = response.body
    if not isinstance(value, Mapping):
        raise ValueError("invalid response shape")
    expected = {
        "client_order_id": client_order_id(intent), "symbol": intent.instrument.symbol,
        "side": intent.side.value, "type": intent.order_type.value,
        "time_in_force": "day", "asset_class": "us_equity",
    }
    if any(type(value.get(key)) is not str or value[key] != wanted for key, wanted in expected.items()):
        raise ValueError("order identity mismatch")
    if (type(value.get("status")) is not str or value["status"] not in _ACKNOWLEDGED_STATUSES
            or type(value.get("order_class")) is not str or value["order_class"] not in {"", "simple"}
            or value.get("extended_hours") is not False):
        raise ValueError("unsupported order state or execution features")
    if value.get("order_type") is not None and value["order_type"] != intent.order_type.value:
        raise ValueError("inconsistent order type aliases")
    if _response_decimal(value.get("qty")) != intent.quantity:
        raise ValueError("quantity mismatch")
    if intent.order_type is OrderType.LIMIT:
        if _response_decimal(value.get("limit_price")) != intent.limit_price:
            raise ValueError("limit price mismatch")
    elif value.get("limit_price") is not None:
        raise ValueError("unexpected limit price")
    if _response_decimal(value.get("filled_qty")) != 0:
        raise ValueError("fill evidence is outside this submission receipt boundary")
    if any(value.get(key) is not None for key in (
        "notional", "stop_price", "trail_price", "trail_percent", "take_profit", "stop_loss",
        "filled_avg_price", "filled_at", "canceled_at", "expired_at", "failed_at", "replaced_at",
        "replaced_by", "replaces",
    )) or value.get("legs") not in (None, []):
        raise ValueError("unexpected order economics or lifecycle evidence")
    broker_id = value.get("id")
    if type(broker_id) is not str or len(broker_id) != 36 or str(UUID(broker_id)) != broker_id:
        raise ValueError("invalid broker order identity")
    submitted_at = value.get("submitted_at")
    if type(submitted_at) is not str or len(submitted_at) > 64 or not _TIMESTAMP.fullmatch(submitted_at):
        raise ValueError("invalid broker timestamp")
    timestamp = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("invalid broker timestamp")
    return OrderAcknowledgement(
        "alpaca-paper-v1:" + broker_id, intent.intent_id, intent.scope, broker_id, timestamp,
    )


class AlpacaPaperBoundary:
    """One locally claimed attempt, with explicit read-only recovery afterwards."""

    def __init__(self, journal: PaperOrderJournal, transport: PaperTransport, *, binding: PaperDeploymentBinding) -> None:
        self.journal, self.transport, self.binding = journal, transport, binding
        self.account_id, self.deployment_id = binding.account_id, binding.deployment_id
        self._validate_identity()

    def _validate_identity(self, intent: OrderIntent | None = None) -> None:
        try:
            if not isinstance(self.binding, PaperDeploymentBinding):
                raise PaperDeploymentBindingError()
            self.binding.require_same(self.journal.binding)
            self.binding.require_match(
                account_id=self.journal.account_id, deployment_id=self.journal.deployment_id,
            )
        except PaperDeploymentBindingError:
            raise AlpacaPaperBoundaryError("local paper identity does not match journal identity")
        if intent is not None and (intent.scope.execution_domain is not ExecutionDomain.PAPER
                or intent.scope.account_id != self.account_id or intent.scope.deployment_id != self.deployment_id):
            raise AlpacaPaperBoundaryError("intent does not match the local paper identity")

    def _read(self, intent_id: str) -> JournalEntry | None:
        try:
            return self.journal.get(intent_id)
        except Exception:
            pass
        raise AlpacaPaperPersistenceError("paper journal could not be read; submission remains prohibited") from None

    def _unknown(self, intent_id: str) -> JournalEntry:
        current = self._read(intent_id)
        if current is None or current.state is JournalState.QUEUED:
            raise AlpacaPaperPersistenceError("durable submission claim could not be verified")
        if current.state is not JournalState.SUBMISSION_PENDING:
            return current
        conflict = False
        try:
            return self.journal.mark_submission_unknown(intent_id)
        except JournalConflictError:
            conflict = True
        except Exception:
            pass
        if conflict:
            # Another recovery can acknowledge between our read and transition.
            fresh = self._read(intent_id)
            if fresh is not None and fresh.state in {JournalState.SUBMISSION_UNKNOWN, JournalState.ACKNOWLEDGED, JournalState.REJECTED}:
                return fresh
        raise AlpacaPaperPersistenceError("ambiguous submission could not be recorded; do not resubmit") from None

    def _finish(self, acknowledgement: OrderAcknowledgement | None, intent_id: str) -> JournalEntry:
        if acknowledgement is None:
            return self._unknown(intent_id)
        conflict = False
        try:
            return self.journal.record_acknowledgement(acknowledgement)
        except JournalConflictError:
            conflict = True
        except Exception:
            pass
        if conflict:
            raise AlpacaPaperPersistenceError("submission receipt conflicts with durable journal evidence; do not resubmit") from None
        raise AlpacaPaperPersistenceError("submission receipt could not be persisted; do not resubmit") from None

    def submit(self, intent: OrderIntent) -> JournalEntry:
        request_for(intent)
        self._validate_identity(intent)
        try:
            self.journal.enqueue(intent)
            claimed = self.journal.claim_submission(intent.intent_id)
        except Exception:
            pass
        else:
            if claimed is None:
                fresh = self._read(intent.intent_id)
                if fresh is not None:
                    return fresh
            else:
                acknowledgement = None
                try:
                    body = request_for(claimed.intent)
                    response = self.transport.post(ORDERS_URL, body)
                    acknowledgement = _acknowledgement(response, claimed.intent)
                except Exception:
                    pass  # Never retain, format, or log untrusted exception/payload text.
                return self._finish(acknowledgement, intent.intent_id)
        raise AlpacaPaperPersistenceError("submission claim could not be verified; no POST was attempted") from None

    def recover(self, intent_id: str) -> JournalEntry:
        self._validate_identity()
        entry = self._read(intent_id)
        if entry is None or entry.state is JournalState.QUEUED:
            raise AlpacaPaperBoundaryError("recovery requires an existing submission claim")
        if entry.state in {JournalState.ACKNOWLEDGED, JournalState.REJECTED}:
            return entry
        request_for(entry.intent)
        self._validate_identity(entry.intent)
        acknowledgement = None
        try:
            response = self.transport.get(LOOKUP_URL + "?client_order_id=" + client_order_id(entry.intent))
            acknowledgement = _acknowledgement(response, entry.intent)
        except Exception:
            pass
        return self._finish(acknowledgement, intent_id)
