from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import ast
from pathlib import Path

import pytest

from execution.alpaca_snapshots import AlpacaSnapshotError, normalize_snapshots
from execution.contracts import AccountSnapshot, ExecutionDomain, Instrument, PositionSnapshot, QuantityUnit
from execution.paper_binding import PaperDeploymentBinding
from execution.reconciliation import reconcile_snapshots


ACCOUNT = "54c41ab9-eab7-4823-a47d-2a0b63b18590"
ASSET = "13b33184-593b-4dcf-a1d1-0fc11f26c2a1"
SECOND_ASSET = "db14c29f-ff4c-4438-9eb5-a4b15e60f831"
NOW = datetime(2026, 9, 3, 14, tzinfo=timezone.utc)
INSTRUMENTS = {"SCHX": Instrument("SCHX", "etf", "USD", QuantityUnit.SHARES, True)}
SECOND_INSTRUMENT = Instrument("MSFT", "equity", "USD", QuantityUnit.SHARES, True)
DUAL_INSTRUMENTS = INSTRUMENTS | {"MSFT": SECOND_INSTRUMENT}
UNTRUSTED = "private-account-value-must-never-appear"
UNSET = object()
BINDING = PaperDeploymentBinding(
    account_id=ACCOUNT,
    deployment_id="snapshot-fixture",
    owner_attestation_reference="owner-attestation:snapshot-fixture-20260903",
)


def account(**changes):
    value = {
        "id": ACCOUNT, "status": "ACTIVE", "currency": "USD", "cash": "10000.125",
        "equity": "10046.905", "buying_power": "20000.25", "trading_blocked": False,
        "account_blocked": False, "trade_suspended_by_user": False,
    }
    value.update(changes)
    return value


def position(**changes):
    value = {
        "asset_id": ASSET, "symbol": "SCHX", "asset_class": "us_equity", "side": "long",
        "qty": "2", "avg_entry_price": "23.45", "current_price": "23.39", "market_value": "46.78",
    }
    value.update(changes)
    return value


def normalize(observed_account=UNSET, observed_positions=UNSET, **changes):
    arguments = {
        "binding": BINDING, "observed_at": NOW, "snapshot_id": "actual",
        "instruments": INSTRUMENTS, "positions_complete": True,
    }
    arguments.update(changes)
    return normalize_snapshots(account() if observed_account is UNSET else observed_account,
                               [position()] if observed_positions is UNSET else observed_positions,
                               **arguments)


def test_empty_and_long_observations_preserve_exact_decimals_and_paper_identity():
    empty_account, empty_positions = normalize(observed_positions=[])
    assert empty_account.execution_domain is ExecutionDomain.PAPER
    assert empty_account.cash == Decimal("10000.125") and empty_account.positions_complete is True
    assert empty_positions == ()

    observed_account, observed_positions = normalize()
    observed = observed_positions[0]
    assert observed.instrument is INSTRUMENTS["SCHX"]
    assert (observed.quantity, observed.average_entry_price, observed.market_price, observed.market_value) == (
        Decimal("2"), Decimal("23.45"), Decimal("23.39"), Decimal("46.78"),
    )
    assert observed_account.account_id == ACCOUNT and observed.captured_at == NOW


def test_short_position_requires_consistent_signed_quantity_and_market_value():
    _, positions = normalize(observed_positions=[position(side="short", qty="-2", market_value="-46.78")])
    assert positions[0].quantity == Decimal("-2") and positions[0].market_value == Decimal("-46.78")

    for changes in ({"qty": "2"}, {"market_value": "46.78"}, {"market_value": "-46.78", "side": "long"}):
        observed = position(side="short", qty="-2", market_value="-46.78")
        observed.update(changes)
        with pytest.raises(AlpacaSnapshotError):
            normalize(observed_positions=[observed])


def test_normalized_snapshot_can_match_an_independent_complete_fixture():
    actual_account, actual_positions = normalize()
    expected_instrument = Instrument("SCHX", "etf", "USD", QuantityUnit.SHARES, True)
    expected_account = AccountSnapshot(
        snapshot_id="expected", execution_domain=ExecutionDomain.PAPER, account_id=ACCOUNT,
        currency="USD", captured_at=NOW, cash=Decimal("10000.125"), equity=Decimal("10046.905"),
        buying_power=Decimal("20000.25"), positions_complete=True,
    )
    expected_positions = (PositionSnapshot(
        snapshot_id="expected", execution_domain=ExecutionDomain.PAPER, account_id=ACCOUNT,
        instrument=expected_instrument, captured_at=NOW, quantity=Decimal("2"),
        average_entry_price=Decimal("23.45"), market_price=Decimal("23.39"), market_value=Decimal("46.78"),
    ),)
    result = reconcile_snapshots(
        expected_account, actual_account, expected_positions, actual_positions,
        maximum_snapshot_age=timedelta(seconds=1), compared_at=NOW,
    )
    assert result.status.value == "matched" and result.reasons == ()
    assert actual_account == AccountSnapshot(
        snapshot_id="actual", execution_domain=ExecutionDomain.PAPER, account_id=ACCOUNT,
        currency="USD", captured_at=NOW, cash=Decimal("10000.125"), equity=Decimal("10046.905"),
        buying_power=Decimal("20000.25"), positions_complete=True,
    )
    assert actual_positions == (PositionSnapshot(
        snapshot_id="actual", execution_domain=ExecutionDomain.PAPER, account_id=ACCOUNT,
        instrument=INSTRUMENTS["SCHX"], captured_at=NOW, quantity=Decimal("2"),
        average_entry_price=Decimal("23.45"), market_price=Decimal("23.39"), market_value=Decimal("46.78"),
    ),)


