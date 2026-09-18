from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from execution import (
    ExecutionDomain, ExecutionScope, Instrument, JournalConflictError, JournalState, OrderAcknowledgement, Rejection,
    OrderIntent, OrderSide, OrderType, PaperJournalError, PaperOrderJournal,
    QuantityUnit, RiskMetadata, TimeInForce,
)
from execution.paper_binding import PaperDeploymentBinding


NOW = datetime(2026, 9, 3, 14, tzinfo=timezone.utc)
ACCOUNT = "54c41ab9-eab7-4823-a47d-2a0b63b18590"
BINDING = PaperDeploymentBinding(
    account_id=ACCOUNT,
    deployment_id="deployment",
    owner_attestation_reference="owner-attestation:paper-journal-fixture-20260903",
)


def intent(*, quantity: Decimal = Decimal("2"), price: Decimal = Decimal("23.45"), domain: ExecutionDomain = ExecutionDomain.PAPER, account: str = ACCOUNT, key: str = "key") -> OrderIntent:
    return OrderIntent("intent", ExecutionScope(domain, "strategy", "run", "deployment", account, key), RiskMetadata("policy", "decision", NOW), Instrument("SCHX", "etf", "USD", QuantityUnit.SHARES, True), OrderSide.BUY, quantity, OrderType.LIMIT, TimeInForce.DAY, NOW, price)


def journal(tmp_path) -> PaperOrderJournal:
    return PaperOrderJournal(tmp_path / "paper.sqlite3", binding=BINDING)


def test_reopen_preserves_intent_and_decimal_semantic_retry(tmp_path) -> None:
    path = tmp_path / "paper.sqlite3"
    with journal(tmp_path) as first:
        assert first.enqueue(intent(quantity=Decimal("2.0"))).state is JournalState.QUEUED
    with PaperOrderJournal(path, binding=BINDING) as reopened:
        assert reopened.enqueue(intent(quantity=Decimal("2"))).intent.quantity == Decimal("2")


def test_changed_payload_or_duplicate_intent_identity_conflicts(tmp_path) -> None:
    with journal(tmp_path) as store:
        store.enqueue(intent())
        with pytest.raises(JournalConflictError):
            store.enqueue(intent(quantity=Decimal("3")))
        with pytest.raises(JournalConflictError):
            store.enqueue(intent(key="other-key"))


def test_high_precision_decimal_is_preserved_and_not_collapsed(tmp_path) -> None:
    with journal(tmp_path) as store:
        price = Decimal("1234567890123456789012345678.11")
        stored = store.enqueue(intent(price=price))
        assert stored.intent.limit_price == price
        with pytest.raises(JournalConflictError):
            store.enqueue(intent(price=Decimal("1234567890123456789012345678.12")))


def test_live_or_wrong_account_is_rejected(tmp_path) -> None:
    with journal(tmp_path) as store:
        with pytest.raises(PaperJournalError):
            store.enqueue(intent(domain=ExecutionDomain.LIVE))
        with pytest.raises(PaperJournalError):
            store.enqueue(intent(account="other"))


def test_claim_is_durable_and_only_one_connection_wins(tmp_path) -> None:
    path = tmp_path / "paper.sqlite3"
    with journal(tmp_path) as first:
        first.enqueue(intent())
        with PaperOrderJournal(path, binding=BINDING) as second:
            assert first.claim_submission("intent").state is JournalState.SUBMISSION_PENDING
            assert second.claim_submission("intent") is None
    with PaperOrderJournal(path, binding=BINDING) as reopened:
        assert reopened.claim_submission("intent") is None


def test_true_concurrent_connections_allow_only_one_claim(tmp_path) -> None:
    path = tmp_path / "paper.sqlite3"
    with journal(tmp_path) as store:
        store.enqueue(intent())
    barrier = Barrier(2)
    def claim() -> bool:
        with PaperOrderJournal(path, binding=BINDING) as store:
            barrier.wait()
            return store.claim_submission("intent") is not None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: claim(), range(2))) == 1


