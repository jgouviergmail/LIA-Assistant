"""Self-check engine — verdicts on synthetic inputs, blindness handling.

The engine must keep working when Prometheus is down (in-process probes still
evaluated, prometheus-backed checks 'unknown') — that exact scenario was live
in dev while this subsystem was designed.
"""

from __future__ import annotations

import asyncio
import itertools
import math
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from src.domains.diagnostics import engine as engine_module
from src.domains.diagnostics.checks import PROM_CHECKS, CheckStatus
from src.domains.diagnostics.engine import run_self_check
from src.infrastructure.telemetry.models import PromResult, PromSample

#: One entry of the event loop resolver's answer: family, type, proto, name, address.
_AddrInfo = tuple[int, int, int, str, tuple[str, int] | tuple[str, int, int, int]]


class _FakePromClient:
    """Instant-query stub returning one configured value for every query."""

    def __init__(self, value: float | None = None, unavailable: bool = False) -> None:
        self._value = value
        self._unavailable = unavailable

    async def instant_query(self, promql: str) -> PromResult:
        if self._unavailable:
            return PromResult(status="unavailable", error="transport:ConnectError")
        if self._value is None:
            return PromResult(status="ok", samples=[])
        return PromResult(
            status="ok",
            samples=[PromSample(metric={}, value=self._value, ts=datetime.now(UTC))],
        )


class _ScriptedResolver:
    """Stands in for the event loop's resolver, one scripted outcome per call.

    An outcome is an address the resolver answers, an ``OSError`` it raises, or
    ``None`` for a query never answered — a datagram lost upstream. The last
    outcome repeats. Every call records the host, the port and the monotonic
    instant it was made, so a test can assert what reached the resolver and how
    the attempts were paced.
    """

    def __init__(self, *outcomes: str | OSError | None, delay: float = 0.0) -> None:
        self._outcomes = list(outcomes)
        self._delay = delay
        self.calls: list[tuple[str, int, float]] = []

    async def getaddrinfo(
        self,
        host: str,
        port: int,
        *,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[_AddrInfo]:
        self.calls.append((host, port, time.monotonic()))
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if outcome is None:
            await asyncio.sleep(3600)
            raise TimeoutError("never answered")
        if isinstance(outcome, OSError):
            raise outcome
        if self._delay:
            await asyncio.sleep(self._delay)
        if ":" in outcome:
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (outcome, port, 0, 0))
            ]
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (outcome, port))]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Answer the running loop's resolutions, the only resolver the probe uses."""
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", self.getaddrinfo)


@asynccontextmanager
async def _listener() -> AsyncIterator[int]:
    """A real TCP listener on the IPv4 loopback; yields its port."""
    server = await asyncio.start_server(lambda _r, w: w.close(), "127.0.0.1", 0)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


def _configure_egress(
    monkeypatch: pytest.MonkeyPatch,
    *,
    target: str,
    timeout: float,
    attempts: int = 3,
    slow: float | None = None,
) -> None:
    """Point the probe at ``target`` with explicit budgets, never the ambient ``.env``."""
    from src.core.config import settings

    monkeypatch.setattr(settings, "diagnostics_egress_probe_target", target)
    monkeypatch.setattr(settings, "diagnostics_egress_probe_timeout_seconds", timeout)
    monkeypatch.setattr(settings, "diagnostics_egress_probe_attempts", attempts)
    monkeypatch.setattr(
        settings, "diagnostics_egress_probe_slow_seconds", timeout / 2 if slow is None else slow
    )


@pytest.fixture
def healthy_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """All in-process probes report healthy.

    The egress probe included: the Taskfile injects the root ``.env``, whose
    target is a real host, so a run through ``task`` would otherwise open a real
    connection and let a slow resolver decide these verdicts.
    """

    async def ok_probe() -> tuple[CheckStatus, float | None, str]:
        return CheckStatus.OK, None, ""

    for probe_name in (
        "_probe_database",
        "_probe_redis",
        "_probe_circuit_breakers",
        "_probe_scheduler_tick",
        "_probe_platform_egress",
    ):
        monkeypatch.setattr(engine_module, probe_name, ok_probe)


