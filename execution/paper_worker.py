"""Independently runnable, read-only paper account observer and private health API."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import signal
from threading import Event, Lock, Thread
from typing import Callable
from uuid import UUID

from execution.paper_read_transport import (
    PaperReadError, PaperReadTransport, ReadFailure, absolute_file, strict_json, validate_proxy_url,
)
from execution.paper_binding import PaperDeploymentBinding


class ObservationFailure(str, Enum):
    NOT_OBSERVED = "not_observed"
    ACCOUNT_INVALID = "account_invalid"
    ACCOUNT_MISMATCH = "account_mismatch"
    ACCOUNT_INACTIVE = "account_inactive"
    ACCOUNT_BLOCKED = "account_blocked"
    POSITIONS_INVALID = "positions_invalid"
    STALE = "observation_stale"
    STOPPED = "observer_stopped"
    INTERNAL = "observation_failed"


class ObservationError(RuntimeError):
    def __init__(self, reason: ObservationFailure) -> None:
        self.reason = reason
        super().__init__(reason.value)


def _uuid(value: object) -> str:
    if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
        raise ValueError("invalid identity")
    return value


def _number(value: object) -> Decimal:
    if type(value) is not str or len(value) > 64 or not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value, re.ASCII):
        raise ValueError("invalid numeric field")
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError("invalid numeric field")
    return parsed


@dataclass(frozen=True)
class WorkerConfig:
    expected_account_id: str = field(repr=False)
    deployment_id: str
    owner_attestation_reference: str = field(repr=False)
    proxy_url: str
    identity_file: str = field(repr=False)
    ca_file: str = field(repr=False)
    refresh_seconds: int = 60

    def __post_init__(self) -> None:
        valid = False
        try:
            PaperDeploymentBinding(
                account_id=self.expected_account_id,
                deployment_id=self.deployment_id,
                owner_attestation_reference=self.owner_attestation_reference,
            )
            valid = type(self.refresh_seconds) is int and 30 <= self.refresh_seconds <= 300
            validate_proxy_url(self.proxy_url)
            absolute_file(self.identity_file)
            absolute_file(self.ca_file)
        except Exception:
            valid = False
        if not valid:
            raise PaperReadError(ReadFailure.CONFIGURATION_INVALID) from None

    @property
    def binding(self) -> PaperDeploymentBinding:
        """Return the configured external-attestation reference without verifying it."""
        return PaperDeploymentBinding(
            account_id=self.expected_account_id,
            deployment_id=self.deployment_id,
            owner_attestation_reference=self.owner_attestation_reference,
        )

    @classmethod
    def load(cls, path: str) -> "WorkerConfig":
        try:
            with absolute_file(path).open("rb") as source:
                value = strict_json(source.read(16385), limit=16384)
            expected = {"expected_account_id", "deployment_id", "owner_attestation_reference", "proxy_url", "identity_file", "ca_file", "refresh_seconds"}
            if type(value) is not dict or set(value) != expected:
                raise ValueError("invalid configuration keys")
            return cls(**value)
        except Exception:
            pass
        raise PaperReadError(ReadFailure.CONFIGURATION_INVALID) from None


@dataclass(frozen=True, repr=False)
class AccountObservation:
    account_id: str
    cash: Decimal
    equity: Decimal
    buying_power: Decimal

    def __repr__(self) -> str:
        return "<verified paper account observation>"


def validate_account(value: object, expected_account_id: str) -> AccountObservation:
    reason = ObservationFailure.ACCOUNT_INVALID
    try:
        if type(value) is not dict:
            raise ValueError("invalid account shape")
        actual_id = _uuid(value.get("id"))
        if actual_id != expected_account_id:
            raise ObservationError(ObservationFailure.ACCOUNT_MISMATCH)
        if value.get("status") != "ACTIVE":
            raise ObservationError(ObservationFailure.ACCOUNT_INACTIVE)
        if value.get("currency") != "USD":
            raise ValueError("unsupported account currency")
        for flag in ("trading_blocked", "account_blocked", "trade_suspended_by_user"):
            if type(value.get(flag)) is not bool:
                raise ValueError("missing account restriction flag")
            if value[flag]:
                raise ObservationError(ObservationFailure.ACCOUNT_BLOCKED)
        # This concerns transfers, not order permission. It does not gate reads.
        if "transfers_blocked" in value and type(value["transfers_blocked"]) is not bool:
            raise ValueError("invalid transfer flag")
        return AccountObservation(actual_id, _number(value.get("cash")), _number(value.get("equity")), _number(value.get("buying_power")))
    except ObservationError as error:
        reason = error.reason
    except Exception:
        pass
    raise ObservationError(reason) from None


def validate_positions(value: object) -> int:
    valid = False
    try:
        if type(value) is not list or len(value) > 10000:
            raise ValueError("invalid positions shape")
        asset_ids, symbols = set(), set()
        for position in value:
            if type(position) is not dict:
                raise ValueError("invalid position shape")
            asset_id = _uuid(position.get("asset_id"))
            symbol = position.get("symbol")
            if (type(symbol) is not str or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,31}", symbol, re.ASCII)
                    or asset_id in asset_ids or symbol in symbols or position.get("asset_class") != "us_equity"
                    or position.get("side") not in {"long", "short"}):
                raise ValueError("ambiguous equity position identity")
            asset_ids.add(asset_id)
            symbols.add(symbol)
            if _number(position.get("qty")) == 0 or _number(position.get("avg_entry_price")) <= 0:
                raise ValueError("invalid open position quantity or price")
            _number(position.get("cost_basis"))
            for name in ("market_value", "unrealized_pl", "unrealized_plpc", "unrealized_intraday_pl", "unrealized_intraday_plpc", "change_today", "qty_available"):
                if position.get(name) is not None:
                    _number(position[name])
            for name in ("current_price", "lastday_price"):
                if position.get(name) is not None and _number(position[name]) <= 0:
                    raise ValueError("invalid observed price")
        valid = True
    except Exception:
        pass
    if not valid:
        raise ObservationError(ObservationFailure.POSITIONS_INVALID) from None
    return len(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _health(*, ready=False, gateway_status="unverified", observed_at=None, position_count=None,
            blocked_reason="not_observed", attestation_status="not_configured") -> dict[str, object]:
    return {
        "ready": ready, "account_verified": ready, "gateway_status": gateway_status,
        "observed_at": observed_at, "position_count": position_count,
        "blocked_reason": blocked_reason, "order_submission_enabled": False,
        "deployment_ready": False,
        "account_authorization_status": attestation_status,
    }


class PaperObserver:
    def __init__(self, config: WorkerConfig, transport: PaperReadTransport, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self.config, self._transport, self._clock = config, transport, clock
        self._lock = Lock()
        self._observed_at: datetime | None = None
        self._state = _health(attestation_status="external_attestation_reference_unverified")

    def refresh(self) -> dict[str, object]:
        gateway_status = "unverified"
        reason: str | None = ObservationFailure.INTERNAL.value
        count = None
        observed_at = None
        try:
            observed_at = self._clock()
            if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError("invalid observation clock")
            observed_at = observed_at.astimezone(timezone.utc)
            account = self._transport.get("/v2/account")
            gateway_status = "reachable"
            validate_account(account, self.config.expected_account_id)
            positions = self._transport.get("/v2/positions")
            count = validate_positions(positions)
            reason = None
        except PaperReadError as error:
            reason = error.reason.value
            gateway_status = "denied" if error.reason is ReadFailure.GATEWAY_DENIED else "unavailable"
        except ObservationError as error:
            reason = error.reason.value
        except Exception:
            pass
        with self._lock:
            if reason is None:
                self._observed_at = observed_at
            self._state = _health(
                ready=reason is None, gateway_status=gateway_status,
                observed_at=None if self._observed_at is None else self._observed_at.isoformat().replace("+00:00", "Z"),
                position_count=count if reason is None else None, blocked_reason=reason,
                attestation_status="external_attestation_reference_unverified",
            )
        return self.health()

    def health(self) -> dict[str, object]:
        with self._lock:
            state = dict(self._state)
            if state["ready"]:
                try:
                    elapsed = (self._clock() - self._observed_at).total_seconds()
                    fresh = 0 <= elapsed <= 2 * self.config.refresh_seconds
                except Exception:
                    fresh = False
                if not fresh:
                    state.update(ready=False, account_verified=False, position_count=None, blocked_reason=ObservationFailure.STALE.value)
            return state

    def stop(self) -> None:
        with self._lock:
            self._state.update(ready=False, account_verified=False, position_count=None, blocked_reason=ObservationFailure.STOPPED.value)


def health_server(observer: PaperObserver, bind: str, port: int) -> HTTPServer:
    if bind not in {"127.0.0.1", "0.0.0.0"} or type(port) is not int or not 0 <= port <= 65535:
        raise PaperReadError(ReadFailure.CONFIGURATION_INVALID)

    class Handler(BaseHTTPRequestHandler):
        server_version = "QuantFactoryPaperObserver"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def log_message(self, *_):
            pass

        def _send(self, status, body):
            encoded = json.dumps(body, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(encoded)
            self.close_connection = True

        def send_error(self, code, message=None, explain=None):
            self._send(code, {"error": "request_rejected"})

        def do_GET(self):
            if self.path != "/healthz":
                self._send(404, {"error": "not_found"})
                return
            state = observer.health()
            self._send(200 if state["ready"] else 503, state)

        def do_POST(self):
            self._send(405, {"error": "read_only_health"})

        do_DELETE = do_PATCH = do_PUT = do_POST

    class QuietServer(HTTPServer):
        def handle_error(self, *_):
            pass

    return QuietServer((bind, port), Handler)


def serve(observer: PaperObserver, stop: Event, *, bind: str = "127.0.0.1", port: int = 8051) -> None:
    server = health_server(observer, bind, port)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    thread.start()
    try:
        while not stop.is_set():
            observer.refresh()
            if stop.wait(observer.config.refresh_seconds):
                break
    finally:
        observer.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def check_health(port: int) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", "/healthz")
        response = connection.getresponse()
        body = strict_json(response.read(4097), limit=4096)
        return 0 if response.status == 200 and type(body) is dict and body.get("ready") is True and body.get("order_submission_enabled") is False else 1
    except Exception:
        return 1
    finally:
        connection.close()


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "paper observer arguments invalid\n")


def main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(description="Read-only paper account observations; order submission is disabled.")
    parser.add_argument("mode", choices=("observe", "serve", "healthcheck"))
    parser.add_argument("--config")
    parser.add_argument("--health-bind", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=8051)
    args = parser.parse_args(argv)
    if not 1 <= args.health_port <= 65535:
        return 2
    if args.mode == "healthcheck":
        return check_health(args.health_port)
    transport = None
    reason = ReadFailure.CONFIGURATION_INVALID.value
    try:
        config = WorkerConfig.load(args.config)
        transport = PaperReadTransport(proxy_url=config.proxy_url, identity_file=config.identity_file, ca_file=config.ca_file)
        observer = PaperObserver(config, transport)
        if args.mode == "observe":
            state = observer.refresh()
            print(json.dumps(state, sort_keys=True, allow_nan=False))
            return 0 if state["ready"] else 1
        stop = Event()
        previous = {}
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda *_: stop.set())
        try:
            serve(observer, stop, bind=args.health_bind, port=args.health_port)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        return 0
    except PaperReadError as error:
        reason = error.reason.value
    except Exception:
        reason = ObservationFailure.INTERNAL.value
    finally:
        if transport is not None:
            transport.close()
    print(json.dumps(_health(blocked_reason=reason), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