def test_unknown_claim_is_never_requeued_after_restart(tmp_path) -> None:
    path = tmp_path / "paper.sqlite3"
    with journal(tmp_path) as store:
        store.enqueue(intent())
        store.claim_submission("intent")
        assert store.mark_submission_unknown("intent").state is JournalState.SUBMISSION_UNKNOWN
    with PaperOrderJournal(path, binding=BINDING) as reopened:
        assert reopened.claim_submission("intent") is None


def test_foreign_database_is_untouched(tmp_path) -> None:
    path = tmp_path / "research.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE research_runs(id TEXT)")
    connection.commit(); connection.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PaperJournalError, match="foreign"):
        PaperOrderJournal(path, binding=BINDING)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_event_failure_rolls_back_new_record(tmp_path) -> None:
    with journal(tmp_path) as store:
        store.connection.execute("CREATE TRIGGER block_event BEFORE INSERT ON paper_order_events BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        with pytest.raises(sqlite3.IntegrityError, match="blocked"):
            store.enqueue(intent())
        assert store.connection.execute("SELECT count(*) FROM paper_order_records").fetchone()[0] == 0
        store.connection.execute("DROP TRIGGER block_event")
        assert store.enqueue(intent()).state is JournalState.QUEUED


def test_corrupt_hash_cannot_claim_or_mutate_record(tmp_path) -> None:
    with journal(tmp_path) as store:
        store.enqueue(intent())
        store.connection.execute("UPDATE paper_order_records SET semantic_hash = 'bad' WHERE intent_id = 'intent'")
        with pytest.raises(PaperJournalError):
            store.claim_submission("intent")
        row = store.connection.execute("SELECT state FROM paper_order_records WHERE intent_id = 'intent'").fetchone()
        assert row[0] == "queued"
        assert store.connection.execute("SELECT count(*) FROM paper_order_events WHERE intent_id = 'intent'").fetchone()[0] == 1


def test_state_flip_after_claim_cannot_enable_second_claim(tmp_path) -> None:
    with journal(tmp_path) as store:
        store.enqueue(intent()); store.claim_submission("intent")
        store.connection.execute("UPDATE paper_order_records SET state = 'queued' WHERE intent_id = 'intent'")
        with pytest.raises(PaperJournalError):
            store.claim_submission("intent")


def test_stored_terminal_identity_mismatch_fails_closed(tmp_path) -> None:
    with journal(tmp_path) as store:
        item = intent(); store.enqueue(item); store.claim_submission("intent")
        store.record_acknowledgement(OrderAcknowledgement("ack", "intent", item.scope, "broker-1", NOW))
        store.connection.execute("UPDATE paper_order_records SET broker_order_id = 'broker-2' WHERE intent_id = 'intent'")
        with pytest.raises(PaperJournalError):
            store.enqueue(item)


def test_cross_intent_broker_order_identity_is_rejected(tmp_path) -> None:
    with journal(tmp_path) as store:
        first = intent(); second = OrderIntent("intent-2", ExecutionScope(ExecutionDomain.PAPER, "strategy", "run", "deployment", ACCOUNT, "key-2"), first.risk, first.instrument, first.side, first.quantity, first.order_type, first.time_in_force, first.created_at, first.limit_price)
        store.enqueue(first); store.enqueue(second); store.claim_submission("intent"); store.claim_submission("intent-2")
        store.record_acknowledgement(OrderAcknowledgement("ack-1", "intent", first.scope, "broker-1", NOW))
        with pytest.raises(JournalConflictError, match="another intent"):
            store.record_acknowledgement(OrderAcknowledgement("ack-2", "intent-2", second.scope, "broker-1", NOW))
        assert store.connection.execute("SELECT state FROM paper_order_records WHERE intent_id = 'intent-2'").fetchone()[0] == "submission_pending"


def test_removed_required_unique_constraint_is_refused_on_reopen(tmp_path) -> None:
    path = tmp_path / "paper.sqlite3"
    with journal(tmp_path) as store:
        store.connection.execute("DROP INDEX paper_order_records_broker_order_id_unique")
    with pytest.raises(PaperJournalError, match="schema"):
        PaperOrderJournal(path, binding=BINDING)


def test_terminal_events_validate_scope_and_are_idempotent(tmp_path) -> None:
    with journal(tmp_path) as store:
        item = intent()
        store.enqueue(item); store.claim_submission("intent")
        acknowledgement = OrderAcknowledgement("ack", "intent", item.scope, "broker-1", NOW)
        assert store.record_acknowledgement(acknowledgement).state is JournalState.ACKNOWLEDGED
        assert store.record_acknowledgement(acknowledgement).broker_order_id == "broker-1"
        with pytest.raises(JournalConflictError):
            store.record_acknowledgement(OrderAcknowledgement("ack-2", "intent", item.scope, "broker-2", NOW))
    with journal(tmp_path) as store:
        item = intent()
        store.enqueue(item); store.claim_submission("intent")
        bad_scope = ExecutionScope(ExecutionDomain.PAPER, "strategy", "run", "other", ACCOUNT, "key")
        with pytest.raises(JournalConflictError):
            store.record_rejection(Rejection("reject", "intent", bad_scope, NOW, "BLOCK", "denied"))


@pytest.mark.parametrize("path", ["", ":memory:", "relative.sqlite3"])
def test_nondurable_or_ambiguous_path_is_rejected(path) -> None:
    with pytest.raises(PaperJournalError, match="absolute durable"):
        PaperOrderJournal(path, binding=BINDING)


@pytest.mark.parametrize("field", ["account_id", "deployment_id", "owner_attestation_reference"])
def test_journal_identity_mismatch_cannot_change_existing_file(tmp_path, field) -> None:
    path = tmp_path / "paper.sqlite3"
    with journal(tmp_path) as store:
        store.enqueue(intent())
    before = path.read_bytes()
    values = {"account_id": ACCOUNT, "deployment_id": "deployment", "owner_attestation_reference": BINDING.owner_attestation_reference}
    values[field] = (
        "0ca07231-9205-48f0-9fb5-8e04ae3121be" if field == "account_id"
        else "owner-attestation:other-paper-journal-record" if field == "owner_attestation_reference"
        else "other"
    )
    with pytest.raises(PaperJournalError, match="identity"):
        PaperOrderJournal(path, binding=PaperDeploymentBinding(**values))
    assert path.read_bytes() == before


def test_version_one_journal_is_rejected_without_metadata_migration(tmp_path) -> None:
    path = tmp_path / "paper.sqlite3"
    with journal(tmp_path) as store:
        store.connection.execute("UPDATE paper_journal_metadata SET value='1' WHERE key='schema_version'")
        store.connection.execute("DELETE FROM paper_journal_metadata WHERE key='owner_attestation_reference'")
    before = path.read_bytes()
    with pytest.raises(PaperJournalError, match="schema version"):
        PaperOrderJournal(path, binding=BINDING)
    assert path.read_bytes() == before


def test_decimal_canonicalization_ignores_callers_precision(tmp_path) -> None:
    price = Decimal("23.123456789012345678901234567891")
    with localcontext() as context, journal(tmp_path) as store:
        context.prec = 2
        assert store.enqueue(intent(price=price)).intent.limit_price == price
        assert store.enqueue(intent(price=Decimal(str(price) + "0"))).intent.limit_price == price
        with pytest.raises(JournalConflictError):
            store.enqueue(intent(price=Decimal("23.123456789012345678901234567892")))


def test_concurrent_initialization_enqueue_and_claim_have_one_winner(tmp_path) -> None:
    barrier = Barrier(4)
    def start(_):
        barrier.wait(timeout=10)
        with journal(tmp_path) as store:
            store.enqueue(intent())
            return store.claim_submission("intent") is not None
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(start, range(4))) == 1
    with journal(tmp_path) as store:
        assert store.connection.execute("SELECT count(*) FROM paper_order_records").fetchone()[0] == 1
        assert store.connection.execute("SELECT count(*) FROM paper_order_events").fetchone()[0] == 2
        assert store.claim_submission("intent") is None