@pytest.mark.unit
class TestEngineWithPrometheus:
    async def test_value_below_warn_is_ok(self, healthy_probes: None) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=0.0))
        prom_results = {r.check_id: r for r in snapshot.results}
        assert prom_results["api_error_rate"].status is CheckStatus.OK
        assert snapshot.overall is CheckStatus.OK

    async def test_value_between_warn_and_crit_is_degraded(self, healthy_probes: None) -> None:
        from src.core.config import settings

        check = next(c for c in PROM_CHECKS if c.check_id == "api_error_rate")
        warn = getattr(settings, check.warn_setting)
        crit = getattr(settings, check.crit_setting)
        between = (warn + crit) / 2
        snapshot = await run_self_check(prom_client=_FakePromClient(value=between))
        result = next(r for r in snapshot.results if r.check_id == "api_error_rate")
        assert result.status is CheckStatus.DEGRADED
        assert result.value == pytest.approx(between)

    async def test_value_at_crit_is_critical_and_overall_follows(
        self, healthy_probes: None
    ) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=10_000.0))
        result = next(r for r in snapshot.results if r.check_id == "api_error_rate")
        assert result.status is CheckStatus.CRITICAL
        assert snapshot.overall is CheckStatus.CRITICAL

    async def test_no_samples_is_unknown_no_data(self, healthy_probes: None) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=None))
        result = next(r for r in snapshot.results if r.check_id == "api_error_rate")
        assert result.status is CheckStatus.UNKNOWN
        assert result.detail == "no_data"

    async def test_nan_sample_is_unknown(self, healthy_probes: None) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=math.nan))
        result = next(r for r in snapshot.results if r.check_id == "api_error_rate")
        assert result.status is CheckStatus.UNKNOWN


@pytest.mark.unit
class TestEngineBlind:
    async def test_prometheus_down_keeps_in_process_probes_alive(
        self, healthy_probes: None
    ) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(unavailable=True))
        by_id = {r.check_id: r for r in snapshot.results}
        for check in PROM_CHECKS:
            assert by_id[check.check_id].status is CheckStatus.UNKNOWN
        assert by_id["database"].status is CheckStatus.OK
        # Blindness alone caps the overall verdict at degraded.
        assert snapshot.overall is CheckStatus.DEGRADED


@pytest.mark.unit
class TestEngineProbeFailures:
    async def test_database_probe_exception_is_critical_without_leaking_message(
        self, monkeypatch: pytest.MonkeyPatch, healthy_probes: None
    ) -> None:
        async def broken_probe() -> tuple[CheckStatus, float | None, str]:
            raise ConnectionError("postgres://user:secret@host says no")

        monkeypatch.setattr(engine_module, "_probe_database", broken_probe)
        snapshot = await run_self_check(prom_client=_FakePromClient(value=0.0))
        result = next(r for r in snapshot.results if r.check_id == "database")
        assert result.status is CheckStatus.CRITICAL
        # Exception class name only: messages can carry hosts or credentials.
        assert result.detail == "ConnectionError"
        assert "secret" not in str(snapshot.to_results_jsonb())


@pytest.mark.unit
class TestSnapshotDTO:
    async def test_results_jsonb_shape_is_plain_and_exact(self, healthy_probes: None) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=0.0))
        rows = snapshot.to_results_jsonb()
        assert len(rows) == len(snapshot.results)
        for row in rows:
            assert set(row) == {"check_id", "status", "value", "detail", "alertname"}
            assert isinstance(row["status"], str)


