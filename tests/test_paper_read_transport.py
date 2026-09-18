import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import ssl
import subprocess
from threading import Thread
import traceback

import pytest
import requests

from execution.paper_read_transport import (
    MAX_RESPONSE_BYTES, PaperReadError, PaperReadTransport, ReadFailure,
    strict_json, validate_proxy_url,
)

CAPABILITY = "fixture-only-restricted-capability-0123456789"
UNTRUSTED = "untrusted-upstream-payload-must-not-leak"


@pytest.fixture(scope="module")
def certificate(tmp_path_factory):
    root = tmp_path_factory.mktemp("paper-observer-test-ca")
    certificate, key = root / "ca.pem", root / "test.key"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=paper-api.alpaca.markets",
        "-addext", "subjectAltName=DNS:paper-api.alpaca.markets",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    return certificate, context


@contextmanager
def proxy_fixture(certificate, *, status=200, payload=b'{"ok":true}', connect_status=200, headers=None):
    observed = {"connect": [], "requests": []}
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            observed["requests"].append((self.command, self.path, dict(self.headers)))
            self.send_response(status)
            for name, value in ({"Content-Type": "application/json", "Content-Length": str(len(payload)), "Connection": "close"} | (headers or {})).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_CONNECT(self):
            observed["connect"].append((self.path, self.headers.get("Proxy-Authorization")))
            self.send_response(connect_status)
            self.end_headers()
            self.close_connection = True
            if connect_status == 200:
                with certificate[1].wrap_socket(self.connection, server_side=True) as secured:
                    Upstream(secured, self.client_address, self.server)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    server.daemon_threads = True
    server.handle_error = lambda *_: None
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", observed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def transport(tmp_path, certificate, proxy_url="http://127.0.0.1:10255"):
    identity = tmp_path / "restricted.identity"
    identity.write_text(CAPABILITY + "\n")
    return PaperReadTransport(proxy_url=proxy_url, identity_file=str(identity), ca_file=str(certificate[0]))


def test_real_connect_tls_routes_only_through_proxy_ignores_environment_and_hides_capability(tmp_path, certificate, monkeypatch, caplog):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "APCA_API_BASE_URL", "REQUESTS_CA_BUNDLE"):
        monkeypatch.setenv(name, "https://invalid.example/not-used")
    with proxy_fixture(certificate) as (url, observed):
        client = transport(tmp_path, certificate, url)
        with caplog.at_level(logging.DEBUG):
            assert client.get("/v2/account") == {"ok": True}
            assert client.get("/v2/positions") == {"ok": True}
        adapter = client._session.get_adapter("https://paper-api.alpaca.markets/v2/account")
        assert client._session.trust_env is False
        assert adapter.max_retries.total == 0
        assert CAPABILITY not in repr(client) + repr(adapter) + repr(client._session.proxies) + caplog.text
        assert len(observed["connect"]) == 2
        expected = "Basic " + base64.b64encode(("qf:" + CAPABILITY).encode()).decode()
        assert all(authority == "paper-api.alpaca.markets:443" and auth == expected for authority, auth in observed["connect"])
        assert [item[:2] for item in observed["requests"]] == [("GET", "/v2/account"), ("GET", "/v2/positions")]
        for _, _, request_headers in observed["requests"]:
            assert not any(name.lower() in {"proxy-authorization", "authorization", "apca-api-key-id", "apca-api-secret-key"} for name in request_headers)
        client.close()


@pytest.mark.parametrize("connect_status,http_status", [(407, 200), (200, 302), (200, 503)])
def test_real_proxy_denial_redirect_and_upstream_error_have_no_retry_or_direct_fallback(tmp_path, certificate, connect_status, http_status):
    with proxy_fixture(certificate, connect_status=connect_status, status=http_status, payload=UNTRUSTED.encode(), headers={"Location": "https://api.alpaca.markets/v2/account"}) as (url, observed):
        client = transport(tmp_path, certificate, url)
        with pytest.raises(PaperReadError) as caught:
            client.get("/v2/account")
        assert len(observed["connect"]) == 1
        assert len(observed["requests"]) == (0 if connect_status == 407 else 1)
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert UNTRUSTED not in "".join(traceback.format_exception(caught.value))
        assert CAPABILITY not in str(caught.value)
        client.close()


@pytest.mark.parametrize("path", ["/v2/orders", "/v2/account?x=1", "/v2/positions/ABC", "https://api.alpaca.markets/v2/account", "/v2/../v2/account"])
def test_endpoint_allowlist_rejects_before_network(tmp_path, certificate, monkeypatch, path):
    client = transport(tmp_path, certificate)
    monkeypatch.setattr(client._session, "get", lambda *_args, **_kwargs: pytest.fail("forbidden network call"))
    with pytest.raises(PaperReadError) as caught:
        client.get(path)
    assert caught.value.reason is ReadFailure.ENDPOINT_DENIED
    assert not any(hasattr(client, method) for method in ("post", "delete", "patch", "put"))
    client.close()