def test_concurrent_distinct_intents_cannot_reuse_one_idempotency_key(tmp_path) -> None:
    barrier = Barrier(4)
    def enqueue(number):
        with journal(tmp_path) as store:
            barrier.wait(timeout=10)
            try:
                store.enqueue(replace(intent(), intent_id=f"intent-{number}"))
                return True
            except JournalConflictError:
                return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(enqueue, range(4))) == 1
    with journal(tmp_path) as store:
        assert store.connection.execute("SELECT count(*) FROM paper_order_records").fetchone()[0] == 1
        assert store.connection.execute("SELECT count(*) FROM paper_order_events").fetchone()[0] == 1


def test_failed_initial_metadata_insert_rolls_back_entire_schema(tmp_path, monkeypatch) -> None:
    real_connect = sqlite3.connect
    class FailingInitialization(sqlite3.Connection):
        def executemany(self, sql, parameters):
            if sql.startswith("INSERT INTO paper_journal_metadata"):
                super().execute(sql, next(iter(parameters)))
                raise sqlite3.OperationalError("injected metadata write failure")
            return super().executemany(sql, parameters)
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", lambda *args, **kwargs: real_connect(*args, **kwargs, factory=FailingInitialization))
        with pytest.raises(sqlite3.OperationalError, match="injected"):
            journal(tmp_path)
    connection = real_connect(tmp_path / "paper.sqlite3")
    try:
        assert connection.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0
    finally:
        connection.close()
    with journal(tmp_path) as store:
        assert store.enqueue(intent()).state is JournalState.QUEUED


