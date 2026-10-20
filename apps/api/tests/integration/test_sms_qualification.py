"""Reproducible bounded qualification; emits measurements, no timing ratchet."""

import json
from pathlib import Path
from time import perf_counter

import pytest
from sqlalchemy import func, select, text

from src.domains.ingestion.key_material import key_for_owner
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.sms.search import blind_digest
from src.infrastructure.observability.process_memory import read_resident_memory
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_blind_index_qualification_on_repeated_unicode_messages(db_session, test_user):
    actor = await authority(db_session, test_user)
    service = SmsIngestionService(db_session)
    baseline = read_resident_memory()
    peak = sum((baseline.anon, baseline.file, baseline.shmem)) if baseline else 0
    started = perf_counter()
    count = 2000
    for offset in range(0, count, 50):
        entries = [
            message(body=f"Café demain 東京 明天下午 déjeuner archive uniqueterm{index}")
            for index in range(offset, offset + 50)
        ]
        result = await service.ingest(actor, entries)
        assert result.inserted == 50
        memory = read_resident_memory()
        if memory:
            peak = max(peak, sum((memory.anon, memory.file, memory.shmem)))
    elapsed = perf_counter() - started
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == count
    indexed = await db_session.scalar(select(func.sum(func.cardinality(SmsSearchTerm.term_hashes))))
    key = key_for_owner(test_user)
    await db_session.execute(text("ANALYZE sms_search_terms"))
    probes = {}
    for label, term in (("rare", "uniqueterm1999"), ("common", "cafe"), ("cjk", "東京")):
        digest = blind_digest(test_user.id, "term", term, key=key)
        query = text(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT message_id FROM sms_search_terms WHERE user_id = :owner AND term_hashes @> ARRAY[decode(:term, 'hex')] ORDER BY message_id LIMIT 21"
        )
        raw = (
            await db_session.execute(query, {"owner": test_user.id, "term": digest})
        ).scalar_one()
        plan = json.loads(raw) if isinstance(raw, str) else raw
        probes[label] = {
            "execution_ms": plan[0]["Execution Time"],
            "node": plan[0]["Plan"]["Node Type"],
        }
    size = await db_session.scalar(text("SELECT pg_total_relation_size('sms_search_terms')"))
    baseline_rss = sum((baseline.anon, baseline.file, baseline.shmem)) if baseline else 0
    report = {
        "messages": count,
        "index_terms": indexed,
        "index_rows": count,
        "index_bytes": size,
        "ingestion_seconds": round(elapsed, 3),
        "peak_rss_delta_bytes": peak - baseline_rss,
        "queries": probes,
    }
    destination = (
        Path(__file__).resolve().parents[4] / ".tmp/sms-implementation/index-qualification.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
