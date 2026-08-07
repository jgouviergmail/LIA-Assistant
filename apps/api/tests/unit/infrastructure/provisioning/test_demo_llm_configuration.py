"""A demonstrator must answer with the keys it actually holds.

The registry ships one provider per LLM type, chosen for the full product:
Qwen here, OpenAI there. A demonstrator carries ONE provider key — the cheap
one the owner is willing to spend on strangers — so every type that points
somewhere else fails, and the visitor gets "the model provider is having
technical difficulties" on their very first message.

Measured 2026-08-06 on the first real conversation: the router reached OpenAI
with `NOT_CONFIGURED` (401) and the query analyzer reached Qwen (connection
refused, the host is not even on the egress allowlist). Nothing was broken —
the instance was simply calling providers it had no key for.

So provisioning writes an override for EVERY type. Not a subset: a single
type left pointing elsewhere is a path that fails under load, at random,
depending on which node the graph reaches first.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _settings(provider: str = "deepseek", model: str = "deepseek-chat") -> MagicMock:
    fake = MagicMock()
    fake.demo_instance_llm_provider = provider
    fake.demo_instance_llm_model = model
    return fake


class TestEveryTypeIsPointedAtTheConfiguredProvider:
    async def test_every_llm_type_of_the_registry_gets_an_override(self) -> None:
        from src.domains.llm_config.constants import LLM_DEFAULTS
        from src.infrastructure.provisioning.demo_llm import build_demo_overrides

        overrides = build_demo_overrides(provider="deepseek", model="deepseek-chat")

        text_types = {
            name
            for name, default in LLM_DEFAULTS.items()
            if default.provider not in {"elevenlabs", "edge"}
        }
        assert set(overrides) == text_types, (
            "a type left out keeps its registry provider and fails whenever " "the graph reaches it"
        )
        for llm_type, (provider, model) in overrides.items():
            assert provider == "deepseek", llm_type
            assert model == "deepseek-chat", llm_type

    def test_it_refuses_a_provider_it_cannot_name(self) -> None:
        from src.infrastructure.provisioning.demo_llm import build_demo_overrides

        # An unknown provider would write 57 rows pointing nowhere, and the
        # failure would surface one message at a time.
        with pytest.raises(ValueError, match="unknown provider"):
            build_demo_overrides(provider="not-a-provider", model="x")

    def test_an_empty_provider_writes_nothing(self) -> None:
        """No configured provider means: leave the registry alone."""
        from src.infrastructure.provisioning.demo_llm import build_demo_overrides

        assert build_demo_overrides(provider="", model="") == {}


class TestProvisioningAppliesIt:
    async def test_provisioning_writes_the_overrides(self) -> None:
        from src.infrastructure.provisioning.demo_llm import apply_demo_llm_configuration

        # A MagicMock with ONE async member: `add` and `scalars()` are
        # synchronous in SQLAlchemy, and an AsyncMock would hand production
        # code coroutines nobody awaits (guard F028).
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        )
        session.flush = AsyncMock()

        reload = AsyncMock()
        with (
            patch("src.infrastructure.provisioning.demo_llm.settings", _settings()),
            patch(
                "src.infrastructure.provisioning.demo_llm.LLMConfigOverrideCache.invalidate_and_reload",
                reload,
            ),
        ):
            written = await apply_demo_llm_configuration(session)

        from src.infrastructure.provisioning.demo_llm import build_demo_overrides

        assert written == len(build_demo_overrides(provider="deepseek", model="deepseek-chat"))
        # Writing the rows is not enough: the factory reads the in-memory
        # cache, so an un-reloaded cache leaves the instance calling the
        # registry's provider while the table says otherwise.
        reload.assert_awaited_once()

    async def test_it_does_nothing_when_no_provider_is_configured(self) -> None:
        from src.infrastructure.provisioning.demo_llm import apply_demo_llm_configuration

        session = MagicMock()
        session.execute = AsyncMock()
        with patch("src.infrastructure.provisioning.demo_llm.settings", _settings(provider="")):
            written = await apply_demo_llm_configuration(session)

        assert written == 0
        session.add.assert_not_called()


class TestReprovisioningStillConfigures:
    async def test_an_already_marked_instance_still_gets_its_llm_configuration(self) -> None:
        """Changing provider must not require throwing the database away.

        The marker is written once; the LLM configuration is what an operator
        actually revisits — a new key, a cheaper model. An early return on
        "already provisioned" would make `task demo:provision` a no-op
        exactly when it is being run to change something.
        """
        from src.infrastructure.provisioning import demo_instance

        marker = MagicMock()
        marker.value = "true"
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=lambda: marker,
                scalars=lambda: MagicMock(all=lambda: []),
            )
        )
        session.commit = AsyncMock()

        applied = AsyncMock(return_value=57)
        with (
            patch.object(demo_instance, "apply_demo_llm_configuration", applied),
            patch.object(demo_instance, "get_db_context", _db_context(session)),
            patch.object(demo_instance, "invalidate_setting_cache", AsyncMock()),
        ):
            report = await demo_instance.provision_demo_instance()

        assert report.already_provisioned is True
        applied.assert_awaited_once()


def _db_context(session: object) -> object:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _context():  # type: ignore[no-untyped-def]
        yield session

    return _context


class TestTheDebugPanelIsOpenedForVisitors:
    """A demonstrator shows how LIA works, reasoning included.

    The debug panel is off by default everywhere else — it exposes the run's
    internals, which is noise for an ordinary user and a support burden. On a
    demonstrator it is the point: a visitor who can watch the routing, the
    plan and the token cost understands what they are being shown.

    Written as an INITIAL value, never re-applied: an operator who turns it
    off must stay off across restarts, unlike the LLM configuration which the
    instance cannot work without.
    """

    async def test_provisioning_opens_it_when_nothing_was_decided(self) -> None:
        from src.domains.system_settings.models import SystemSettingKey
        from src.infrastructure.provisioning.demo_defaults import (
            apply_demo_setting_defaults,
        )

        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        )
        added: list[object] = []
        session.add = added.append

        written = await apply_demo_setting_defaults(session)

        assert written == 1
        assert added[0].key == SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED
        assert added[0].value == "true"

    async def test_an_operator_decision_is_never_overwritten(self) -> None:
        from src.infrastructure.provisioning.demo_defaults import (
            apply_demo_setting_defaults,
        )

        existing = MagicMock()
        existing.key = "debug_panel_user_access_enabled"
        existing.value = "false"
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [existing]))
        )
        added: list[object] = []
        session.add = added.append

        written = await apply_demo_setting_defaults(session)

        # Turning it back on at every boot would make the switch a decoration.
        assert written == 0
        assert added == []
        assert existing.value == "false"