def snapshot(store):
    return tuple(tuple(tuple(row) for row in store.connection.execute(f"SELECT * FROM {table} ORDER BY 1"))
                 for table in ("paper_order_records", "paper_order_events"))


@pytest.mark.parametrize("operation", ["enqueue", "claim", "unknown", "acknowledgement", "rejection"])
def test_operational_event_failure_rolls_back_every_transition(tmp_path, operation) -> None:
    with journal(tmp_path) as store:
        item = intent()
        if operation != "enqueue":
            store.enqueue(item)
        if operation in {"unknown", "acknowledgement", "rejection"}:
            store.claim_submission(item.intent_id)
        actions = {
            "enqueue": lambda: store.enqueue(item),
            "claim": lambda: store.claim_submission(item.intent_id),
            "unknown": lambda: store.mark_submission_unknown(item.intent_id),
            "acknowledgement": lambda: store.record_acknowledgement(OrderAcknowledgement("ack", item.intent_id, item.scope, "broker", NOW)),
            "rejection": lambda: store.record_rejection(Rejection("reject", item.intent_id, item.scope, NOW, "DENIED", "fixture denial")),
        }
        before = snapshot(store)
        store.connection.execute("CREATE TRIGGER fail_event BEFORE INSERT ON paper_order_events BEGIN SELECT missing_journal_function(); END")
        with pytest.raises(sqlite3.OperationalError, match="missing_journal_function"):
            actions[operation]()
        assert not store.connection.in_transaction
        assert snapshot(store) == before
        store.connection.execute("DROP TRIGGER fail_event")
        assert actions[operation]() is not None


