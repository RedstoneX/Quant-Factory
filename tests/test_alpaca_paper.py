from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import ast
import json
from pathlib import Path
import sqlite3
from threading import Barrier, Lock
import traceback

import pytest

from execution.alpaca_paper import (
    AlpacaPaperBoundary, AlpacaPaperBoundaryError, AlpacaPaperPersistenceError,
    LOOKUP_URL, ORDERS_URL, TransportResponse, client_order_id, request_for,
)
from execution.contracts import (
    ExecutionDomain, ExecutionScope, Instrument, OrderAcknowledgement, OrderIntent,
    OrderSide, OrderType, QuantityUnit, RiskMetadata, TimeInForce,
)
from execution.paper_journal import JournalState, PaperJournalError, PaperOrderJournal
from execution.paper_binding import PaperDeploymentBinding

NOW = datetime(2026, 9, 3, 14, tzinfo=timezone.utc)
BROKER_ID = "0ca07231-9205-48f0-9fb5-8e04ae3121be"
OTHER_BROKER_ID = "46fe2aa2-f1f8-4e7e-a88c-9f9da48a737d"
ACCOUNT = "54c41ab9-eab7-4823-a47d-2a0b63b18590"
BINDING = PaperDeploymentBinding(
    account_id=ACCOUNT,
    deployment_id="deployment",
    owner_attestation_reference="owner-attestation:alpaca-boundary-fixture-20260903",
)
CLIENT_ID = "qf1-3b2a6dd09052139aeb0109c066348b56d2e291cf6eec"
UNTRUSTED_MARKER = "untrusted-response-text-must-never-be-recorded"


def intent(**changes):
    base = OrderIntent(
        "intent", ExecutionScope(ExecutionDomain.PAPER, "strategy", "run", "deployment", ACCOUNT, "key"),
        RiskMetadata("policy", "decision", NOW), Instrument("SCHX", "etf", "USD", QuantityUnit.SHARES, True),
        OrderSide.BUY, Decimal("2"), OrderType.LIMIT, TimeInForce.DAY, NOW, Decimal("23.45"),
    )
    return replace(base, **changes)


def order_body(**changes):
    # Representative broker Order JSON, deliberately not made from request_for().
    body = {
        "id": BROKER_ID, "client_order_id": CLIENT_ID,
        "created_at": "2026-09-03T14:00:00.000000Z", "updated_at": "2026-09-03T14:00:00.125000Z",
        "submitted_at": "2026-09-03T14:00:00.000000Z", "filled_at": None, "expired_at": None,
        "canceled_at": None, "failed_at": None, "replaced_at": None, "replaced_by": None, "replaces": None,
        "asset_id": "13b33184-593b-4dcf-a1d1-0fc11f26c2a1", "symbol": "SCHX", "asset_class": "us_equity",
        "notional": None, "qty": "2", "filled_qty": "0", "filled_avg_price": None,
        "order_class": "", "order_type": "limit", "type": "limit", "side": "buy", "time_in_force": "day",
        "limit_price": "23.45", "stop_price": None, "status": "new", "extended_hours": False,
        "legs": None, "trail_percent": None, "trail_price": None, "hwm": None,
    }
    body.update(changes)
    return body


class FakeTransport:
    def __init__(self, response=None, *, post_hook=None, get_hook=None):
        self.response = response if response is not None else TransportResponse(200, order_body())
        self.post_hook, self.get_hook = post_hook, get_hook
        self.calls = []
        self.lock = Lock()

    def post(self, url, body):
        with self.lock:
            self.calls.append(("POST", url, dict(body)))
        return self.post_hook(url, body) if self.post_hook else self.response

    def get(self, url):
        with self.lock:
            self.calls.append(("GET", url, None))
        return self.get_hook(url) if self.get_hook else self.response


def journal(tmp_path):
    return PaperOrderJournal(tmp_path / "paper.sqlite3", binding=BINDING)


def boundary(store, transport):
    return AlpacaPaperBoundary(store, transport, binding=BINDING)


def counts(store):
    return tuple(store.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                 for table in ("paper_order_records", "paper_order_events"))


def claimed(store):
    store.enqueue(intent())
    store.claim_submission("intent")


def timeout(*_):
    raise TimeoutError(UNTRUSTED_MARKER)