@pytest.mark.parametrize("url", [
    "".join(("http", "://", "qf", ":", "token", "@", "gateway-relay", ":10255")),
    "https://gateway-relay:10255", "http://gateway-relay:8080",
    "http://gateway-relay:10255/", "http://gateway-relay:10255?x=1", "http://gateway-relay:10255#x",
    "http://example.com:10255", "http://169.254.169.254:80", "http://127.0.0.1:0", "http://127.0.0.1:65536", None,
])
def test_proxy_configuration_rejects_credentials_overrides_and_unapproved_hosts(url):
    with pytest.raises(PaperReadError) as caught:
        validate_proxy_url(url)
    assert caught.value.reason is ReadFailure.CONFIGURATION_INVALID
    assert "token" not in str(caught.value)


class FakeResponse:
    status_code = 200
    def __init__(self, chunks, headers=None):
        self.chunks = chunks
        self.headers = {"Content-Type": "application/json"} | (headers or {})
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def iter_content(self, chunk_size):
        yield from self.chunks


@pytest.mark.parametrize("response,reason", [
    (FakeResponse([b"{"], {"Content-Length": str(MAX_RESPONSE_BYTES + 1)}), ReadFailure.RESPONSE_OVERSIZED),
    (FakeResponse([b"x" * MAX_RESPONSE_BYTES, b"x"]), ReadFailure.RESPONSE_OVERSIZED),
    (FakeResponse([b"{}"], {"Content-Encoding": "gzip"}), ReadFailure.RESPONSE_INVALID),
    (FakeResponse([b"{}"], {"Content-Type": "text/html"}), ReadFailure.RESPONSE_INVALID),
    (FakeResponse([b"{}"], {"Content-Length": "invalid"}), ReadFailure.RESPONSE_INVALID),
    (FakeResponse([b'{"a":1,"a":2}']), ReadFailure.RESPONSE_INVALID),
    (FakeResponse([b'{"a":{"b":1,"b":2}}']), ReadFailure.RESPONSE_INVALID),
    (FakeResponse([b'{"a":NaN}']), ReadFailure.RESPONSE_INVALID),
    (FakeResponse([b'{"a":1e9999}']), ReadFailure.RESPONSE_INVALID),
    (FakeResponse([b"\xff"]), ReadFailure.RESPONSE_INVALID),
])
def test_response_bounds_and_strict_json_fail_closed(tmp_path, certificate, monkeypatch, response, reason):
    client = transport(tmp_path, certificate)
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr(client._session, "get", get)
    with pytest.raises(PaperReadError) as caught:
        client.get("/v2/account")
    assert caught.value.reason is reason
    assert len(calls) == 1
    assert calls[0][1]["timeout"] == (3, 8)
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["verify"] == str(certificate[0])
    assert calls[0][1]["proxies"] == {"https": "http://127.0.0.1:10255"}
    client.close()


def test_transport_exception_is_sanitized_without_chain(tmp_path, certificate, monkeypatch):
    client = transport(tmp_path, certificate)
    def fail(*_args, **_kwargs):
        raise requests.ReadTimeout(CAPABILITY + UNTRUSTED)
    monkeypatch.setattr(client._session, "get", fail)
    with pytest.raises(PaperReadError) as caught:
        client.get("/v2/account")
    assert caught.value.reason is ReadFailure.GATEWAY_UNAVAILABLE
    assert caught.value.__context__ is None
    assert CAPABILITY not in "".join(traceback.format_exception(caught.value))
    client.close()


@pytest.mark.parametrize("content", [b"short", b"X" * 1024 + b"\nmore-data", b"X" * 1027, b"valid-capability-123\nsecond-line"])
def test_capability_file_is_bounded_and_cannot_ignore_trailing_content(tmp_path, certificate, content):
    identity = tmp_path / "identity"
    identity.write_bytes(content)
    with pytest.raises(PaperReadError) as caught:
        PaperReadTransport(proxy_url="http://gateway-relay:10255", identity_file=str(identity), ca_file=str(certificate[0]))
    assert caught.value.reason is ReadFailure.CAPABILITY_UNAVAILABLE
    assert caught.value.__context__ is None


def test_explicit_absolute_identity_and_ca_are_required(tmp_path, certificate):
    with pytest.raises(PaperReadError):
        PaperReadTransport(proxy_url="http://gateway-relay:10255", identity_file="relative", ca_file=str(certificate[0]))
    identity = tmp_path / "identity"
    identity.write_text(CAPABILITY)
    with pytest.raises(PaperReadError):
        PaperReadTransport(proxy_url="http://gateway-relay:10255", identity_file=str(identity), ca_file=str(tmp_path / "missing-ca.pem"))
