"""Unit tests for LLMModelRepository (CRUD on llm_models).

Note on asyncio markers: this project sets ``asyncio_mode = "auto"`` in
``pyproject.toml``, so ``async def`` test functions are run by pytest-asyncio
without an explicit ``@pytest.mark.asyncio`` marker.
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import LLMModelKindEnum, LLMProviderEnum
from src.domains.llm.repository import LLMModelRepository


@pytest_asyncio.fixture
async def repo(async_session: AsyncSession) -> LLMModelRepository:
    return LLMModelRepository(async_session)


# Default reasoning + sampling kwargs for repo.create_model() in tests.
# Mirror the "non-reasoning chat with full sampling" baseline so existing
# tests stay focused on what they were written to verify (creation, lookup,
# soft delete, ...) rather than reasoning shape semantics — the latter has
# its own dedicated suite in test_service.py and test_service_helpers.py.
_DEFAULT_REASONING_KWARGS: dict[str, Any] = {
    "kind": LLMModelKindEnum.chat,
    "reasoning_enum_values": None,
    "reasoning_doc_i18n_key": None,
    "supports_temperature": True,
    "supports_top_p": True,
    "supports_frequency_penalty": True,
    "supports_presence_penalty": True,
}


@pytest.mark.unit
async def test_create_model_inserts_row_and_returns_it(repo: LLMModelRepository) -> None:
    created = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="gpt-test-1",
        max_input_tokens=1000,
        max_output_tokens=200,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    assert created.id is not None
    assert created.model_name == "gpt-test-1"
    assert created.provider == LLMProviderEnum.openai
    assert created.is_active is True
    # Server-side defaults must be populated by BaseRepository.create() refresh()
    assert created.created_at is not None
    assert created.updated_at is not None


@pytest.mark.unit
async def test_get_by_name_returns_existing_row(repo: LLMModelRepository) -> None:
    created = await repo.create_model(
        provider=LLMProviderEnum.anthropic,
        model_name="claude-test-2",
        max_input_tokens=200000,
        max_output_tokens=8192,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=True,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    fetched = await repo.get_by_name("claude-test-2")
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.unit
async def test_get_by_name_returns_none_when_missing(repo: LLMModelRepository) -> None:
    assert await repo.get_by_name("does-not-exist") is None


@pytest.mark.unit
async def test_get_by_id_round_trip(repo: LLMModelRepository) -> None:
    created = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="gpt-test-roundtrip",
        max_input_tokens=1000,
        max_output_tokens=100,
        supports_tools=False,
        supports_structured_output=False,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.model_name == "gpt-test-roundtrip"


@pytest.mark.unit
async def test_get_by_id_returns_none_when_missing(repo: LLMModelRepository) -> None:
    assert await repo.get_by_id(uuid.uuid4()) is None


@pytest.mark.unit
async def test_get_by_id_excludes_inactive_by_default(repo: LLMModelRepository) -> None:
    """Soft-delete-aware get_by_id (inherited from BaseRepository)."""
    created = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="get-inactive-1",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    await repo.deactivate_by_id(created.id)
    assert await repo.get_by_id(created.id) is None
    # include_inactive=True bypasses the soft-delete filter.
    refreshed = await repo.get_by_id(created.id, include_inactive=True)
    assert refreshed is not None
    assert refreshed.is_active is False


@pytest.mark.unit
async def test_list_active_returns_only_active(repo: LLMModelRepository) -> None:
    await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="active-1",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    inactive = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="inactive-1",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    await repo.deactivate_by_id(inactive.id)

    actives = await repo.list_active()
    names = {m.model_name for m in actives}
    assert "active-1" in names
    assert "inactive-1" not in names


@pytest.mark.unit
async def test_update_capabilities_mutates_only_given_fields(repo: LLMModelRepository) -> None:
    created = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="upd-1",
        max_input_tokens=100,
        max_output_tokens=50,
        supports_tools=False,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    updated = await repo.update_capabilities(
        created.id,
        max_output_tokens=999,
        supports_tools=True,
    )
    assert updated.max_output_tokens == 999
    assert updated.supports_tools is True
    assert updated.max_input_tokens == 100  # untouched
    assert updated.is_reasoning_model is False  # untouched


@pytest.mark.unit
async def test_update_capabilities_rejects_immutable_fields(repo: LLMModelRepository) -> None:
    created = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="upd-2",
        max_input_tokens=100,
        max_output_tokens=50,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    with pytest.raises(ValueError, match="immutable"):
        await repo.update_capabilities(created.id, provider=LLMProviderEnum.anthropic)
    with pytest.raises(ValueError, match="immutable"):
        await repo.update_capabilities(created.id, model_name="renamed")


@pytest.mark.unit
async def test_update_capabilities_rejects_unknown_fields(repo: LLMModelRepository) -> None:
    """Typos in field names must raise instead of silently no-op'ing."""
    created = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="upd-typo",
        max_input_tokens=100,
        max_output_tokens=50,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    with pytest.raises(ValueError, match="Unknown LLMModel fields"):
        await repo.update_capabilities(created.id, supports_tool=True)  # missing 's'


@pytest.mark.unit
async def test_update_capabilities_raises_when_missing(repo: LLMModelRepository) -> None:
    with pytest.raises(LookupError):
        await repo.update_capabilities(uuid.uuid4(), max_output_tokens=10)


@pytest.mark.unit
async def test_deactivate_by_id_sets_is_active_false(repo: LLMModelRepository) -> None:
    created = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="deact-1",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_DEFAULT_REASONING_KWARGS,
    )
    await repo.deactivate_by_id(created.id)
    refreshed = await repo.get_by_id(created.id, include_inactive=True)
    assert refreshed is not None
    assert refreshed.is_active is False


@pytest.mark.unit
async def test_deactivate_by_id_raises_when_missing(repo: LLMModelRepository) -> None:
    with pytest.raises(LookupError):
        await repo.deactivate_by_id(uuid.uuid4())