def test_request_uses_actual_order_creation_fields_and_exact_strings():
    assert request_for(intent()) == {
        "symbol": "SCHX", "side": "buy", "qty": "2", "type": "limit", "time_in_force": "day",
        "order_class": "simple", "client_order_id": CLIENT_ID, "extended_hours": False, "limit_price": "23.45",
    }
    market = intent(order_type=OrderType.MARKET, limit_price=None)
    assert "limit_price" not in request_for(market)
    assert "asset_class" not in request_for(market)
    assert request_for(market)["type"] == "market"


def test_client_order_id_has_a_pinned_unambiguous_scope_mapping():
    item = intent()
    assert client_order_id(item) == CLIENT_ID
    assert len(CLIENT_ID) == 48
    left = intent(scope=replace(item.scope, strategy_id="a|b", run_id="c"))
    right = intent(scope=replace(item.scope, strategy_id="a", run_id="b|c"))
    assert client_order_id(left) != client_order_id(right)
    identities = {client_order_id(intent(scope=replace(item.scope, **{field: "other"})))
                  for field in ("strategy_id", "run_id", "deployment_id", "account_id", "idempotency_key")}
    assert len(identities) == 5 and CLIENT_ID not in identities
    assert client_order_id(intent(quantity=Decimal("2.000"), limit_price=Decimal("23.4500"))) == CLIENT_ID


@pytest.mark.parametrize("price,expected", [("23.450000", "23.45"), ("1.00", "1"), ("0.9999000", "0.9999"), ("0.0001", "0.0001"), ("1234567890123456789012345678.12", "1234567890123456789012345678.12")])
def test_exact_decimal_mapping_and_ticks_ignore_low_arithmetic_precision(price, expected):
    with localcontext() as context:
        context.prec = 2
        assert request_for(intent(limit_price=Decimal(price)))["limit_price"] == expected
        assert request_for(intent(quantity=Decimal("123456789012345678901234567890")))["qty"] == "123456789012345678901234567890"


@pytest.mark.parametrize("change", [
    {"scope": replace(intent().scope, execution_domain=ExecutionDomain.LIVE)},
    {"scope": replace(intent().scope, account_id="other")},
    {"scope": replace(intent().scope, deployment_id="other")},
    {"instrument": replace(intent().instrument, asset_class="us_equity")},
    {"instrument": replace(intent().instrument, currency="EUR")},
    {"instrument": replace(intent().instrument, whole_unit_only=False)},
    {"instrument": replace(intent().instrument, whole_unit_only=False), "quantity": Decimal("1.5")},
    {"instrument": Instrument("SCHX", "etf", "USD", QuantityUnit.CONTRACTS)},
    {"instrument": replace(intent().instrument, symbol="SCHX ")},
    {"order_type": OrderType.STOP, "limit_price": None, "stop_price": Decimal("23")},
    {"time_in_force": TimeInForce.GOOD_TIL_CANCELLED},
    {"limit_price": Decimal("1.001")}, {"limit_price": Decimal("0.99999")},
    {"quantity": Decimal("1e100000")},
])
def test_unsupported_request_is_rejected_before_enqueue_or_claim(tmp_path, change):
    fake = FakeTransport()
    with journal(tmp_path) as store:
        with pytest.raises(AlpacaPaperBoundaryError):
            boundary(store, fake).submit(intent(**change))
        assert counts(store) == (0, 0)
        assert fake.calls == []


@pytest.mark.parametrize("identity", [
    PaperDeploymentBinding("0ca07231-9205-48f0-9fb5-8e04ae3121be", "deployment", "owner-attestation:other-account-fixture"),
    PaperDeploymentBinding(ACCOUNT, "other", "owner-attestation:other-deployment-fixture"),
    PaperDeploymentBinding(ACCOUNT, "deployment", "owner-attestation:other-attestation-fixture"),
])
def test_explicit_constructor_identity_must_match_journal(tmp_path, identity):
    with journal(tmp_path) as store:
        with pytest.raises(AlpacaPaperBoundaryError):
            AlpacaPaperBoundary(store, FakeTransport(), binding=identity)
        assert counts(store) == (0, 0)