@pytest.mark.parametrize("observed_account,observed_positions,changes", [
    (account(id="bc10a0bb-f65c-4203-94d1-e330774166fc"), [position()], {}),
    (account(currency="EUR"), [position()], {}),
    (account(status="PAPER_ONLY"), [position()], {}),
    ({key: value for key, value in account().items() if key != "status"}, [position()], {}),
    (account(cash="NaN"), [position()], {}),
    (account(), [position(symbol="UNKNOWN")], {}),
    (account(), [position(qty="1.5")], {}),
    (account(), [position(avg_entry_price=None)], {}),
    (account(), [position(current_price="Infinity")], {}),
    (account(), [position(market_value=None)], {}),
    (account(), None, {}),
    (account(), [], {"positions_complete": False}),
    (account(), [], {"observed_at": datetime(2026, 9, 3, 14)}),
])
def test_unsafe_or_incomplete_observations_fail_closed(observed_account, observed_positions, changes):
    with pytest.raises(AlpacaSnapshotError):
        normalize(observed_account, observed_positions, **changes)


def test_snapshot_binding_rejects_a_different_configured_account_without_leaking_identity():
    different = PaperDeploymentBinding(
        account_id="0ca07231-9205-48f0-9fb5-8e04ae3121be",
        deployment_id="snapshot-fixture",
        owner_attestation_reference="owner-attestation:other-snapshot-fixture",
    )
    with pytest.raises(AlpacaSnapshotError) as caught:
        normalize(binding=different)
    assert ACCOUNT not in str(caught.value) + repr(caught.value)


@pytest.mark.parametrize("field,value", [
    ("trading_blocked", None), ("trading_blocked", "false"), ("trading_blocked", True),
    ("account_blocked", None), ("account_blocked", 0), ("account_blocked", True),
    ("trade_suspended_by_user", None), ("trade_suspended_by_user", "false"), ("trade_suspended_by_user", True),
])
def test_missing_non_boolean_or_true_account_restrictions_fail_closed(field, value):
    observed = account()
    if value is None:
        del observed[field]
    else:
        observed[field] = value
    with pytest.raises(AlpacaSnapshotError):
        normalize(observed)


def test_duplicate_asset_and_duplicate_symbol_are_distinct_fail_closed_cases():
    duplicate_symbol = [position(), position(asset_id=SECOND_ASSET)]
    duplicate_asset = [position(), position(symbol="MSFT", asset_id=ASSET)]
    for observed in (duplicate_symbol, duplicate_asset):
        with pytest.raises(AlpacaSnapshotError):
            normalize(observed_positions=observed, instruments=DUAL_INSTRUMENTS)


def test_registry_must_be_declared_immutable_usd_whole_share_instruments():
    with pytest.raises(AlpacaSnapshotError):
        normalize(instruments={"SCHX": Instrument("SCHX", "etf", "EUR", QuantityUnit.SHARES, True)})
    with pytest.raises(AlpacaSnapshotError):
        normalize(instruments={"SCHX": Instrument("SCHX", "etf", "USD", QuantityUnit.SHARES, False)})
    with pytest.raises(AlpacaSnapshotError):
        normalize(instruments={"WRONG": INSTRUMENTS["SCHX"]})


def test_rejected_payload_never_appears_in_exception_text():
    unsafe = account(cash=UNTRUSTED)
    with pytest.raises(AlpacaSnapshotError) as caught:
        normalize(unsafe)
    assert UNTRUSTED not in str(caught.value) + repr(caught.value)


def test_mapper_is_pure_and_does_not_import_transport_or_network_modules():
    source = Path(__file__).parents[1] / "execution" / "alpaca_snapshots.py"
    tree = ast.parse(source.read_text())
    imported_modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    imported_names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not {"requests", "http", "socket", "urllib"} & imported_names
    assert not {"execution.paper_worker", "execution.paper_read_transport"} & imported_modules


def test_inputs_are_not_mutated():
    observed_account, observed_positions = account(), [position()]
    before_account, before_positions = deepcopy(observed_account), deepcopy(observed_positions)
    normalize(observed_account, observed_positions)
    assert observed_account == before_account and observed_positions == before_positions
