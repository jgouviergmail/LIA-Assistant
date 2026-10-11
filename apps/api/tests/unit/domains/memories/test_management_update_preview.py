"""Shared edit preview preserves omitted values, source constraints and explicit zeros."""

import ast
import inspect
import textwrap

import pytest

from src.domains.memories.models import Memory
from src.domains.memories.schemas import MemoryCreate, MemoryUpdate
from src.domains.memories.service import MemoryService, preview_memory_update

pytestmark = pytest.mark.unit


def test_new_ui_fields_cannot_be_omitted_from_preview_or_source_write() -> None:
    tree = ast.parse(inspect.getsource(preview_memory_update))
    projections = [node for node in ast.walk(tree) if isinstance(node, ast.Dict)]
    assert len(projections) == 1
    fields = {node.value for node in projections[0].keys if isinstance(node, ast.Constant)}
    assert fields == set(MemoryCreate.model_fields) == set(MemoryUpdate.model_fields)
    method = ast.parse(textwrap.dedent(inspect.getsource(MemoryService.update_from_management)))
    writes = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update_memory"
    ]
    assert len(writes) == 1
    assert {keyword.arg for keyword in writes[0].keywords} == fields


def test_sparse_preview_is_pure_and_preserves_source_clear_and_zero_semantics() -> None:
    row = Memory(
        content="Existing fact",
        category="personal",
        emotional_weight=4,
        trigger_topic="old topic",
        usage_nuance="Keep this nuance",
        importance=0.8,
        pinned=True,
        char_count=13,
    )
    changes = MemoryUpdate(importance=0.0, emotional_weight=0, trigger_topic="")
    desired = preview_memory_update(row, changes)
    assert desired.content == row.content and desired.usage_nuance == row.usage_nuance
    assert (
        desired.importance == 0.0 and desired.emotional_weight == 0 and desired.trigger_topic == ""
    )
    assert row.importance == 0.8 and row.trigger_topic == "old topic" and row.pinned is True


def test_source_explicit_null_remains_an_omitted_delta_in_shared_preview() -> None:
    row = Memory(
        content="Existing fact",
        category="procedural",
        emotional_weight=0,
        trigger_topic="topic",
        usage_nuance="Nuance",
        importance=0.7,
        pinned=True,
    )
    assert preview_memory_update(row, MemoryUpdate(content=None)).content == row.content
