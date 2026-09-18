"""Durable paper-only order-intent journal; it never calls a broker."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from execution.contracts import (
    ExecutionContractError,
    ExecutionDomain,
    ExecutionScope,
    OrderAcknowledgement,
    OrderIntent,
    Rejection,
    to_primitive,
)
from execution.paper_binding import PaperDeploymentBinding


# Version 2 adds owner-attestation metadata. Version 1 journals are rejected;
# this offline slice deliberately supplies no migration path.
JOURNAL_SCHEMA_VERSION = 2
ENVELOPE_TYPE = "quant_factory.paper_order_intent"
ENVELOPE_VERSION = 1


class PaperJournalError(RuntimeError):
    """Raised when a journal cannot safely preserve paper-order evidence."""


class JournalConflictError(PaperJournalError):
    """Raised when a stable idempotency or intent identity changes meaning."""


class JournalState(str, Enum):
    QUEUED = "queued"
    SUBMISSION_PENDING = "submission_pending"
    SUBMISSION_UNKNOWN = "submission_unknown"
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"


@dataclass(frozen=True)
class JournalEntry:
    intent: OrderIntent
    state: JournalState
    broker_order_id: str | None
    acknowledgement: OrderAcknowledgement | None
    rejection: Rejection | None


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ExecutionContractError("journal Decimal values must be finite")
    sign, digits, exponent = value.as_tuple()
    digits = list(digits)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = "".join(str(digit) for digit in digits) or "0"
    if coefficient == "0":
        return "0"
    return f"{'-' if sign else ''}{coefficient}e{exponent}"


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if hasattr(value, "__dataclass_fields__"):
        return {field: _canonical(getattr(value, field)) for field in value.__dataclass_fields__}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return to_primitive(value)
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    return value


def _intent_envelope(intent: OrderIntent) -> str:
    envelope = {"type": ENVELOPE_TYPE, "version": ENVELOPE_VERSION, "intent": _canonical(intent)}
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _intent_hash(envelope: str) -> str:
    return hashlib.sha256(envelope.encode("utf-8")).hexdigest()


def _decode_intent(envelope: str) -> OrderIntent:
    from execution.contracts import Instrument, OrderSide, OrderType, QuantityUnit, RiskMetadata, TimeInForce

    document = json.loads(envelope)
    if document.get("type") != ENVELOPE_TYPE or document.get("version") != ENVELOPE_VERSION:
        raise PaperJournalError("unsupported journal intent envelope")
    value = document["intent"]
    scope_value = value["scope"]
    risk_value = value["risk"]
    instrument_value = value["instrument"]
    parse_time = lambda text: datetime.fromisoformat(text.replace("Z", "+00:00"))
    return OrderIntent(
        intent_id=value["intent_id"],
        scope=ExecutionScope(ExecutionDomain(scope_value["execution_domain"]), scope_value["strategy_id"], scope_value["run_id"], scope_value["deployment_id"], scope_value["account_id"], scope_value["idempotency_key"]),
        risk=RiskMetadata(risk_value["policy_id"], risk_value["decision_id"], parse_time(risk_value["evaluated_at"])),
        instrument=Instrument(instrument_value["symbol"], instrument_value["asset_class"], instrument_value["currency"], QuantityUnit(instrument_value["quantity_unit"]), instrument_value["whole_unit_only"]),
        side=OrderSide(value["side"]), quantity=Decimal(value["quantity"]), order_type=OrderType(value["order_type"]),
        time_in_force=TimeInForce(value["time_in_force"]), created_at=parse_time(value["created_at"]),
        limit_price=None if value["limit_price"] is None else Decimal(value["limit_price"]),
        stop_price=None if value["stop_price"] is None else Decimal(value["stop_price"]),
    )


# These definitions are the versioned storage contract. Reopen accepts the same
# DDL (ignoring whitespace/case), not merely familiar table or index names.
_SCHEMA = {
    ("table", "paper_journal_metadata"): """CREATE TABLE paper_journal_metadata (
        key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
    ("table", "paper_order_records"): """CREATE TABLE paper_order_records (
        intent_id TEXT PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        envelope TEXT NOT NULL,
        semantic_hash TEXT NOT NULL,
        state TEXT NOT NULL,
        broker_order_id TEXT,
        acknowledgement TEXT,
        rejection TEXT)""",
    ("table", "paper_order_events"): """CREATE TABLE paper_order_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        intent_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL)""",
    ("index", "paper_order_records_broker_order_id_unique"):
        "CREATE UNIQUE INDEX paper_order_records_broker_order_id_unique ON paper_order_records(broker_order_id)",
}


