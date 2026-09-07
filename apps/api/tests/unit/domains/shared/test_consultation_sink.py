"""The seam a domain records through, and what it does with no register.

``agents`` imports ``relations`` (ADR-269), so a domain that imported the
consultation register back would close a cycle — and the coupling ratchet
counts LOCAL imports too, so hiding it inside a function would only make the
edge harder to see. The dependency is inverted instead: this module holds the
seam, the register installs itself at import, and any domain calls the seam.

The property that makes that safe is the one tested here: **with nothing
installed, recording is a no-op rather than an error**. A script, a probe or a
narrow unit test has no register open, and a seam that raised there would turn
an observability concern into an outage — the exact inversion of what a
register is for.
"""

from __future__ import annotations

import pytest

from src.domains.shared import consultation_sink

pytestmark = pytest.mark.unit


class TestWithNoRegisterInstalled:
    """A probe, a script, a narrow test: none of them open a register."""

    def test_recording_writes_nothing_and_raises_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consultation_sink, "_sink", consultation_sink._ignore)
        consultation_sink.record_consultation(
            user_id="11111111-1111-1111-1111-111111111111",
            capability="briefing:mails",
            source="user",
            succeeded=True,
            duration_ms=4,
        )

    async def test_the_collector_yields_an_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It must still be usable as a context manager, or callers branch."""
        monkeypatch.setattr(consultation_sink, "_collector_factory", None)
        async with consultation_sink.consultation_collector(run_id="run-1") as rows:
            assert rows == []
            rows.append("nothing keeps this")

    def test_the_seam_reports_itself_unclaimed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(consultation_sink, "_sink", consultation_sink._ignore)
        assert consultation_sink.sink_is_installed() is False


class TestOnceTheRegisterClaimsIt:
    """Installed by its owner, once, at import."""

    def test_the_register_receives_every_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        received: list[dict] = []

        def _capture(**kwargs: object) -> None:
            received.append(kwargs)

        monkeypatch.setattr(consultation_sink, "_sink", _capture)
        consultation_sink.record_consultation(
            user_id="11111111-1111-1111-1111-111111111111",
            capability="heartbeat:emails",
            source="proactive",
            succeeded=False,
            duration_ms=17,
            run_id="sweep-9",
        )

        assert received == [
            {
                "user_id": "11111111-1111-1111-1111-111111111111",
                "capability": "heartbeat:emails",
                "source": "proactive",
                "succeeded": False,
                "duration_ms": 17,
                "run_id": "sweep-9",
            }
        ]

    def test_installing_claims_the_seam(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(consultation_sink, "_sink", consultation_sink._ignore)
        consultation_sink.install_consultation_sink(lambda **_: None)
        assert consultation_sink.sink_is_installed() is True

    async def test_the_installed_factory_provides_the_live_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from contextlib import asynccontextmanager

        kept: list[str] = []

        @asynccontextmanager
        async def _factory(*, run_id: str):  # type: ignore[no-untyped-def]
            kept.append(run_id)
            yield ["existing"]

        monkeypatch.setattr(consultation_sink, "_collector_factory", _factory)
        async with consultation_sink.consultation_collector(run_id="run-2") as rows:
            assert rows == ["existing"]
        assert kept == ["run-2"]

    def test_installing_a_factory_replaces_the_previous_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consultation_sink, "_collector_factory", None)
        sentinel = object()
        consultation_sink.install_collector_factory(sentinel)  # type: ignore[arg-type]
        assert consultation_sink._collector_factory is sentinel


class TestTheRealWiringIsInPlace:
    """« If you import it, it installs » is not « it is imported ».

    That distinction cost the heartbeat register everything. The first version
    of this class asserted only the conditional — import the module, the seam
    is claimed — which is true and useless: measured on dev 2026-09-07, along
    the exact import path the sweep uses (the proactive runner, then
    ``heartbeat.consultations``), ``sink_is_installed()`` answered **False**.
    The register worked only because the API happens to import the treatments
    router at boot. Reorder that and every out-of-turn consultation is dropped
    by a no-op, silently, with no signal.
    """

    def test_importing_the_register_claims_the_seam(self) -> None:
        import src.domains.agents.effects.treatments  # noqa: F401

        assert consultation_sink.sink_is_installed() is True

    def test_the_boot_declares_the_wiring_rather_than_inheriting_it(self) -> None:
        """A declared step, not a side effect of somebody else's import."""
        from src.infrastructure.startup.registries import _install_consultation_sink

        _install_consultation_sink()
        assert consultation_sink.sink_is_installed() is True

    def test_the_boot_refuses_a_mute_register(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An observability subsystem that fails open is the failure nobody sees."""
        from src.infrastructure.startup import registries

        monkeypatch.setattr(consultation_sink, "sink_is_installed", lambda: False)
        with pytest.raises(RuntimeError, match="did not claim its seam"):
            registries._install_consultation_sink()

    def test_the_step_runs_in_the_registry_boot_segment(self) -> None:
        """Declared AND called: a step nobody calls guards nothing."""
        import ast
        import inspect

        from src.infrastructure.startup import registries

        called = {
            node.func.id
            for node in ast.walk(ast.parse(inspect.getsource(registries)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_install_consultation_sink" in called
