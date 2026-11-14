"""Where a search across discussions resumes: an opaque position, refused when damaged.

A search page spans every discussion of the account, so its position names no
discussion and no generation — only the last message served. Anything else a
client sends back is refused, never guessed (the history cursor's rule).
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.exceptions import ValidationError
from src.domains.conversations.history_cursor import (
    encode_history_cursor,
    encode_search_cursor,
    search_position,
)
from src.infrastructure.database.keyset import Keyset

pytestmark = pytest.mark.unit

_AT = datetime(2026, 11, 13, 8, 30, tzinfo=UTC)


def _raw(payload: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def test_a_position_comes_back_as_the_keyset_it_was_made_from() -> None:
    message_id = uuid4()

    assert search_position(encode_search_cursor(_AT, message_id)) == Keyset(at=_AT, id=message_id)


def test_no_cursor_is_the_newest_page() -> None:
    assert search_position(None) is None


@pytest.mark.parametrize(
    "cursor",
    [
        pytest.param("", id="empty"),
        pytest.param("%%%", id="not base64"),
        pytest.param(_raw({"version": 1, "at": "2026-11-13T08:30:00"}), id="no message"),
        pytest.param(
            _raw({"version": 1, "at": "2026-11-13T08:30:00", "message_id": str(uuid4())}),
            id="naive instant",
        ),
        pytest.param(
            _raw({"version": 2, "at": "2026-11-13T08:30:00Z", "message_id": str(uuid4())}),
            id="unknown version",
        ),
        pytest.param(
            _raw({"version": True, "at": "2026-11-13T08:30:00Z", "message_id": str(uuid4())}),
            id="boolean version",
        ),
        pytest.param("A" * 4096, id="too long"),
    ],
)
def test_a_damaged_position_is_refused_never_guessed(cursor: str) -> None:
    with pytest.raises(ValidationError):
        search_position(cursor)


def test_a_discussion_s_history_cursor_is_no_search_position() -> None:
    history = encode_history_cursor(
        ConversationRef(
            owner_id=uuid4(),
            id=uuid4(),
            kind=ConversationKind.MAIN,
            revision=0,
            runtime_id=uuid4(),
        ),
        _AT,
        uuid4(),
    )

    with pytest.raises(ValidationError):
        search_position(history)
