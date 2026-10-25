"""The relationship timeline's cursor and keyset (owner request 2026-10-24).

A merged timeline orders by (instant, kind, id) newest first; its cursor is the
last record served, and each source resumes strictly after it. These pin the
two halves an in-memory test can prove: the cursor is opaque and refuses a
forgery, and each source's resumption matches the merged order.
"""

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.exceptions import BaseAPIException
from src.domains.relations.schemas import RelationCall, RelationTimelineItem
from src.domains.relations.timeline import TIMELINE_KINDS, decode_cursor, encode_cursor
from src.infrastructure.database.keyset import Keyset

pytestmark = pytest.mark.unit

AT = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)


def test_a_cursor_reads_back_what_it_wrote() -> None:
    call_id = uuid4()
    item = RelationTimelineItem(
        kind="call",
        at=AT,
        call=RelationCall(id=str(call_id), objective="o", created_at=AT),
    )
    assert decode_cursor(encode_cursor(item)) == (AT, "call", call_id)


@pytest.mark.parametrize(
    "token",
    ["", "not-base64!", "WyJ4Il0", "WyIyMDI2LTEwLTIwVDA5OjMwOjAwIiwgImNhbGwiLCAieCJd"],
    ids=["empty", "garbage", "short", "naive-instant-and-bad-id"],
)
def test_a_forged_cursor_is_refused_never_guessed(token: str) -> None:
    with pytest.raises((BaseAPIException, HTTPException)) as refused:
        decode_cursor(token)
    assert refused.value.status_code == 400


def _forge(value: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "value",
    [
        [AT.isoformat(), "call", 5],
        [1_760_000_000, "call", str(uuid4())],
        [AT.isoformat(), "letter", str(uuid4())],
        [AT.isoformat(), ["call"], str(uuid4())],
        {"at": AT.isoformat(), "kind": "call", "id": str(uuid4())},
    ],
    ids=["numeric-id", "numeric-instant", "unknown-kind", "listed-kind", "object"],
)
def test_a_well_formed_but_mistyped_cursor_is_a_400_never_a_500(value: object) -> None:
    """Valid base64 and valid JSON are not a cursor: every field is checked."""
    with pytest.raises((BaseAPIException, HTTPException)) as refused:
        decode_cursor(_forge(value))
    assert refused.value.status_code == 400


def test_each_source_resumes_where_the_merged_order_does() -> None:
    cursor_id = uuid4()
    # The same kind continues by id at the cursor's instant.
    assert Keyset.after("memory", AT, "memory", cursor_id) == Keyset(at=AT, id=cursor_id)
    # An EARLIER kind sorts after the cursor at the same instant: still to serve.
    assert Keyset.after("call", AT, "memory", cursor_id) == Keyset(at=AT, inclusive=True)
    # A LATER kind at that instant was served before it.
    assert Keyset.after("sms", AT, "memory", cursor_id) == Keyset(at=AT, inclusive=False)


def test_the_tie_break_order_is_the_declared_one() -> None:
    assert list(TIMELINE_KINDS) == sorted(TIMELINE_KINDS)
