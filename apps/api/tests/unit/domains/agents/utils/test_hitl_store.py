"""HITL read contracts; atomic writes and races are proven on real Redis in integration."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.conversation_execution import ExecutionRevoked
from src.domains.agents.utils.hitl_store import SCHEMA_VERSION, HITLStore, HitlStoreClient

pytestmark = pytest.mark.unit


def store_with(raw: str | bytes | None) -> tuple[HITLStore, AsyncMock]:
    """Only model the read boundary; this double never grants runtime authority."""
    client = AsyncMock(spec=HitlStoreClient)
    client.get = AsyncMock(return_value=raw)
    client.set = AsyncMock()
    client.delete = AsyncMock()
    client.eval = AsyncMock()
    client.exists = AsyncMock()
    return HITLStore(client, 3600), client


async def test_absent_question_is_distinct_from_a_malformed_one() -> None:
    store, _ = store_with(None)
    assert await store.get_pending(str(uuid4())) is None


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "null",
        "[]",
        "false",
        '"text"',
        b"\xff",
        '{"schema_version":true,"interrupt_data":{}}',
        '{"schema_version":2,"interrupt_data":{}}',
        '{"schema_version":1}',
        '{"schema_version":1,"interrupt_data":null}',
        '{"action_requests":"invalid"}',
        '{"action_requests":["invalid"]}',
    ],
)
async def test_malformed_record_refuses_instead_of_silently_starting_a_new_turn(
    raw: str | bytes,
) -> None:
    store, client = store_with(raw)
    with pytest.raises((ValueError, UnicodeError)):
        await store.get_pending(str(uuid4()))
    client.set.assert_not_awaited()
    client.delete.assert_not_awaited()
    client.eval.assert_not_awaited()


@pytest.mark.parametrize("legacy", [True, False])
async def test_legacy_and_current_records_share_the_same_read_shape_without_writing(
    legacy: bool,
) -> None:
    payload = {
        "run_id": "original-billing-run",
        "action_requests": [{"name": "ask", "args": {}}],
        "generated_question": "Already shown question",
        "message_id": "question-id",
    }
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "interrupt_ts": "2026-11-10T00:00:00Z",
        "interrupt_data": payload,
    }
    store, client = store_with(json.dumps(payload if legacy else envelope))
    assert await store.get_pending(str(uuid4())) == {
        **payload,
        "interrupt_ts": None if legacy else envelope["interrupt_ts"],
    }
    client.set.assert_not_awaited()
    client.eval.assert_not_awaited()


async def test_read_failure_is_not_an_empty_question() -> None:
    store, client = store_with(None)
    client.get.side_effect = ConnectionError("Test cache unavailable")
    with pytest.raises(ConnectionError):
        await store.get_pending(str(uuid4()))


async def test_write_and_unconditional_delete_require_a_graph_owner() -> None:
    store, client = store_with(None)
    runtime = str(uuid4())
    with pytest.raises(ExecutionRevoked):
        await store.save_interrupt(runtime, {"run_id": "run", "action_requests": []})
    with pytest.raises(ExecutionRevoked):
        await store.delete_interrupt(runtime)
    client.set.assert_not_awaited()
    client.delete.assert_not_awaited()
    client.eval.assert_not_awaited()


@pytest.mark.parametrize("count,expected", [(0, False), (1, True)])
async def test_presence_probe_stays_conservative(count: int, expected: bool) -> None:
    store, client = store_with(None)
    client.exists.return_value = count
    assert await store.has_interrupt(str(uuid4())) is expected


async def test_unreadable_bytes_are_kept_by_opportunistic_cleanup() -> None:
    store, client = store_with(b"\xff")
    assert not await store.clear_if_invalid(str(uuid4()))
    client.eval.assert_not_awaited()
