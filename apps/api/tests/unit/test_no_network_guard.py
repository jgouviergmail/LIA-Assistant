"""Self-test for the F028 unit-suite no-network guard (see ``conftest.py``)."""

from __future__ import annotations

import socket

import pytest

from tests.unit import conftest as unit_conftest
from tests.unit.conftest import UnitTestNetworkError


def test_external_socket_connection_is_blocked() -> None:
    """A plain unit test must not be able to open an external outbound socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(UnitTestNetworkError):
            # 203.0.113.0/24 is TEST-NET-3 (RFC 5737): never routable, so if the
            # guard were absent this would time out rather than connect.
            sock.connect(("203.0.113.1", 80))
    finally:
        sock.close()


def test_connect_ex_is_also_blocked() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(UnitTestNetworkError):
            sock.connect_ex(("203.0.113.1", 80))
    finally:
        sock.close()


def test_loopback_is_allowed_through_the_guard() -> None:
    """Loopback stays permitted (in-process TestClient lifespans, dev DB/Redis).

    We don't require a listener — a refused/failed loopback connect is fine; the
    point is the guard must NOT raise ``UnitTestNetworkError`` for 127.0.0.1.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.05)
    try:
        try:
            sock.connect(("127.0.0.1", 65500))  # likely nothing listening
        except UnitTestNetworkError:  # pragma: no cover - would be a guard bug
            raise
        except OSError:
            pass  # connection refused/timeout is the expected, allowed outcome
    finally:
        sock.close()


def test_guard_is_active_by_default() -> None:
    """Outside a ``real_io`` marker, the connect method is the guard, not the real one."""
    assert socket.socket.connect is not unit_conftest._REAL_CONNECT


@pytest.mark.real_io
def test_real_io_marker_opts_out() -> None:
    """A ``real_io``-marked test keeps the genuine socket implementation."""
    assert socket.socket.connect is unit_conftest._REAL_CONNECT
