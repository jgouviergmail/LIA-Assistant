"""Native action input and invocation paths share the same closed boundary."""

from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from langgraph.store.memory import InMemoryStore

from src.domains.agents.application.catalogue_registration import PREFERENCES_UPDATE_MANIFEST
from src.domains.agents.tools.application_action_tools import update_lia_preferences_tool
from src.domains.agents.tools.application_read_tools import get_lia_preferences_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "family,payload",
    [
        ("assistant", {"memory_enabled": False}),
        ("layout", {"settings_shortcuts": ["font"]}),
    ],
)
async def test_raw_pipeline_patch_uses_the_same_closed_model_before_preparation(
    family: str, payload: dict[str, object]
) -> None:
    from src.domains.agents.application.preference_dispatch import preference_model
    from src.domains.agents.application.preparation import _preference_content

    module = import_module(
        f"src.domains.agents.tools.application_{'action' if family == 'assistant' else 'layout'}_tools"
    )
    prepare = AsyncMock(
        return_value=_preference_content(
            uuid4(),
            preference_model(f"{family}_preferences.update").model_validate(payload),
            {key: True if family == "assistant" else [] for key in payload},
        )
    )

    @asynccontextmanager
    async def session():
        yield AsyncMock()

    with (
        patch.object(module, f"prepare_{family}_content", prepare),
        patch(
            "src.domains.agents.application.reversible_execution.execute_reversible_change",
            new=AsyncMock(
                return_value=UnifiedToolOutput.data_success(message="Saved.", structured_data={})
            ),
        ),
        patch.object(module, "get_db_context", session),
    ):
        result = await getattr(module, f"update_lia_{family}_preferences_tool").coroutine(
            patch=payload, runtime=make_tool_runtime(user_id=uuid4(), store=InMemoryStore())
        )
    assert result.success
    assert isinstance(prepare.await_args.args[2], preference_model(f"{family}_preferences.update"))


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "set"},
        {"mode": "set", "patch": {"font_size": True}},
        {"mode": "increase_font", "patch": {"font_size": 17}},
        {"mode": "set", "patch": {"hashed_password": "secret"}},
    ],
)
def test_offered_schema_refuses_incompatible_or_sensitive_change(
    payload: dict[str, object],
) -> None:
    schema = PREFERENCES_UPDATE_MANIFEST.parameters[0].schema
    assert schema is not None
    assert not Draft202012Validator(schema).is_valid(payload)


async def test_raw_pipeline_dictionary_resolves_a_concrete_reversible_change() -> None:
    actor = User(id=uuid4(), is_active=True, is_superuser=False, deleted_at=None, font_size=16)
    db = AsyncMock()
    db.scalar.side_effect = ["true", actor]

    @asynccontextmanager
    async def session():
        yield db

    context = make_tool_runtime(user_id=actor.id, store=InMemoryStore(), language="fr")
    with (
        patch("src.domains.agents.tools.application_action_tools.get_db_context", session),
        patch(
            "src.domains.agents.application.reversible_execution.execute_reversible_change",
            new_callable=AsyncMock,
            return_value=UnifiedToolOutput.data_success(message="Saved.", structured_data={}),
        ) as execute,
    ):
        # The pipeline calls coroutine with raw JSON, unlike ainvoke's Pydantic path.
        result = await update_lia_preferences_tool.coroutine(
            change={"mode": "increase_font"}, runtime=context
        )
    assert result.success
    assert not result.metadata.get("requires_confirmation")
    assert not result.registry_updates
    assert execute.await_args.args[0].after == {"font_size": 17}
    assert actor.font_size == 16
    execute.assert_awaited_once()


async def test_invalid_stored_projection_is_a_dependency_failure_without_raw_data() -> None:
    actor = User(id=uuid4(), is_active=True, deleted_at=None, font_size=object())
    db = AsyncMock()
    db.scalar.side_effect = ["true", actor]

    @asynccontextmanager
    async def session():
        yield db

    with patch("src.domains.agents.tools.application_read_tools.get_db_context", session):
        result = await get_lia_preferences_tool.coroutine(
            fields=["font_size"], runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore())
        )
    assert not result.success
    assert result.error_code == "DEPENDENCY_ERROR"
    assert "object at" not in result.message