@pytest.mark.unit
class TestProbeCoverageIsAsserted:
    """A registered check with no probe crashes the whole self-check run.

    ``run_self_check`` looks its probe up by ``check_id``; a missing entry is a
    ``KeyError`` that kills the tick — no snapshot, no verdict, and the only
    trace is a scheduler error. ADR-085 doctrine: a mapping keyed by a registry
    gets a boot-time completeness assert.
    """

    def test_every_in_process_check_has_a_probe(self) -> None:
        from src.domains.diagnostics.engine import assert_probe_coverage

        assert_probe_coverage()

    def test_a_check_without_a_probe_is_refused(self) -> None:
        from src.domains.diagnostics.checks import InProcessCheck
        from src.domains.diagnostics.engine import assert_probe_coverage

        ghost = (InProcessCheck(check_id="ghost", title="Ghost", alertname=None),)
        with pytest.raises(AssertionError, match="ghost"):
            assert_probe_coverage(ghost)

    def test_an_orphan_probe_is_refused(self) -> None:
        """A probe nobody registered is dead code that fakes coverage."""
        from src.domains.diagnostics.checks import InProcessCheck
        from src.domains.diagnostics.engine import assert_probe_coverage

        only_one = (InProcessCheck(check_id="database", title="PG", alertname=None),)
        with pytest.raises(AssertionError, match="no check"):
            assert_probe_coverage(only_one)

    def test_the_boot_gate_calls_it(self) -> None:
        import inspect

        from src.infrastructure.startup import registries

        source = inspect.getsource(registries._validate_diagnostics_registries)
        assert "assert_probe_coverage" in source


