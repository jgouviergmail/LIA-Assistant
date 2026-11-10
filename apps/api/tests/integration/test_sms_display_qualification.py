"""Measure the native reader at the configured archive ceiling on disposable PostgreSQL."""

import json
import random
import string
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.sms.display_reads import SmsDisplayReader
from src.domains.sms.display_schemas import SmsDisplayQuery
from src.domains.sms.identity import IdentityBook
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.users.models import User
from tests.integration.test_sms_ingestion import authority, message

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.usefixtures("sms_identity_session"),
]

# Replicate a REAL admitted/encrypted/indexed row inside PostgreSQL; identifiers
# and receipts stay unique. This measures archive reads, not ingestion throughput.
_CLONE = text("""
WITH ids AS MATERIALIZED (
 SELECT gen_random_uuid() AS mid, gen_random_uuid() AS rid FROM generate_series(1, :amount)
), receipts AS (
 INSERT INTO ingestion_receipts (id, user_id, source_id, event_key, payload_hash, verdict, filter_version, created_at, updated_at)
 SELECT ids.rid, seed.user_id, seed.source_id, ids.rid::text, seed.payload_hash, seed.verdict, seed.filter_version, now(), now()
 FROM ids CROSS JOIN ingestion_receipts seed WHERE seed.id = :receipt
 RETURNING id
), messages AS (
 INSERT INTO sms_messages (id, user_id, receipt_id, sender_encrypted, sender_hash, body_encrypted, origin, received_at, date_kind, logical_bytes, search_complete, created_at, updated_at)
 SELECT ids.mid, seed.user_id, ids.rid, seed.sender_encrypted, seed.sender_hash, seed.body_encrypted, seed.origin, :received, seed.date_kind, seed.logical_bytes, seed.search_complete, now(), now()
 FROM ids JOIN receipts ON receipts.id = ids.rid CROSS JOIN sms_messages seed WHERE seed.id = :message
 RETURNING id
)
INSERT INTO sms_search_terms (id, user_id, message_id, term_hashes, index_version, display_hashes, display_version, display_complete, created_at, updated_at)
SELECT gen_random_uuid(), seed.user_id, messages.id, seed.term_hashes, seed.index_version, seed.display_hashes, seed.display_version, seed.display_complete, now(), now()
FROM messages CROSS JOIN sms_search_terms seed WHERE seed.message_id = :message
""")


async def test_exact_name_pages_and_honest_body_bounds_at_archive_ceiling(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "src.domains.sms.identity_resolution.load_identity_book",
        AsyncMock(return_value=IdentityBook(complete=True)),
    )
    rng = random.Random(1909)
    body = (
        "Café facture 東京 "
        + " ".join(
            "".join(rng.choices(string.ascii_letters, k=10))
            for _ in range(settings.sms_max_body_chars)
        )
    )[: settings.sms_max_body_chars]
    actor = await authority(db_session, test_user)
    original = datetime.now(UTC) - timedelta(days=1)
    payload = message(sender="Archive Sender", body=body, date=original.isoformat())
    result = await SmsIngestionService(db_session).ingest(actor, [payload])
    assert result.inserted == 1
    row = await db_session.get(SmsMessage, result.items[0].message_id)
    assert row is not None
    count = settings.sms_archive_max_logical_bytes // row.logical_bytes
    assert count > settings.sms_search_max_candidates
    started = perf_counter()
    for offset in range(1, count, settings.sms_search_max_candidates):
        await db_session.execute(
            _CLONE,
            {
                "amount": min(count - offset, settings.sms_search_max_candidates),
                "message": row.id,
                "receipt": row.receipt_id,
                "received": original - timedelta(days=1),
            },
        )
    await db_session.commit()
    fill_seconds = perf_counter() - started
    occupied = await db_session.scalar(
        select(func.sum(SmsMessage.logical_bytes)).where(SmsMessage.user_id == test_user.id)
    )
    assert occupied == count * row.logical_bytes
    assert (
        await SmsIngestionService(db_session).ingest(
            actor, [message(sender="Archive Sender", body=body)]
        )
    ).items[0].verdict == "storage_full"
    reader = SmsDisplayReader(db_session)
    tracemalloc.start()
    started = perf_counter()
    try:
        page = await reader.list(
            test_user.id, SmsDisplayQuery(query="archive sender", sort="name", limit=10)
        )
        _, python_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    name_seconds = perf_counter() - started
    assert page.total == count and len(page.items) == 10 and page.next_cursor
    later = await reader.list(
        test_user.id,
        SmsDisplayQuery(query="archive sender", sort="name", limit=10, cursor=page.next_cursor),
    )
    assert not ({item.id for item in page.items} & {item.id for item in later.items})
    with pytest.raises(ResourceConflictError, match="QUERY_TOO_BROAD"):
        await reader.list(test_user.id, SmsDisplayQuery(query="fact"))
    narrowed = await reader.list(test_user.id, SmsDisplayQuery(query="fact", from_ts=original))
    assert narrowed.total == 1 and narrowed.items[0].body == body
    physical = await db_session.scalar(text("SELECT pg_total_relation_size('sms_search_terms')"))
    incomplete = await db_session.scalar(
        select(func.count())
        .select_from(SmsSearchTerm)
        .where(SmsSearchTerm.display_complete.is_(False))
    )
    plan = (
        await db_session.execute(
            text(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT count(*) FROM sms_messages WHERE user_id = :owner"
            ),
            {"owner": test_user.id},
        )
    ).scalar_one()
    report = {
        "messages": count,
        "logical_bytes": int(occupied),
        "ceiling": settings.sms_archive_max_logical_bytes,
        "projection_physical_bytes": physical,
        "incomplete_projections": incomplete,
        "bulk_fill_seconds": fill_seconds,
        "name_page_seconds": name_seconds,
        "name_page_traced_python_peak_bytes": python_peak,
        "count_plan": plan,
    }
    destination = tmp_path / "sms-display-qualification.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