def test_claim_is_committed_and_readable_from_another_connection_before_post(tmp_path):
    def observe_claim(url, body):
        assert url == "https://paper-api.alpaca.markets/v2/orders"
        with journal(tmp_path) as other:
            entry = other.get("intent")
            assert entry.state is JournalState.SUBMISSION_PENDING
            assert counts(other) == (1, 2)
            assert other.claim_submission("intent") is None
        return TransportResponse(201, order_body())
    fake = FakeTransport(post_hook=observe_claim)
    with journal(tmp_path) as store:
        result = boundary(store, fake).submit(intent())
        assert result.state is JournalState.ACKNOWLEDGED
        assert result.broker_order_id == BROKER_ID
        assert result.acknowledgement.acknowledged_at == NOW
        assert counts(store) == (1, 3)
    assert len(fake.calls) == 1


@pytest.mark.parametrize("order_type", [OrderType.MARKET, OrderType.LIMIT])
@pytest.mark.parametrize("status", ["accepted", "new"])
def test_successful_supported_receipts(order_type, status, tmp_path):
    item = intent(order_type=order_type, limit_price=None if order_type is OrderType.MARKET else Decimal("23.45"))
    fake = FakeTransport(TransportResponse(200, order_body(type=order_type.value, order_type=order_type.value, limit_price=None if order_type is OrderType.MARKET else "23.4500", qty="2.0", status=status)))
    with journal(tmp_path) as store:
        assert boundary(store, fake).submit(item).state is JournalState.ACKNOWLEDGED


@pytest.mark.parametrize("http_status", [0, 199, 300, 301, 400, 401, 403, 404, 409, 422, 429, 500, 503, True, 200.0, "200", None])
def test_non_success_or_non_integer_transport_status_is_unknown_without_retry(tmp_path, http_status):
    fake = FakeTransport(TransportResponse(http_status, order_body()))
    with journal(tmp_path) as store:
        adapter = boundary(store, fake)
        assert adapter.submit(intent()).state is JournalState.SUBMISSION_UNKNOWN
        assert adapter.submit(intent()).state is JournalState.SUBMISSION_UNKNOWN
        assert counts(store) == (1, 3)
    assert len(fake.calls) == 1


@pytest.mark.parametrize("body", [None, [], "not json", 123, {}, {"message": UNTRUSTED_MARKER}])
def test_malformed_body_is_unknown(tmp_path, body):
    with journal(tmp_path) as store:
        fake = FakeTransport(TransportResponse(200, body))
        assert boundary(store, fake).submit(intent()).state is JournalState.SUBMISSION_UNKNOWN
        assert len(fake.calls) == 1


@pytest.mark.parametrize("field,value", [
    ("client_order_id", "wrong"), ("symbol", "AAPL"), ("side", "sell"), ("type", "market"),
    ("order_type", "market"), ("time_in_force", "gtc"), ("asset_class", "crypto"), ("order_class", "bracket"),
    ("extended_hours", True), ("extended_hours", 0), ("qty", "3"), ("limit_price", "23.46"),
    ("notional", "46.90"), ("stop_price", "20"), ("trail_price", "1"), ("trail_percent", "1"),
    ("legs", [{"id": OTHER_BROKER_ID}]), ("take_profit", {}), ("stop_loss", {}),
    ("filled_qty", "1"), ("filled_avg_price", "23.45"), ("filled_at", "2026-09-03T14:00:01Z"),
    ("replaced_by", OTHER_BROKER_ID), ("replaces", OTHER_BROKER_ID),
    ("id", UNTRUSTED_MARKER), ("id", BROKER_ID.upper()), ("id", True),
    ("submitted_at", "2026-09-03T14:00:00"), ("submitted_at", "garbage"),
    ("submitted_at", "X" * 65), ("submitted_at", NOW),
])
def test_identity_economics_and_timestamp_mismatches_are_unknown(tmp_path, field, value):
    with journal(tmp_path) as store:
        fake = FakeTransport(TransportResponse(200, order_body(**{field: value})))
        assert boundary(store, fake).submit(intent()).state is JournalState.SUBMISSION_UNKNOWN
        assert store.get("intent").acknowledgement is None