@pytest.mark.parametrize("schema_change", [
    "missing_primary_key", "missing_idempotency_unique", "nonunique_broker_index",
    "wrong_broker_index_column", "partial_broker_index", "wrong_event_primary_key",
])
def test_reopen_checks_actual_schema_constraints_and_preserves_bytes(tmp_path, schema_change) -> None:
    path = tmp_path / "paper.sqlite3"
    with journal(tmp_path) as store:
        if schema_change in {"missing_primary_key", "missing_idempotency_unique"}:
            original = store.connection.execute("SELECT sql FROM sqlite_master WHERE name='paper_order_records'").fetchone()[0]
            if schema_change == "missing_primary_key":
                changed = original.replace("intent_id TEXT PRIMARY KEY", "intent_id TEXT")
            else:
                changed = original.replace("idempotency_key TEXT NOT NULL UNIQUE", "idempotency_key TEXT NOT NULL")
            store.connection.execute("DROP TABLE paper_order_records")
            store.connection.execute(changed)
            store.connection.execute("CREATE UNIQUE INDEX paper_order_records_broker_order_id_unique ON paper_order_records(broker_order_id)")
        elif schema_change == "wrong_event_primary_key":
            original = store.connection.execute("SELECT sql FROM sqlite_master WHERE name='paper_order_events'").fetchone()[0]
            store.connection.execute("DROP TABLE paper_order_events")
            store.connection.execute(original.replace("sequence INTEGER PRIMARY KEY AUTOINCREMENT", "sequence INTEGER"))
        else:
            store.connection.execute("DROP INDEX paper_order_records_broker_order_id_unique")
            definitions = {
                "nonunique_broker_index": "CREATE INDEX paper_order_records_broker_order_id_unique ON paper_order_records(broker_order_id)",
                "wrong_broker_index_column": "CREATE UNIQUE INDEX paper_order_records_broker_order_id_unique ON paper_order_records(rejection)",
                "partial_broker_index": "CREATE UNIQUE INDEX paper_order_records_broker_order_id_unique ON paper_order_records(broker_order_id) WHERE broker_order_id='only-one-value'",
            }
            store.connection.execute(definitions[schema_change])
    before = path.read_bytes()
    with pytest.raises(PaperJournalError, match="schema"):
        journal(tmp_path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("corruption", [
    "missing_ack", "opposite_terminal_payload", "missing_broker", "ack_intent", "ack_scope",
    "malformed_ack", "queued_payload", "terminal_payload", "missing_claim_event", "extra_state_event",
])
def test_terminal_corruption_fails_closed_without_mutating_evidence(tmp_path, corruption) -> None:
    with journal(tmp_path) as store:
        item = intent()
        store.enqueue(item)
        store.claim_submission(item.intent_id)
        store.record_acknowledgement(OrderAcknowledgement("ack", item.intent_id, item.scope, "broker", NOW))
        if corruption == "missing_ack":
            store.connection.execute("UPDATE paper_order_records SET acknowledgement=NULL")
        elif corruption == "opposite_terminal_payload":
            store.connection.execute("UPDATE paper_order_records SET rejection='{}'")
        elif corruption == "missing_broker":
            store.connection.execute("UPDATE paper_order_records SET broker_order_id=NULL")
        elif corruption in {"ack_intent", "ack_scope"}:
            value = json.loads(store.connection.execute("SELECT acknowledgement FROM paper_order_records").fetchone()[0])
            if corruption == "ack_intent":
                value["intent_id"] = "other"
            else:
                value["scope"]["account_id"] = "other"
            store.connection.execute("UPDATE paper_order_records SET acknowledgement=?", (json.dumps(value, sort_keys=True, separators=(",", ":")),))
        elif corruption == "malformed_ack":
            store.connection.execute("UPDATE paper_order_records SET acknowledgement='{' ")
        elif corruption in {"queued_payload", "terminal_payload"}:
            event_type = "queued" if corruption == "queued_payload" else "acknowledged"
            store.connection.execute("UPDATE paper_order_events SET payload='{}' WHERE event_type=?", (event_type,))
        elif corruption == "missing_claim_event":
            store.connection.execute("DELETE FROM paper_order_events WHERE event_type='submission_pending'")
        else:
            store.connection.execute("INSERT INTO paper_order_events(intent_id,event_type,payload) VALUES ('intent','acknowledged','{}')")
        before = snapshot(store)
        with pytest.raises(PaperJournalError):
            store.enqueue(item)
        assert not store.connection.in_transaction
        assert snapshot(store) == before


@pytest.mark.parametrize("operation", ["claim", "unknown", "acknowledgement", "rejection"])
def test_every_transition_validates_existing_evidence_before_writing(tmp_path, operation) -> None:
    with journal(tmp_path) as store:
        item = intent()
        store.enqueue(item)
        if operation != "claim":
            store.claim_submission(item.intent_id)
        store.connection.execute("UPDATE paper_order_records SET semantic_hash='corrupt'")
        actions = {
            "claim": lambda: store.claim_submission(item.intent_id),
            "unknown": lambda: store.mark_submission_unknown(item.intent_id),
            "acknowledgement": lambda: store.record_acknowledgement(OrderAcknowledgement("ack", item.intent_id, item.scope, "broker", NOW)),
            "rejection": lambda: store.record_rejection(Rejection("reject", item.intent_id, item.scope, NOW, "DENIED", "fixture denial")),
        }
        before = snapshot(store)
        with pytest.raises(PaperJournalError):
            actions[operation]()
        assert snapshot(store) == before
        assert not store.connection.in_transaction


@pytest.mark.parametrize("terminal", ["acknowledgement", "rejection"])
def test_unknown_submission_accepts_one_durable_terminal_outcome(tmp_path, terminal) -> None:
    with journal(tmp_path) as store:
        item = intent()
        store.enqueue(item)
        store.claim_submission(item.intent_id)
        store.mark_submission_unknown(item.intent_id)
        record = (OrderAcknowledgement("ack", item.intent_id, item.scope, "broker", NOW)
                  if terminal == "acknowledgement" else Rejection("reject", item.intent_id, item.scope, NOW, "DENIED", "fixture denial"))
        action = getattr(store, f"record_{terminal}")
        first = action(record)
        before = snapshot(store)
        assert action(record) == first
        assert snapshot(store) == before
    with journal(tmp_path) as store:
        assert store.enqueue(item) == first
        assert store.claim_submission(item.intent_id) is None


def test_claim_returns_its_committed_entry_if_another_connection_advances_state(tmp_path, monkeypatch) -> None:
    real_connect = sqlite3.connect
    class AfterCommitConnection(sqlite3.Connection):
        after_commit = None
        def execute(self, sql, parameters=()):
            result = super().execute(sql, parameters)
            if sql == "COMMIT" and self.after_commit is not None:
                callback, self.after_commit = self.after_commit, None
                callback()
            return result
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: real_connect(*args, **kwargs, factory=AfterCommitConnection))
    with journal(tmp_path) as store:
        store.enqueue(intent())
        def advance_committed_claim():
            with journal(tmp_path) as other:
                other.mark_submission_unknown("intent")
        store.connection.after_commit = advance_committed_claim
        claimed = store.claim_submission("intent")
        assert claimed.state is JournalState.SUBMISSION_PENDING
        assert store.enqueue(intent()).state is JournalState.SUBMISSION_UNKNOWN
        assert store.claim_submission("intent") is None


def test_newly_written_corrupt_evidence_rolls_back_before_claim_returns(tmp_path) -> None:
    with journal(tmp_path) as store:
        store.enqueue(intent())
        before = snapshot(store)
        store.connection.execute("""CREATE TRIGGER corrupt_claim AFTER INSERT ON paper_order_events
            WHEN NEW.event_type='submission_pending'
            BEGIN UPDATE paper_order_records SET broker_order_id='unexpected' WHERE intent_id=NEW.intent_id; END""")
        with pytest.raises(PaperJournalError, match="nonterminal"):
            store.claim_submission("intent")
        assert snapshot(store) == before
        assert not store.connection.in_transaction
