"""Future UI creation fields must reach the shared domain command used by tools."""

import ast
import inspect
import textwrap

import pytest

from src.domains.memories.schemas import MemoryCreate
from src.domains.memories.service import MemoryService

pytestmark = pytest.mark.unit


def test_shared_creation_covers_every_ui_field_without_actor_or_private_input() -> None:
    method = ast.parse(textwrap.dedent(inspect.getsource(MemoryService.create_from_management)))
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_memory"
    ]
    assert len(calls) == 1
    fields = {keyword.arg for keyword in calls[0].keywords} - {"user_id", "memory_id"}
    assert fields == set(MemoryCreate.model_fields)
    assert not fields & {"embedding", "keyword_embedding", "context_biometric", "pinned", "user_id"}