@pytest.mark.parametrize("value", [True, 2, 2.0, Decimal("2"), "NaN", "Infinity", "-2", "2e0", " 2", "", "2" * 65, None])
@pytest.mark.parametrize("field", ["qty", "limit_price"])
def test_broker_numbers_require_bounded_plain_decimal_strings(tmp_path, field, value):
    with journal(tmp_path) as store:
        fake = FakeTransport(TransportResponse(200, order_body(**{field: value})))
        assert boundary(store, fake).submit(intent()).state is JournalState.SUBMISSION_UNKNOWN


@pytest.mark.parametrize("status", ["rejected", "pending_new", "partially_filled", "filled", "canceled", "expired", "done_for_day", "replaced", "unknown", "", None, True])
def test_unhandled_and_terminal_order_states_are_not_fake_receipts(tmp_path, status):
    with journal(tmp_path) as store:
        fake = FakeTransport(TransportResponse(200, order_body(status=status)))
        assert boundary(store, fake).submit(intent()).state is JournalState.SUBMISSION_UNKNOWN


@pytest.mark.parametrize("field", ["id", "client_order_id", "symbol", "asset_class", "qty", "filled_qty", "type", "side", "time_in_force", "order_class", "extended_hours", "limit_price", "status", "submitted_at"])
def test_missing_required_order_fields_are_unknown(tmp_path, field):
    response = order_body()
    del response[field]
    with journal(tmp_path) as store:
        assert boundary(store, FakeTransport(TransportResponse(200, response))).submit(intent()).state is JournalState.SUBMISSION_UNKNOWN


def test_timeout_and_restart_never_resubmit(tmp_path):
    first = FakeTransport(post_hook=timeout)
    with journal(tmp_path) as store:
        assert boundary(store, first).submit(intent()).state is JournalState.SUBMISSION_UNKNOWN
    replacement = FakeTransport()
    with journal(tmp_path) as store:
        assert boundary(store, replacement).submit(intent()).state is JournalState.SUBMISSION_UNKNOWN
    assert len(first.calls) == 1 and replacement.calls == []


def test_pending_claim_after_process_interruption_never_resubmits(tmp_path):
    with journal(tmp_path) as store:
        claimed(store)
    fake = FakeTransport()
    with journal(tmp_path) as store:
        assert boundary(store, fake).submit(intent()).state is JournalState.SUBMISSION_PENDING
    assert fake.calls == []


def test_concurrent_submitters_allow_only_one_post(tmp_path):
    start = Barrier(2)
    fake = FakeTransport()
    def submit(_):
        with journal(tmp_path) as store:
            start.wait(timeout=10)
            return boundary(store, fake).submit(intent()).state
    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(pool.map(submit, range(2)))
    assert all(state in {JournalState.SUBMISSION_PENDING, JournalState.ACKNOWLEDGED} for state in states)
    assert [call[0] for call in fake.calls] == ["POST"]
    with journal(tmp_path) as store:
        assert store.get("intent").state is JournalState.ACKNOWLEDGED


def test_losing_claim_returns_fresh_state_instead_of_earlier_queued_entry(tmp_path, monkeypatch):
    fake = FakeTransport()
    with journal(tmp_path) as store:
        original = store.claim_submission
        def other_submits_first(intent_id):
            with journal(tmp_path) as other:
                assert boundary(other, FakeTransport()).submit(intent()).state is JournalState.ACKNOWLEDGED
            return original(intent_id)
        monkeypatch.setattr(store, "claim_submission", other_submits_first)
        assert boundary(store, fake).submit(intent()).state is JournalState.ACKNOWLEDGED
    assert fake.calls == []


@pytest.mark.parametrize("initial_state", ["missing", "queued"])
def test_recovery_cannot_create_or_claim_an_intent(tmp_path, initial_state):
    fake = FakeTransport()
    with journal(tmp_path) as store:
        if initial_state == "queued":
            store.enqueue(intent())
        before = counts(store)
        with pytest.raises(AlpacaPaperBoundaryError, match="existing submission claim"):
            boundary(store, fake).recover("intent")
        assert counts(store) == before
        assert fake.calls == []


