"""A memory's text bounds: enforced at every door, published to every producer.

Measured in production on 2026-11-06: the extractor wrote a 495-character memory, its
owner added a few words in the settings form, and every save answered a generic
error, five times in a row. ``content`` was refused for its length by a bound nothing
had published: not to the form, which showed no limit and threw the reason away, and
not to the extractor, the one writer that did not even enforce it.

The bound is one fact. These tests hold it at each door, and hold the read side to the
opposite rule: what the database holds is shown, whatever the bound says today.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from src.core.config import settings
from src.core.constants import (
    MEMORY_CONTENT_MIN_CHARS,
    MEMORY_TRIGGER_TOPIC_MAX_CHARS,
    MEMORY_USAGE_NUANCE_MAX_CHARS,
)
from src.domains.memories.models import Memory
from src.domains.memories.read_models import memory_to_response
from src.domains.memories.schemas import (
    ExtractedMemory,
    MemoryCreate,
    MemoryLimits,
    MemoryListResponse,
    MemoryUpdate,
)

pytestmark = pytest.mark.unit

#: Every door a memory's text enters through, with the fields it needs beside the text.
WRITE_DOORS: list[tuple[type[BaseModel], dict[str, Any]]] = [
    (MemoryCreate, {"content": "A valid fact", "category": "personal"}),
    (MemoryUpdate, {}),
    (ExtractedMemory, {"content": "A valid fact", "category": "personal"}),
]
DOOR_IDS = [door.__name__ for door, _ in WRITE_DOORS]


def _refusal_type(door: type[BaseModel], fields: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as refused:
        door(**fields)
    return str(refused.value.errors()[0]["type"])


@pytest.mark.parametrize(("door", "base"), WRITE_DOORS, ids=DOOR_IDS)
def test_every_door_accepts_a_content_at_the_published_ceiling(
    door: type[BaseModel], base: dict[str, Any]
) -> None:
    ceiling = MemoryLimits().content_max_chars
    assert len(door(**{**base, "content": "x" * ceiling}).content) == ceiling  # type: ignore[attr-defined]


@pytest.mark.parametrize(("door", "base"), WRITE_DOORS, ids=DOOR_IDS)
def test_every_door_refuses_a_content_past_the_published_ceiling(
    door: type[BaseModel], base: dict[str, Any]
) -> None:
    past = "x" * (MemoryLimits().content_max_chars + 1)
    assert _refusal_type(door, {**base, "content": past}) == "string_too_long"


@pytest.mark.parametrize(("door", "base"), WRITE_DOORS, ids=DOOR_IDS)
def test_every_door_refuses_a_content_under_the_published_floor(
    door: type[BaseModel], base: dict[str, Any]
) -> None:
    under = "x" * (MemoryLimits().content_min_chars - 1)
    assert _refusal_type(door, {**base, "content": under}) == "string_too_short"


@pytest.mark.parametrize(("door", "base"), WRITE_DOORS, ids=DOOR_IDS)
@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("trigger_topic", "trigger_topic_max_chars"),
        ("usage_nuance", "usage_nuance_max_chars"),
    ],
)
def test_every_door_holds_the_published_ceiling_of_the_short_texts(
    door: type[BaseModel], base: dict[str, Any], field: str, limit: str
) -> None:
    ceiling = getattr(MemoryLimits(), limit)
    assert getattr(door(**{**base, field: "x" * ceiling}), field) == "x" * ceiling
    assert _refusal_type(door, {**base, field: "x" * (ceiling + 1)}) == "string_too_long"


def test_a_bound_counts_characters_not_utf16_units() -> None:
    """The form counts what this counts: an emoji is one, whatever `String.length` says."""
    ceiling = MemoryLimits().content_max_chars
    emoji = "\N{GRINNING FACE}"
    assert MemoryUpdate(content=emoji * ceiling).content == emoji * ceiling
    assert _refusal_type(MemoryUpdate, {"content": emoji * (ceiling + 1)}) == "string_too_long"


@pytest.mark.parametrize("echoed", ["", "ok", "x" * (settings.memory_content_max_chars + 1)])
def test_a_delete_is_never_refused_for_a_text_it_does_not_read(echoed: str) -> None:
    action = ExtractedMemory(action="delete", memory_id="m1", content=echoed)
    assert action.action == "delete" and action.content is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_an_update_with_a_blank_content_keeps_its_text_and_its_other_fields(blank: str) -> None:
    """A blank content wrote an EMPTY successor: the fact was gone, and the list with it."""
    action = ExtractedMemory(action="update", memory_id="m1", content=blank, category="procedural")
    assert action.content is None and action.category == "procedural"


def test_a_create_with_a_blank_content_is_still_refused() -> None:
    assert _refusal_type(ExtractedMemory, {"content": "", "category": "personal"}) == (
        "string_too_short"
    )


def test_the_limits_are_the_declared_values() -> None:
    limits = MemoryLimits()
    assert limits.content_min_chars == MEMORY_CONTENT_MIN_CHARS
    assert limits.content_max_chars == settings.memory_content_max_chars
    assert limits.trigger_topic_max_chars == MEMORY_TRIGGER_TOPIC_MAX_CHARS
    assert limits.usage_nuance_max_chars == MEMORY_USAGE_NUANCE_MAX_CHARS


def test_the_list_publishes_the_limits_to_the_form_that_fills_a_memory() -> None:
    assert MemoryListResponse().model_dump(mode="json")["limits"] == MemoryLimits().model_dump()


def test_a_short_text_ceiling_is_the_width_of_its_column() -> None:
    columns = Memory.__table__.columns
    assert columns["trigger_topic"].type.length == MEMORY_TRIGGER_TOPIC_MAX_CHARS
    assert columns["usage_nuance"].type.length == MEMORY_USAGE_NUANCE_MAX_CHARS


def _stored(content: str) -> Memory:
    now = datetime.now(UTC)
    return Memory(
        id=uuid4(),
        user_id=uuid4(),
        content=content,
        category="personal",
        importance=0.7,
        pinned=False,
        emotional_weight=0,
        usage_count=0,
        trigger_topic="",
        usage_nuance="",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    "length",
    [settings.memory_content_max_chars + 1, MEMORY_CONTENT_MIN_CHARS - 1],
    ids=["past_the_ceiling", "under_the_floor"],
)
def test_a_stored_row_outside_the_bounds_stays_readable(length: int) -> None:
    """A write bound never refuses a READ: one such row would take the whole list down.

    The list, the export and the assistant's reads all project through this, so a
    refusal here is a screen nobody can open, and a memory nobody can delete from it.
    A row can get there: an operator lowering ``MEMORY_CONTENT_MAX_CHARS`` leaves
    every longer memory behind.
    """
    assert len(memory_to_response(_stored("x" * length)).content) == length
