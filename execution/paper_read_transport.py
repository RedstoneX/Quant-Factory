"""GET-only paper observations through an explicit restricted OneCLI capability."""
from __future__ import annotations

import base64
from enum import Enum
import json
import math
from pathlib import Path
import re
import ssl
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PAPER_ORIGIN = "https://paper-api.alpaca.markets"
ALLOWED_PATHS = frozenset({"/v2/account", "/v2/positions"})
MAX_RESPONSE_BYTES = 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 8


class ReadFailure(str, Enum):
    CONFIGURATION_INVALID = "configuration_invalid"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    ENDPOINT_DENIED = "endpoint_denied"
    GATEWAY_UNAVAILABLE = "gateway_unavailable"
    GATEWAY_DENIED = "gateway_denied"
    UPSTREAM_STATUS = "upstream_status"
    RESPONSE_INVALID = "response_invalid"
    RESPONSE_OVERSIZED = "response_oversized"


class PaperReadError(RuntimeError):
    """Carries only a fixed reason; never an upstream body or exception message."""

    def __init__(self, reason: ReadFailure, *, http_status: int | None = None) -> None:
        self.reason = reason
        self.http_status = (http_status if type(http_status) is int
                            and 100 <= http_status <= 599 else None)
        super().__init__(reason.value)


def absolute_file(value: object) -> Path:
    if type(value) is not str or not value or not Path(value).is_absolute():
        raise PaperReadError(ReadFailure.CONFIGURATION_INVALID)
    return Path(value)


def validate_proxy_url(value: object) -> str:
    if type(value) is not str:
        raise PaperReadError(ReadFailure.CONFIGURATION_INVALID)
    valid = False
    try:
        parts = urlsplit(value)
        valid = (parts.scheme == "http" and parts.username is None and parts.password is None
                 and not parts.path and not parts.query and not parts.fragment
                 and parts.port is not None and 1 <= parts.port <= 65535
                 and ((parts.hostname == "gateway-relay" and parts.port == 10255)
                      or parts.hostname == "127.0.0.1")
                 and value == f"http://{parts.hostname}:{parts.port}")
    except (TypeError, ValueError):
        pass
    if not valid:
        raise PaperReadError(ReadFailure.CONFIGURATION_INVALID) from None
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _finite_float(text: str) -> float:
    result = float(text)
    if not math.isfinite(result):
        raise ValueError("nonfinite JSON number")
    return result


def _reject_constant(_):
    raise ValueError("nonfinite JSON number")


def strict_json(raw: bytes, *, limit: int = MAX_RESPONSE_BYTES):
    if len(raw) > limit:
        raise PaperReadError(ReadFailure.RESPONSE_OVERSIZED)
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        pass
    raise PaperReadError(ReadFailure.RESPONSE_INVALID) from None


class _CapabilityAdapter(HTTPAdapter):
    def __init__(self, authorization: str) -> None:
        self._authorization = authorization
        super().__init__(max_retries=Retry(total=0, connect=0, read=0, redirect=0, status=0, other=0))

    def proxy_headers(self, proxy: str) -> dict[str, str]:
        # Requests/urllib3 place this header on CONNECT, never on the upstream GET.
        return {"Proxy-Authorization": self._authorization}

    def __repr__(self) -> str:
        return "<restricted paper proxy adapter>"


class PaperReadTransport:
    """No endpoint override, broker credentials, mutation method or direct fallback."""

    def __init__(self, *, proxy_url: str, identity_file: str, ca_file: str) -> None:
        self._proxy_url = validate_proxy_url(proxy_url)
        identity_path, ca_path = absolute_file(identity_file), absolute_file(ca_file)
        authorization = None
        try:
            with identity_path.open("rb") as source:
                raw = source.read(1027)
            if len(raw) > 1026:
                raise ValueError("oversized capability file")
            token = raw.removesuffix(b"\n").removesuffix(b"\r")
            if not 16 <= len(token) <= 1024 or not re.fullmatch(rb"[!-~]+", token):
                raise ValueError("invalid capability")
            ssl.create_default_context(cafile=str(ca_path))
            authorization = "Basic " + base64.b64encode(b"qf:" + token).decode("ascii")
        except Exception:
            pass
        if authorization is None:
            raise PaperReadError(ReadFailure.CAPABILITY_UNAVAILABLE) from None
        self._ca_file = str(ca_path)
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.adapters.clear()
        self._session.mount(PAPER_ORIGIN + "/", _CapabilityAdapter(authorization))
        self._session.proxies = {"https": self._proxy_url}

    def __repr__(self) -> str:
        return "<read-only paper account transport>"

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def get(self, path: str):
        if type(path) is not str or path not in ALLOWED_PATHS:
            raise PaperReadError(ReadFailure.ENDPOINT_DENIED)
        failure = ReadFailure.GATEWAY_UNAVAILABLE
        http_status = None
        try:
            with self._session.get(
                PAPER_ORIGIN + path, proxies={"https": self._proxy_url},
                verify=self._ca_file, timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                allow_redirects=False, stream=True,
                headers={"Accept": "application/json", "Accept-Encoding": "identity", "Cache-Control": "no-cache"},
            ) as response:
                http_status = response.status_code
                if response.status_code in {401, 403, 407}:
                    raise PaperReadError(ReadFailure.GATEWAY_DENIED)
                if response.status_code != 200:
                    raise PaperReadError(ReadFailure.UPSTREAM_STATUS)
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise PaperReadError(ReadFailure.RESPONSE_INVALID)
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise PaperReadError(ReadFailure.RESPONSE_INVALID)
                length = response.headers.get("Content-Length")
                if length is not None:
                    if not re.fullmatch(r"[0-9]{1,9}", length):
                        raise PaperReadError(ReadFailure.RESPONSE_INVALID)
                    if int(length) > MAX_RESPONSE_BYTES:
                        raise PaperReadError(ReadFailure.RESPONSE_OVERSIZED)
                payload = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    if len(payload) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise PaperReadError(ReadFailure.RESPONSE_OVERSIZED)
                    payload.extend(chunk)
                return strict_json(bytes(payload))
        except PaperReadError as error:
            failure = error.reason
        except Exception:
            pass
        finally:
            self._session.cookies.clear()
        raise PaperReadError(failure, http_status=http_status) from None
