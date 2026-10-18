"""The admin screen is told the output cap the request is held to (ADR-184).

``/llm-config/metadata`` published ``max_output_tokens`` for every model, but
that column is a column DEFAULT on a row nobody curated: warning an
administrator against it would flag correct budgets. What the screen receives
is the output cap ``infrastructure/llm/output_cap.py`` enforces — the figure a
curated row vouches for, or nothing — so the warning and that rule cannot
disagree (a provider branch's own ceiling is outside it).
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.llm_config.models import LLMConfigOverride
from src.domains.llm_config.service import LLMConfigService
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile

pytestmark = pytest.mark.unit

_IMAGE_CACHE = "src.domains.image_generation.options_cache.ImageOptionsCache"


@pytest.fixture(autouse=True)
def _isolated_catalogue() -> Generator[None]:
    saved = (
        dict(ModelCapabilitiesCache._cache),
        dict(ModelCapabilitiesCache._provider_by_model),
        dict(ModelCapabilitiesCache._discovered),
        dict(ModelCapabilitiesCache._discovered_provider),
    )
    ModelCapabilitiesCache._cache = {}
    ModelCapabilitiesCache._provider_by_model = {}
    ModelCapabilitiesCache._discovered = {}
    ModelCapabilitiesCache._discovered_provider = {}
    yield
    (
        ModelCapabilitiesCache._cache,
        ModelCapabilitiesCache._provider_by_model,
        ModelCapabilitiesCache._discovered,
        ModelCapabilitiesCache._discovered_provider,
    ) = saved


def _install(model: str, provider: str, *, max_output_tokens: int, provenance: str) -> None:
    ModelCapabilitiesCache._cache[model] = ModelProfile(
        model_id=model,
        max_output_tokens=max_output_tokens,
        capability_provenance=provenance,
    )
    ModelCapabilitiesCache._provider_by_model[model] = provider


def _published() -> dict[str, int | None]:
    with patch(f"{_IMAGE_CACHE}.get_models_grouped_by_provider", return_value={}):
        metadata = LLMConfigService.get_provider_models()
    return {
        model.model_id: model.vouched_max_output_tokens
        for models in metadata.providers.values()
        for model in models
    }


def test_a_curated_row_publishes_the_cap_the_request_is_held_to() -> None:
    _install("meta-curated", "anthropic", max_output_tokens=128_000, provenance="verified")

    assert _published()["meta-curated"] == 128_000


def test_a_row_nobody_curated_publishes_no_cap() -> None:
    _install("meta-declared", "openai", max_output_tokens=4_096, provenance="declared")

    published = _published()

    assert published["meta-declared"] is None


def test_a_self_hosted_model_publishes_no_cap() -> None:
    _install("meta-local", "ollama", max_output_tokens=8_192, provenance="imported")

    assert _published()["meta-local"] is None


async def test_the_admin_screen_reads_the_stored_budget_never_the_capped_one() -> None:
    """The card's warning compares the STORED figure with the cap.

    The runtime resolution (`get_llm_config_for_agent`) now returns the capped
    budget; the admin listing must keep reading the row itself, or a slot
    stored above its model's cap would look fine on the very screen meant to
    say it is not.
    """
    _install("meta-slot", "anthropic", max_output_tokens=128_000, provenance="verified")
    row = LLMConfigOverride(
        llm_type="subagent", provider="anthropic", model="meta-slot", max_tokens=200_000
    )
    db = AsyncMock()
    single = MagicMock()
    single.scalar_one_or_none.return_value = row
    listing = MagicMock()
    listing.scalars.return_value.all.return_value = [row]
    service = LLMConfigService(db)

    db.execute = AsyncMock(return_value=single)
    one = await service.get_config("subagent")
    db.execute = AsyncMock(return_value=listing)
    every = {config.llm_type: config for config in await service.get_all_configs()}

    assert one.effective.max_tokens == 200_000
    assert every["subagent"].effective.max_tokens == 200_000


async def test_the_ollama_listing_publishes_no_cap_when_the_server_is_away() -> None:
    _install("meta-local:7b", "ollama", max_output_tokens=8_192, provenance="imported")

    with patch(
        "src.infrastructure.llm.providers.ollama_discovery.refresh_ollama_capabilities",
        new=AsyncMock(return_value=[]),
    ):
        response = await LLMConfigService.get_ollama_models()

    assert response.source == "fallback"
    assert [(m.model_id, m.vouched_max_output_tokens) for m in response.models] == [
        ("meta-local:7b", None)
    ]