@pytest.mark.parametrize("status,body", [(404, {}), (500, {}), (200, {}), (200, order_body(client_order_id="wrong"))])
def test_inconclusive_recovery_stays_unknown_without_requeue(tmp_path, status, body):
    fake = FakeTransport(TransportResponse(status, body))
    with journal(tmp_path) as store:
        claimed(store)
        adapter = boundary(store, fake)
        assert adapter.recover("intent").state is JournalState.SUBMISSION_UNKNOWN
        assert adapter.recover("intent").state is JournalState.SUBMISSION_UNKNOWN
        assert adapter.submit(intent()).state is JournalState.SUBMISSION_UNKNOWN
        assert counts(store) == (1, 3)
    assert [call[0] for call in fake.calls] == ["GET", "GET"]
    assert all(call[1] == LOOKUP_URL + "?client_order_id=" + CLIENT_ID for call in fake.calls)


def test_successful_recovery_and_repeated_lookup_retain_stable_receipt(tmp_path):
    fake = FakeTransport(TransportResponse(200, order_body(submitted_at="2026-09-03T10:00:00-04:00")))
    with journal(tmp_path) as store:
        claimed(store)
        first = boundary(store, fake).recover("intent")
        assert first.state is JournalState.ACKNOWLEDGED
        assert first.acknowledgement.acknowledged_at == NOW
        assert first.acknowledgement.acknowledgement_id == "alpaca-paper-v1:" + BROKER_ID
    with journal(tmp_path) as store:
        assert boundary(store, fake).recover("intent") == first
        assert boundary(store, fake).submit(intent()) == first
    assert len(fake.calls) == 1 and fake.calls[0][0] == "GET"


def test_two_concurrent_recoveries_persist_one_identical_receipt(tmp_path):
    with journal(tmp_path) as store:
        claimed(store)
    both_looked_up = Barrier(2)
    def lookup(_):
        both_looked_up.wait(timeout=10)
        return TransportResponse(200, order_body())
    fake = FakeTransport(get_hook=lookup)
    def recover(_):
        with journal(tmp_path) as store:
            return boundary(store, fake).recover("intent")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(recover, range(2)))
    assert results[0] == results[1]
    with journal(tmp_path) as store:
        assert counts(store) == (1, 3)
    assert [call[0] for call in fake.calls] == ["GET", "GET"]


@pytest.mark.parametrize("different", [{"id": OTHER_BROKER_ID}, {"submitted_at": "2026-09-03T14:00:01Z"}])
def test_concurrent_conflicting_recovery_preserves_first_receipt_and_reports_failure(tmp_path, different):
    with journal(tmp_path) as store:
        claimed(store)
    both_looked_up = Barrier(2)
    def recover(number):
        def lookup(_):
            both_looked_up.wait(timeout=10)
            return TransportResponse(200, order_body(**(different if number else {})))
        with journal(tmp_path) as store:
            try:
                return boundary(store, FakeTransport(get_hook=lookup)).recover("intent")
            except AlpacaPaperPersistenceError as error:
                return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(recover, range(2)))
    failures = [result for result in results if isinstance(result, AlpacaPaperPersistenceError)]
    successes = [result for result in results if not isinstance(result, Exception)]
    assert len(failures) == len(successes) == 1
    assert "conflicts" in str(failures[0])
    with journal(tmp_path) as store:
        assert store.get("intent") == successes[0]
        assert counts(store) == (1, 3)


def test_recovery_acknowledgement_wins_over_submit_timeout(tmp_path):
    recovery = FakeTransport()
    def submit_then_timeout(*_):
        with journal(tmp_path) as other:
            boundary(other, recovery).recover("intent")
        raise TimeoutError(UNTRUSTED_MARKER)
    fake = FakeTransport(post_hook=submit_then_timeout)
    with journal(tmp_path) as store:
        assert boundary(store, fake).submit(intent()).state is JournalState.ACKNOWLEDGED
    assert len(fake.calls) == len(recovery.calls) == 1


def test_acknowledgement_between_unknown_read_and_write_is_preserved(tmp_path, monkeypatch):
    with journal(tmp_path) as store:
        original = store.mark_submission_unknown
        def recover_before_unknown_write(intent_id):
            with journal(tmp_path) as other:
                boundary(other, FakeTransport()).recover(intent_id)
            return original(intent_id)
        monkeypatch.setattr(store, "mark_submission_unknown", recover_before_unknown_write)
        fake = FakeTransport(post_hook=timeout)
        assert boundary(store, fake).submit(intent()).state is JournalState.ACKNOWLEDGED
        assert counts(store) == (1, 3)