def _schema_sql(sql: str) -> str:
    return "".join(sql.split()).upper()


def _payload(record: OrderAcknowledgement | Rejection) -> str:
    return json.dumps(to_primitive(record), sort_keys=True, separators=(",", ":"))


def _scope(value: dict[str, Any]) -> ExecutionScope:
    return ExecutionScope(
        ExecutionDomain(value["execution_domain"]), value["strategy_id"],
        value["run_id"], value["deployment_id"], value["account_id"],
        value["idempotency_key"],
    )


class PaperOrderJournal:
    """A dedicated SQLite journal providing durable at-most-one submission claims."""

    def __init__(self, path: str | Path, *, binding: PaperDeploymentBinding) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise PaperJournalError("paper journal requires an absolute durable database path")
        if not isinstance(binding, PaperDeploymentBinding):
            raise PaperJournalError("paper journal requires a paper deployment binding")
        self.binding = binding
        self.account_id = binding.account_id
        self.deployment_id = binding.deployment_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        try:
            self._initialize()
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "PaperOrderJournal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.execute("COMMIT")
        except BaseException:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise

    def _initialize(self) -> None:
        with self._transaction():
            objects = {
                (row[0], row[1]): row[2]
                for row in self.connection.execute(
                    "SELECT type, name, sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"
                )
            }
            expected_metadata = {
                "schema_version": str(JOURNAL_SCHEMA_VERSION),
                "journal_kind": "paper_order_intent", "execution_domain": "paper",
                "account_id": self.account_id, "deployment_id": self.deployment_id,
                "owner_attestation_reference": self.binding.owner_attestation_reference,
            }
            if not objects:
                for statement in _SCHEMA.values():
                    self.connection.execute(statement)
                self.connection.executemany(
                    "INSERT INTO paper_journal_metadata(key, value) VALUES (?, ?)",
                    expected_metadata.items(),
                )
            else:
                if set(objects) != set(_SCHEMA):
                    raise PaperJournalError("refusing foreign database or incompatible journal schema")
                if any(_schema_sql(objects[key]) != _schema_sql(statement) for key, statement in _SCHEMA.items()):
                    raise PaperJournalError("paper journal schema does not satisfy version 2 constraints")
            metadata = dict(self.connection.execute("SELECT key, value FROM paper_journal_metadata"))
            if metadata.get("schema_version") != str(JOURNAL_SCHEMA_VERSION):
                raise PaperJournalError("paper journal schema version is unsupported; no migration is available")
            if metadata != expected_metadata:
                raise PaperJournalError("paper journal metadata does not match requested paper identity")

    def _validate_intent(self, intent: OrderIntent) -> None:
        if not isinstance(intent, OrderIntent):
            raise PaperJournalError("paper journal requires an OrderIntent")
        scope = intent.scope
        if scope.execution_domain is not ExecutionDomain.PAPER:
            raise PaperJournalError("paper journal rejects live order intents")
        if scope.account_id != self.account_id or scope.deployment_id != self.deployment_id:
            raise PaperJournalError("order intent scope does not match paper journal identity")

    def _entry(self, row: sqlite3.Row) -> JournalEntry:
        # Caller holds a transaction, so the row and its event stream share one
        # snapshot. Never re-read evidence after committing a submission claim.
        try:
            return self._validated_entry(row)
        except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as exc:
            raise PaperJournalError("stored journal evidence is malformed") from exc

    def _validated_entry(self, row: sqlite3.Row) -> JournalEntry:
        intent = _decode_intent(row["envelope"])
        if (_intent_hash(row["envelope"]) != row["semantic_hash"]
                or _intent_envelope(intent) != row["envelope"]
                or intent.intent_id != row["intent_id"]
                or intent.scope.idempotency_key != row["idempotency_key"]):
            raise PaperJournalError("stored journal record has inconsistent identity or semantic hash")
        self._validate_intent(intent)
        state = JournalState(row["state"])
        acknowledgement = None
        rejection = None
        if state is JournalState.ACKNOWLEDGED:
            if row["acknowledgement"] is None or row["rejection"] is not None or row["broker_order_id"] is None:
                raise PaperJournalError("acknowledged journal record lacks consistent terminal evidence")
            value = json.loads(row["acknowledgement"])
            acknowledgement = OrderAcknowledgement(
                value["acknowledgement_id"], value["intent_id"], _scope(value["scope"]),
                value["broker_order_id"], datetime.fromisoformat(value["acknowledged_at"].replace("Z", "+00:00")),
            )
            if (acknowledgement.scope != intent.scope or acknowledgement.intent_id != intent.intent_id
                    or acknowledgement.broker_order_id != row["broker_order_id"]
                    or _payload(acknowledgement) != row["acknowledgement"]):
                raise PaperJournalError("stored acknowledgement identity conflicts with intent")
        elif state is JournalState.REJECTED:
            if row["rejection"] is None or row["acknowledgement"] is not None or row["broker_order_id"] is not None:
                raise PaperJournalError("rejected journal record lacks consistent terminal evidence")
            value = json.loads(row["rejection"])
            rejection = Rejection(
                value["rejection_id"], value["intent_id"], _scope(value["scope"]),
                datetime.fromisoformat(value["rejected_at"].replace("Z", "+00:00")),
                value["reason_code"], value["reason"],
            )
            if (rejection.scope != intent.scope or rejection.intent_id != intent.intent_id
                    or _payload(rejection) != row["rejection"]):
                raise PaperJournalError("stored rejection identity conflicts with intent")
        elif any(row[column] is not None for column in ("broker_order_id", "acknowledgement", "rejection")):
            raise PaperJournalError("nonterminal journal record contains terminal evidence")

        events = self.connection.execute(
            "SELECT event_type, payload FROM paper_order_events WHERE intent_id = ? ORDER BY sequence",
            (intent.intent_id,),
        ).fetchall()
        event_types = [event[0] for event in events]
        prefix = ["queued", "submission_pending"]
        allowed_sequences = {
            JournalState.QUEUED: [["queued"]],
            JournalState.SUBMISSION_PENDING: [prefix],
            JournalState.SUBMISSION_UNKNOWN: [prefix + ["submission_unknown"]],
            JournalState.ACKNOWLEDGED: [prefix + ["acknowledged"], prefix + ["submission_unknown", "acknowledged"]],
            JournalState.REJECTED: [prefix + ["rejected"], prefix + ["submission_unknown", "rejected"]],
        }
        if event_types not in allowed_sequences[state]:
            raise PaperJournalError("journal event history conflicts with stored state")
        payloads = {
            "queued": row["envelope"], "submission_pending": "{}", "submission_unknown": "{}",
            "acknowledged": row["acknowledgement"], "rejected": row["rejection"],
        }
        if any(event[1] != payloads[event[0]] for event in events):
            raise PaperJournalError("journal event payload conflicts with stored evidence")
        return JournalEntry(intent, state, row["broker_order_id"], acknowledgement, rejection)

    def _row(self, intent_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM paper_order_records WHERE intent_id = ?", (intent_id,),
        ).fetchone()

    def get(self, intent_id: str) -> JournalEntry | None:
        """Read validated evidence in one snapshot without creating or claiming it."""
        if not isinstance(intent_id, str) or not intent_id.strip():
            raise PaperJournalError("journal lookup requires an intent identity")
        with self._transaction():
            row = self._row(intent_id)
            return None if row is None else self._entry(row)

    def enqueue(self, intent: OrderIntent) -> JournalEntry:
        self._validate_intent(intent)
        envelope = _intent_envelope(intent)
        semantic_hash = _intent_hash(envelope)
        with self._transaction():
            existing = self.connection.execute(
                "SELECT * FROM paper_order_records WHERE idempotency_key = ? OR intent_id = ?",
                (intent.scope.idempotency_key, intent.intent_id),
            ).fetchall()
            if existing:
                entries = [self._entry(row) for row in existing]
                if (len(existing) == 1 and existing[0]["intent_id"] == intent.intent_id
                        and existing[0]["idempotency_key"] == intent.scope.idempotency_key
                        and existing[0]["semantic_hash"] == semantic_hash):
                    return entries[0]
                raise JournalConflictError("idempotency key or intent id already identifies a different intent")
            self.connection.execute(
                "INSERT INTO paper_order_records VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (intent.intent_id, intent.scope.idempotency_key, envelope, semantic_hash, JournalState.QUEUED.value),
            )
            self.connection.execute(
                "INSERT INTO paper_order_events(intent_id, event_type, payload) VALUES (?, ?, ?)",
                (intent.intent_id, "queued", envelope),
            )
            return self._entry(self._row(intent.intent_id))

    def claim_submission(self, intent_id: str) -> JournalEntry | None:
        with self._transaction():
            row = self._row(intent_id)
            if row is None:
                return None
            current = self._entry(row)
            if current.state is not JournalState.QUEUED:
                return None
            self.connection.execute(
                "UPDATE paper_order_records SET state = ? WHERE intent_id = ?",
                (JournalState.SUBMISSION_PENDING.value, intent_id),
            )
            self.connection.execute(
                "INSERT INTO paper_order_events(intent_id, event_type, payload) VALUES (?, ?, ?)",
                (intent_id, "submission_pending", "{}"),
            )
            return self._entry(self._row(intent_id))

    def mark_submission_unknown(self, intent_id: str) -> JournalEntry:
        with self._transaction():
            row = self._row(intent_id)
            if row is None or self._entry(row).state is not JournalState.SUBMISSION_PENDING:
                raise JournalConflictError("journal state does not allow this transition")
            self.connection.execute(
                "UPDATE paper_order_records SET state = ? WHERE intent_id = ?",
                (JournalState.SUBMISSION_UNKNOWN.value, intent_id),
            )
            self.connection.execute(
                "INSERT INTO paper_order_events(intent_id, event_type, payload) VALUES (?, ?, ?)",
                (intent_id, "submission_unknown", "{}"),
            )
            return self._entry(self._row(intent_id))

    def record_acknowledgement(self, acknowledgement: OrderAcknowledgement) -> JournalEntry:
        return self._record_terminal(acknowledgement, JournalState.ACKNOWLEDGED, "acknowledgement")

    def record_rejection(self, rejection: Rejection) -> JournalEntry:
        return self._record_terminal(rejection, JournalState.REJECTED, "rejection")

    def _record_terminal(self, record: OrderAcknowledgement | Rejection, state: JournalState, column: str) -> JournalEntry:
        payload = _payload(record)
        broker_order_id = record.broker_order_id if isinstance(record, OrderAcknowledgement) else None
        with self._transaction():
            row = self._row(record.intent_id)
            if row is None:
                raise JournalConflictError("terminal event intent does not exist in journal")
            current = self._entry(row)
            if current.intent.scope != record.scope:
                raise JournalConflictError("terminal event intent scope does not match journal")
            if current.state is state and row[column] == payload:
                return current
            if current.state not in {JournalState.SUBMISSION_PENDING, JournalState.SUBMISSION_UNKNOWN}:
                raise JournalConflictError("journal state does not allow this terminal event")
            if broker_order_id is not None and self.connection.execute(
                    "SELECT 1 FROM paper_order_records WHERE broker_order_id = ? AND intent_id != ?",
                    (broker_order_id, record.intent_id),
            ).fetchone():
                raise JournalConflictError("broker order identity already belongs to another intent")
            self.connection.execute(
                f"UPDATE paper_order_records SET state = ?, broker_order_id = ?, {column} = ? WHERE intent_id = ?",
                (state.value, broker_order_id, payload, record.intent_id),
            )
            self.connection.execute(
                "INSERT INTO paper_order_events(intent_id, event_type, payload) VALUES (?, ?, ?)",
                (record.intent_id, state.value, payload),
            )
            return self._entry(self._row(record.intent_id))