@pytest.mark.unit
class TestPlatformEgressProbe:
    """The check the 2026-08-28 outage asked for, taught to tell a hiccup from a cut.

    ``net.ipv4.ip_forward`` fell to 0 on the host and every container lost
    outbound routing. The platform could only describe the CONSEQUENCE — 100 %
    LLM failures, two open circuit breakers — never the cause. The probe names
    it, and since ADR-361 it names WHICH step failed and confirms a loss over
    paced attempts: measured on production, Docker's resolver needs 4 s to fail
    over to its next DNS server, so one datagram lost twice used to consume the
    whole single attempt and page the administrator for a platform that was
    never cut off.
    """

    async def test_absent_when_no_target_is_configured(
        self, monkeypatch: pytest.MonkeyPatch, healthy_probes: None
    ) -> None:
        """Unconfigured is neither healthy nor unknown: the check does not exist.

        ``unknown`` would cap every default install at ``degraded``, and ``ok``
        would claim a measurement nobody took.
        """
        from src.core.config import settings

        monkeypatch.setattr(settings, "diagnostics_egress_probe_target", "", raising=False)

        snapshot = await run_self_check(prom_client=_FakePromClient(value=0.0))

        assert "platform_egress" not in {result.check_id for result in snapshot.results}

    async def test_present_when_a_target_is_configured(
        self, monkeypatch: pytest.MonkeyPatch, healthy_probes: None
    ) -> None:
        """Configured, the check runs on every tick: the gate decides, not the probe."""
        from src.core.config import settings

        monkeypatch.setattr(settings, "diagnostics_egress_probe_target", "egress.test:443")

        snapshot = await run_self_check(prom_client=_FakePromClient(value=0.0))

        assert "platform_egress" in {result.check_id for result in snapshot.results}

    async def test_ok_through_the_real_resolver_and_a_real_listener(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No double at all: the loop's own resolver, a real socket, a literal target."""
        async with _listener() as port:
            target = f"127.0.0.1:{port}"
            _configure_egress(monkeypatch, target=target, timeout=10.0)
            status, value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.OK
        assert detail == target
        assert value is not None and value >= 0.0

    async def test_one_prompt_attempt_is_ok_and_ends_the_probe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A clean first attempt is the healthy case: OK, the target as detail, no retry."""
        resolver = _ScriptedResolver("127.0.0.1")
        async with _listener() as port:
            target = f"egress.test:{port}"
            _configure_egress(monkeypatch, target=target, timeout=10.0)
            resolver.install(monkeypatch)
            status, value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.OK
        assert detail == target
        assert value is not None
        assert len(resolver.calls) == 1

    async def test_a_resolver_that_never_answers_is_named_as_a_resolution_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every query lost upstream: the connection itself was never attempted.

        Measured 2026-10-20: the incident read « api.openai.com:443 unreachable
        (TimeoutError) » and pointed at the provider while Docker's resolver was
        still failing over between DNS servers.
        """
        resolver = _ScriptedResolver(None)
        _configure_egress(monkeypatch, target="egress.test:443", timeout=0.05, attempts=2)
        resolver.install(monkeypatch)

        status, value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.CRITICAL
        assert value is None
        assert "egress.test:443" in detail
        assert "name resolution timed out" in detail
        assert len(resolver.calls) == 2

    async def test_a_resolution_error_is_named_by_its_class_never_its_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An error message can carry hosts; the class name is the bounded fact."""
        resolver = _ScriptedResolver(socket.gaierror(-3, "Temporary failure resolving a host"))
        _configure_egress(monkeypatch, target="egress.test:443", timeout=0.05, attempts=1)
        resolver.install(monkeypatch)

        status, _value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.CRITICAL
        assert "name resolution failed (gaierror)" in detail
        assert "Temporary failure" not in detail

    async def test_a_connection_that_never_completes_is_named_as_a_connect_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The 2026-08-28 shape: the name resolves, the packets never leave."""

        async def _never_connects(*_args: object, **_kwargs: object) -> tuple[object, object]:
            await asyncio.sleep(3600)
            raise AssertionError("never reached")

        _configure_egress(monkeypatch, target="egress.test:443", timeout=0.05, attempts=1)
        _ScriptedResolver("192.0.2.1").install(monkeypatch)
        monkeypatch.setattr(asyncio, "open_connection", _never_connects)

        status, _value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.CRITICAL
        assert "connect timed out" in detail

    async def test_critical_when_the_target_never_answers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TEST-NET-1 (RFC 5737) is routable nowhere: a real connect times out or is refused."""
        _configure_egress(monkeypatch, target="192.0.2.1:443", timeout=0.2, attempts=1)

        status, value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.CRITICAL
        assert value is None
        assert "192.0.2.1:443" in detail
        assert "connect" in detail, "a literal resolves locally: the connect is what failed"

    async def test_a_loss_shorter_than_the_attempts_is_degraded_not_critical(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One query lost, the next one answered: the platform reached out, not cleanly."""
        resolver = _ScriptedResolver(None, "127.0.0.1")
        async with _listener() as port:
            _configure_egress(monkeypatch, target=f"egress.test:{port}", timeout=0.5, attempts=3)
            resolver.install(monkeypatch)
            status, value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.DEGRADED
        assert value is not None
        assert "name resolution timed out" in detail
        assert len(resolver.calls) == 2, "a success must end the attempts"

    async def test_a_slow_success_is_degraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A resolver failover answered in 4 s used to read OK beside a 14 ms normal."""
        resolver = _ScriptedResolver("127.0.0.1", delay=0.1)
        async with _listener() as port:
            _configure_egress(monkeypatch, target=f"egress.test:{port}", timeout=5.0, slow=0.05)
            resolver.install(monkeypatch)
            status, value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.DEGRADED
        assert value is not None and value >= 100.0
        assert "slow" in detail and "name resolution" in detail
        assert len(resolver.calls) == 1

    async def test_failed_attempts_are_paced_one_per_budget_and_capped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fast failure waits out its slot, so the attempts cover a real window."""
        resolver = _ScriptedResolver(socket.gaierror(-3, "lookup failed"))
        _configure_egress(monkeypatch, target="egress.test:443", timeout=0.1, attempts=3)
        resolver.install(monkeypatch)

        status, _value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.CRITICAL
        assert len(resolver.calls) == 3
        instants = [instant for _host, _port, instant in resolver.calls]
        gaps = [later - earlier for earlier, later in itertools.pairwise(instants)]
        assert all(gap >= 0.09 for gap in gaps), gaps
        assert "after 3 attempts" in detail

    @pytest.mark.parametrize(
        "target",
        [
            "not-a-target",  # no port at all
            ":443",  # no host
            "host:https",  # port is not a number
            "host:0",  # port out of range
            "host:70000",  # port out of range
        ],
    )
    async def test_a_malformed_target_is_a_configuration_error_not_a_crash(
        self, monkeypatch: pytest.MonkeyPatch, target: str
    ) -> None:
        """A typo in the setting must never read as 'the platform is cut off'."""
        from src.core.config import settings

        monkeypatch.setattr(settings, "diagnostics_egress_probe_target", target, raising=False)

        status, value, detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.UNKNOWN
        assert value is None
        assert "malformed" in detail

    async def test_the_reported_duration_excludes_teardown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A shown number is the measured number: connect time, not connect+close."""

        class _SlowClosingWriter:
            def close(self) -> None:
                return None

            async def wait_closed(self) -> None:
                await asyncio.sleep(0.25)

        async def _instant_connect(*_args: object, **_kwargs: object) -> tuple[object, object]:
            return object(), _SlowClosingWriter()

        _configure_egress(monkeypatch, target="example.test:443", timeout=10.0)
        _ScriptedResolver("192.0.2.10").install(monkeypatch)
        monkeypatch.setattr(asyncio, "open_connection", _instant_connect)

        status, value, _detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.OK
        assert value is not None and value < 100.0, f"teardown leaked into the measure: {value} ms"

    async def test_an_ipv6_literal_is_understood(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`[::1]:port` is the standard spelling; getaddrinfo refuses the brackets."""
        try:
            server = await asyncio.start_server(lambda _r, w: w.close(), "::1", 0)
        except OSError:  # pragma: no cover - host without IPv6 loopback
            pytest.skip("no IPv6 loopback on this host")
        port = server.sockets[0].getsockname()[1]
        try:
            _configure_egress(monkeypatch, target=f"[::1]:{port}", timeout=10.0)
            status, _value, detail = await engine_module._probe_platform_egress()
        finally:
            server.close()
            await server.wait_closed()

        assert status is CheckStatus.OK, detail

    def test_the_ui_can_name_the_check_in_every_locale(self) -> None:
        """A check id with no label renders raw in the admin panel (ADR-085)."""
        import json

        from src.domains.diagnostics.checks import IN_PROCESS_CHECKS, PROM_CHECKS
        from tests._repo_paths import repo_root_or_skip

        root = repo_root_or_skip()
        declared = {check.check_id for check in PROM_CHECKS} | {
            check.check_id for check in IN_PROCESS_CHECKS
        }
        for locale in ("en", "fr", "de", "es", "it", "zh"):
            path = root / "apps" / "web" / "locales" / locale / "translation.json"
            if not path.is_file():
                pytest.skip("guard needs the full repository checkout (locales).")
            labels = json.loads(path.read_text(encoding="utf-8"))["settings"]["admin"][
                "diagnostics"
            ]["checks"]
            missing = declared - set(labels)
            assert not missing, f"{locale}: no label for {sorted(missing)}"


@pytest.mark.unit
class TestIpv6BracketStripping:
    """Brackets are the standard spelling and getaddrinfo refuses them.

    Measured 2026-08-28: `[::1]` resolved on Windows and raised `gaierror` on
    the Linux CI runner — i.e. on the platform that runs in production, where a
    bracketed target would have been reported as "the platform is cut off"
    rather than reached. The probe therefore strips them itself.
    """

    @pytest.mark.parametrize(
        ("target", "expected_host", "expected_port"),
        [
            ("[::1]:8443", "::1", 8443),
            ("[2a00:1450:400c:c06::5f]:443", "2a00:1450:400c:c06::5f", 443),
            ("example.test:443", "example.test", 443),
        ],
    )
    async def test_the_host_reaching_getaddrinfo_is_bracket_free(
        self,
        monkeypatch: pytest.MonkeyPatch,
        target: str,
        expected_host: str,
        expected_port: int,
    ) -> None:
        class _Writer:
            def close(self) -> None:
                return None

            async def wait_closed(self) -> None:
                return None

        async def _instant_connect(*_args: object, **_kwargs: object) -> tuple[object, object]:
            return object(), _Writer()

        resolver = _ScriptedResolver("127.0.0.1")
        _configure_egress(monkeypatch, target=target, timeout=10.0)
        resolver.install(monkeypatch)
        monkeypatch.setattr(asyncio, "open_connection", _instant_connect)

        status, _value, _detail = await engine_module._probe_platform_egress()

        assert status is CheckStatus.OK
        assert [(host, port) for host, port, _instant in resolver.calls] == [
            (expected_host, expected_port)
        ]