@pytest.mark.parametrize("stage", ["queued", "submission_pending"])
def test_durable_claim_failure_prevents_post(tmp_path, stage):
    with journal(tmp_path) as store:
        store.connection.execute(f"""CREATE TRIGGER fail_event BEFORE INSERT ON paper_order_events
            WHEN NEW.event_type='{stage}' BEGIN SELECT RAISE(ABORT, 'injected journal write failure'); END""")
        fake = FakeTransport()
        with pytest.raises(AlpacaPaperPersistenceError, match="no POST"):
            boundary(store, fake).submit(intent())
        assert fake.calls == []
        assert counts(store) == ((0, 0) if stage == "queued" else (1, 1))


@pytest.mark.parametrize("stage", ["acknowledged", "submission_unknown"])
def test_post_outcome_persistence_failure_is_explicit_and_never_reposts(tmp_path, stage):
    fake = FakeTransport(post_hook=timeout if stage == "submission_unknown" else None)
    with journal(tmp_path) as store:
        store.connection.execute(f"""CREATE TRIGGER fail_event BEFORE INSERT ON paper_order_events
            WHEN NEW.event_type='{stage}' BEGIN SELECT RAISE(ABORT, 'injected journal write failure'); END""")
        with pytest.raises(AlpacaPaperPersistenceError, match="do not resubmit"):
            boundary(store, fake).submit(intent())
        assert store.get("intent").state is JournalState.SUBMISSION_PENDING
        assert counts(store) == (1, 2)
        store.connection.execute("DROP TRIGGER fail_event")
    with journal(tmp_path) as store:
        assert boundary(store, fake).submit(intent()).state is JournalState.SUBMISSION_PENDING
    assert len(fake.calls) == 1


def test_conflicting_broker_binding_is_explicit_failure_not_fake_ack(tmp_path):
    second = intent(intent_id="second", scope=replace(intent().scope, idempotency_key="second-key"))
    with journal(tmp_path) as store:
        boundary(store, FakeTransport()).submit(intent())
        fake = FakeTransport(TransportResponse(200, order_body(client_order_id=client_order_id(second))))
        with pytest.raises(AlpacaPaperPersistenceError, match="conflicts"):
            boundary(store, fake).submit(second)
        assert store.get("second").state is JournalState.SUBMISSION_PENDING
        assert store.get("intent").broker_order_id == BROKER_ID


def test_untrusted_errors_and_payloads_never_leak_into_logs_evidence_or_exception_chains(tmp_path, capsys, caplog, monkeypatch):
    fake = FakeTransport(post_hook=timeout)
    with journal(tmp_path) as store:
        def fail_write(_):
            raise sqlite3.OperationalError(UNTRUSTED_MARKER)
        monkeypatch.setattr(store, "mark_submission_unknown", fail_write)
        with pytest.raises(AlpacaPaperPersistenceError) as caught:
            boundary(store, fake).submit(intent())
        assert caught.value.__cause__ is None and caught.value.__context__ is None
        assert UNTRUSTED_MARKER not in "".join(traceback.format_exception(caught.value))
    assert UNTRUSTED_MARKER.encode() not in (tmp_path / "paper.sqlite3").read_bytes()
    assert UNTRUSTED_MARKER not in caplog.text + capsys.readouterr().out
    assert UNTRUSTED_MARKER not in repr(TransportResponse(500, {"error": UNTRUSTED_MARKER}))


def test_public_journal_lookup_validates_corruption_without_creating_records(tmp_path):
    with journal(tmp_path) as store:
        assert store.get("missing") is None
        assert counts(store) == (0, 0)
        claimed(store)
        store.connection.execute("UPDATE paper_order_records SET semantic_hash='bad'")
        with pytest.raises(PaperJournalError):
            store.get("intent")
        fake = FakeTransport()
        with pytest.raises(AlpacaPaperPersistenceError, match="could not be read"):
            boundary(store, fake).recover("intent")
        assert fake.calls == []
        assert counts(store) == (1, 2)


def test_boundary_has_no_concrete_network_or_research_dependency():
    import execution.alpaca_paper as module
    tree = ast.parse(Path(module.__file__).read_text())
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not any(name.split(".")[0] in {"requests", "httpx", "socket", "urllib", "alpaca", "dashboard", "research", "market_data", "os"} for name in imports if name)
    assert not hasattr(module, "main")
