"""Explicit explanation selectors and error boundaries stay closed and source-complete."""

import ast
import inspect
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from pydantic import ValidationError

from src.domains.agents.application.interest_detail_schemas import InterestDetailRead
from src.domains.agents.tools.application_interest_tools import get_lia_interest_details_tool
from src.domains.interests.explainability import explain_interest
from src.domains.interests.schemas import InterestExplanation
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("extra", ["actor_id", "conversation_id", "excerpt", "embedding"])
def test_detail_selection_refuses_scope_and_source_injection(extra: str) -> None:
    with pytest.raises(ValidationError):
        InterestDetailRead.model_validate({"interest_id": str(uuid4()), extra: "injected"})


def test_source_explanation_additions_cannot_be_silently_omitted() -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(explain_interest)))
    fields = next(
        {item.arg for item in node.keywords}
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "InterestExplanation"
    )
    assert fields == set(InterestExplanation.model_fields)
    assert (
        "runtime"
        not in get_lia_interest_details_tool.tool_call_schema.model_json_schema()["properties"]
    )


async def test_corrupt_stored_details_are_not_reported_as_bad_user_selection() -> None:
    owner = uuid4()

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield object()

    with (
        installed_runtime_context(user_id=owner),
        patch("src.domains.agents.tools.application_interest_tools.get_db_context", session),
        patch(
            "src.domains.agents.tools.application_interest_tools.read_interest_details",
            AsyncMock(side_effect=ValueError("Corrupt source")),
        ),
    ):
        output = await get_lia_interest_details_tool.coroutine(
            selection=InterestDetailRead(interest_id=uuid4()),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    assert not output.success and output.error_code == "INVALID_RESPONSE_FORMAT"
    assert "Corrupt source" not in str(output)
