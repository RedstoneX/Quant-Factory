"""Prove the test-only socket guard allows loopback and rejects outbound TCP."""

from __future__ import annotations

import errno
import socket


def _prove_loopback() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=1):
            connection, _ = listener.accept()
            connection.close()


def _prove_outbound_blocked(family: socket.AddressFamily, address: tuple) -> None:
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        try:
            connection.connect(address)
        except OSError as error:
            if error.errno == errno.EPERM:
                return
            raise RuntimeError(
                f"socket guard returned unexpected errno {error.errno} for {address}"
            ) from error
    raise RuntimeError(f"socket guard permitted outbound connection to {address}")


def main() -> None:
    _prove_loopback()
    _prove_outbound_blocked(socket.AF_INET, ("192.0.2.1", 9))
    _prove_outbound_blocked(socket.AF_INET6, ("2001:db8::1", 9, 0, 0))
    print("socket guard: loopback allowed; outbound IPv4/IPv6 blocked")


if __name__ == "__main__":
    main()
