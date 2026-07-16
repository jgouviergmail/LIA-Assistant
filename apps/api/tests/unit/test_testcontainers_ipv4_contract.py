"""Contract: Windows test-DB URLs never use ``localhost`` (IPv4 loopback only).

On Windows, ``localhost`` resolves to ``::1`` first; Docker publishes on IPv4
only, so each connection wastes ~10 s on the doomed IPv6 attempt before falling
back (~21 s of repeated per-test setup, measured 30× slower). ``conftest``
forces IPv4 loopback for Testcontainers and normalizes the returned URLs. These
tests pin that contract deterministically (``sys.platform`` monkeypatched, so
they hold on the Linux CI runner too) and guard against a regression that would
silently reintroduce the slow path on the Windows runner.
"""

from __future__ import annotations

import pytest

from tests.conftest import _force_testcontainers_ipv4_on_windows, _prefer_ipv4_loopback


class TestPreferIpv4Loopback:
    def test_rewrites_localhost_host_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "win32")
        url = "postgresql+asyncpg://test:pw@localhost:49153/test"
        assert _prefer_ipv4_loopback(url) == "postgresql+asyncpg://test:pw@127.0.0.1:49153/test"

    def test_rewrites_localhost_without_port_on_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.platform", "win32")
        assert _prefer_ipv4_loopback("postgresql://u:p@localhost/db").endswith("@127.0.0.1/db")

    def test_noop_off_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "linux")
        url = "postgresql+asyncpg://test:pw@localhost:5432/test"
        assert _prefer_ipv4_loopback(url) == url

    def test_does_not_touch_localhost_inside_credentials_or_dbname(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``localhost`` appearing as a password or db-name substring must survive:
        # only the ``@localhost:``/``@localhost/`` host token is rewritten.
        monkeypatch.setattr("sys.platform", "win32")
        url = "postgresql+asyncpg://user:localhostpw@127.0.0.1:5432/localhost_db"
        assert _prefer_ipv4_loopback(url) == url

    def test_does_not_touch_remote_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "win32")
        url = "postgresql+asyncpg://u:p@db.internal:5432/test"
        assert _prefer_ipv4_loopback(url) == url


class TestForceTestcontainersIpv4:
    @pytest.fixture(autouse=True)
    def _reset_override(self) -> None:
        from testcontainers.core.config import testcontainers_config

        original = testcontainers_config.tc_host_override
        testcontainers_config.tc_host_override = None
        yield
        testcontainers_config.tc_host_override = original

    def test_sets_override_on_windows_local_docker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from testcontainers.core.config import testcontainers_config

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.delenv("DOCKER_HOST", raising=False)
        _force_testcontainers_ipv4_on_windows()
        assert testcontainers_config.tc_host_override == "127.0.0.1"

    def test_noop_off_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from testcontainers.core.config import testcontainers_config

        monkeypatch.setattr("sys.platform", "linux")
        _force_testcontainers_ipv4_on_windows()
        assert testcontainers_config.tc_host_override is None

    def test_respects_explicit_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from testcontainers.core.config import testcontainers_config

        monkeypatch.setattr("sys.platform", "win32")
        testcontainers_config.tc_host_override = "10.0.0.5"
        _force_testcontainers_ipv4_on_windows()
        assert testcontainers_config.tc_host_override == "10.0.0.5"

    def test_skips_remote_docker_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from testcontainers.core.config import testcontainers_config

        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("DOCKER_HOST", "tcp://192.168.0.9:2375")
        _force_testcontainers_ipv4_on_windows()
        assert testcontainers_config.tc_host_override is None
