"""A loaded catalogue and an invalid deployment configuration are different failures."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest

from src.core import bootstrap
from src.domains.llm_config import constants
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.startup import caches

pytestmark = pytest.mark.unit


def test_matrix_audit_uses_the_effective_slot_instead_of_an_inactive_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default = constants.LLM_DEFAULTS["response"].model_copy(
        update={"model": "inactive-default", "reasoning_effort": None}
    )
    monkeypatch.setattr(constants, "LLM_DEFAULTS", {"response": default})
    monkeypatch.setattr(
        LLMConfigOverrideCache,
        "_overrides",
        {"response": {"provider": "openai", "model": "active-override"}},
    )
    monkeypatch.setattr(ModelCapabilitiesCache, "_loaded", True)
    monkeypatch.setattr(
        ModelCapabilitiesCache,
        "_cache",
        {"active-override": ModelProfile(model_id="active-override")},
    )

    bootstrap.validate_llm_defaults_against_matrix(effective=True)

    with pytest.raises(RuntimeError, match="inactive-default"):
        bootstrap.validate_llm_defaults_against_matrix()


@pytest.mark.parametrize("load_fails", [False, True])
async def test_configuration_audit_never_skips_the_independent_failover_check(
    monkeypatch: pytest.MonkeyPatch, load_fails: bool
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[Mock]:
        yield Mock()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(LLMConfigOverrideCache, "load_from_db", AsyncMock())
    monkeypatch.setattr(LLMConfigOverrideCache, "get_api_key", Mock(return_value="configured"))
    monkeypatch.setattr(
        ModelCapabilitiesCache,
        "load_from_db",
        AsyncMock(side_effect=ConnectionError() if load_fails else None),
    )
    monkeypatch.setattr(
        "src.domains.image_generation.options_cache.ImageOptionsCache.load_from_db", AsyncMock()
    )
    monkeypatch.setattr("src.infrastructure.cache.invalidation.register_cache", Mock())
    monkeypatch.setattr(caches.settings, "skills_enabled", False)
    audit = Mock(side_effect=RuntimeError("invalid effective slot"))
    monkeypatch.setattr(caches, "validate_llm_defaults_against_matrix", audit)
    failover = Mock()
    monkeypatch.setattr("src.infrastructure.llm.failover.assert_failover_chain", failover)
    log = Mock()
    monkeypatch.setattr(caches, "logger", log)

    await caches.init_config_caches()

    critical_events = [call.args[0] for call in log.critical.call_args_list]
    if load_fails:
        failover.assert_not_called()
        audit.assert_not_called()
        assert "model_capabilities_cache_initialization_failed" in critical_events
    else:
        failover.assert_called_once_with(caches.settings.fallback_models)
        audit.assert_called_once_with(effective=True)
        assert "model_capabilities_cache_initialization_failed" not in critical_events
        assert any(
            call.args[0] == "llm_configuration_validation_failed"
            for call in log.error.call_args_list
        )
