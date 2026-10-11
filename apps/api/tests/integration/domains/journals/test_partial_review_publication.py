"""Partial semantic approval publishes only unchanged approved source-only facets."""

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.journals import billing
from src.domains.journals import consolidation_lifecycle as lifecycle
from src.domains.journals import consolidation_service as consolidation
from src.domains.journals.consolidation_output import parse_maintenance_output
from src.domains.journals.models import JournalEntry
from src.domains.journals.portrait_catalogue import eligible_source_items
from src.domains.journals.portrait_review import prepare_portrait_review
from src.domains.journals.portrait_sources import PortraitSourceBundle
from src.domains.journals.source_state import portrait_source_state
from src.domains.memories import portrait_source as memory_source
from src.domains.memories.models import Memory
from src.domains.shared import portrait_sources
from src.domains.shared.portrait_sources import SourceBudget
from src.infrastructure.llm import token_capture
from tests.integration.domains.journals.test_consolidation_integrity import (
    _review_payload,
    _user,
)
from tests.integration.domains.journals.test_consolidation_integrity import (
    isolated_runtime as isolated_runtime,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
APPROVED = (0, 1, 2, 5)
DOMAINS = ("courriels", "calendrier", "réunions", "trajet", "budget", "dossiers", "décisions")


async def _seed_case(db, monkeypatch):
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 1000)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 1000)
    allowed = AsyncMock(return_value=True)
    monkeypatch.setattr(memory_source, "_allowed", allowed)
    monkeypatch.setattr(
        portrait_sources,
        "_REGISTRY",
        {
            "memories": (
                memory_source.read_memories,
                replace(memory_source.FRESHNESS, allowed=allowed),
            )
        },
    )

    @asynccontextmanager
    async def context():
        yield db

    monkeypatch.setattr(memory_source, "get_db_context", context)
    user = await _user(db)
    rows = [
        Memory(
            user_id=user.id,
            category="preference",
            content=f"Quand une demande urgente porte sur les {domain}, je demande une prochaine action concrète.",
        )
        for domain in DOMAINS
    ]
    db.add_all(rows)
    await db.commit()
    section = await memory_source.read_memories(
        user_id=user.id, language="fr", budget=SourceBudget(40, 200)
    )
    assert section.status == "used" and section.used == 7
    items = eligible_source_items("memories", section.text)
    assert len(items) == 7
    supports = [next(item for item in items if row.content in item.quote) for row in rows]
    sources = PortraitSourceBundle(
        sections={
            **dict.fromkeys(portrait_sources.PORTRAIT_SOURCE_KEYS, ""),
            "memories": section.text,
        },
        provenance={
            "version": 1,
            "journal_entries": 0,
            "sources": {"memories": {"status": "used", "used": 7, "total": 7}},
        },
    )
    payload = {
        "actions": [],
        "portrait_claims": [
            {
                "facet": "interaction",
                "text": f"Quand une demande urgente porte sur les {domain}, je retiens son attente d'une prochaine action concrète.",
                "supports": [{"source": "memories", "item_id": item.item_id}],
                "in_brief": True,
            }
            for domain, item in zip(DOMAINS, supports, strict=True)
        ],
    }
    monkeypatch.setattr(
        consolidation, "build_portrait_source_sections", AsyncMock(return_value=sources)
    )
    user.journal_revision = 4
    user.journal_consolidated_revision = 3
    user.journal_portrait_full = "Earlier approved full portrait."
    user.journal_portrait_brief = "Earlier approved brief portrait."
    previous_at = datetime.now(UTC) - timedelta(days=2)
    user.journal_portrait_compiled_at = previous_at
    user.journal_last_consolidated_at = previous_at
    user.journal_portrait_sources = {
        "journal_revision": 4,
        "source_state": await portrait_source_state(db, user),
    }
    await db.commit()
    return SimpleNamespace(
        db=db, user=user, rows=rows, sources=sources, payload=payload, previous_at=previous_at
    )


def _model_phases(monkeypatch, case, *, mode="partial", on_review=None):
    billed = []

    def price(**kwargs):
        usd = (kwargs["prompt_tokens"] + kwargs["completion_tokens"]) / 1000
        return usd, usd / 2

    monkeypatch.setattr(token_capture, "get_cached_cost_usd_eur", price)
    monkeypatch.setattr(token_capture, "get_cached_usd_eur_rate", lambda *_: 0.5)

    async def persist(**kwargs):
        records = kwargs["capture"].claim_billing_records(kwargs["model_name"])
        billed.append((kwargs, records))

    monkeypatch.setattr(consolidation, "_persist_journal_tokens", AsyncMock(side_effect=persist))
    monkeypatch.setattr(
        consolidation, "_update_user_last_cost", AsyncMock(wraps=billing._update_user_last_cost)
    )

    async def answer(**kwargs):
        review = _review_payload(kwargs["messages"])
        if review is None:
            content, tokens_in, tokens_out = case.payload, 11, 7
        else:
            assert len(review["facets"]) == 7
            if on_review is not None:
                await on_review()
            verdicts = [
                {
                    "index": facet["index"],
                    "supported": mode != "all_refused" and facet["index"] not in (4, 6),
                    "scope_preserved": facet["index"] != 3,
                    "uncertainty_preserved": True,
                    "synthesized": True,
                }
                for facet in review["facets"]
            ]
            content = "{" if mode == "malformed" else {"reviews": verdicts}
            tokens_in, tokens_out = 5, 3
        return AIMessage(
            content=content if isinstance(content, str) else json.dumps(content),
            usage_metadata={
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "total_tokens": tokens_in + tokens_out,
            },
            response_metadata={"model_name": "returned-offline"},
        )

    invoke = AsyncMock(side_effect=answer)
    monkeypatch.setattr(consolidation, "invoke_with_instrumentation", invoke)
    return invoke, billed


async def _run(case):
    attempt = lifecycle.ConsolidationAttempt()
    result = await consolidation.consolidate_journals_for_user(
        case.user.id, None, None, "fr", manual=True, attempt=attempt
    )
    assert result == 0  # Portrait-only publication never backfills the journal.
    await case.db.refresh(case.user)
    return attempt


async def _assert_billing_and_no_journal(case, invoke, billed):
    assert invoke.await_count == 2
    assert len(billed) == 2 and [len(records) for _, records in billed] == [1, 1]
    first, second = (records[0] for _, records in billed)
    assert (first.tokens_in, first.tokens_out) == (11, 7)
    assert (second.tokens_in, second.tokens_out) == (5, 3)
    assert first.model_name == second.model_name == "returned-offline"
    assert first.cost_eur == pytest.approx(0.009)
    assert second.cost_eur == pytest.approx(0.004)
    assert billed[0][0]["parent_run_id"] == billed[1][0]["parent_run_id"]
    assert billed[0][0]["capture"] is billed[1][0]["capture"]
    assert billed[0][0]["capture"].claim_billing_records("returned-offline") == ()
    assert float(case.user.journal_last_cost_eur) == pytest.approx(0.013)
    assert case.user.journal_last_cost_tokens_in == 16
    assert case.user.journal_last_cost_tokens_out == 10
    assert case.user.journal_last_cost_source == "consolidation"
    assert (
        await case.db.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(JournalEntry.user_id == case.user.id)
        )
        == 0
    )
    assert case.user.journal_revision == 4


async def test_seven_source_only_facets_publish_exact_four_approved_facets_and_proofs(
    isolated_runtime, monkeypatch
):
    case = await _seed_case(isolated_runtime, monkeypatch)
    invoke, billed = _model_phases(monkeypatch, case)
    attempt = await _run(case)
    await _assert_billing_and_no_journal(case, invoke, billed)
    expected = "\n\n".join(case.payload["portrait_claims"][i]["text"] for i in APPROVED)
    assert case.user.journal_portrait_full == expected
    assert case.user.journal_portrait_brief == expected
    assert attempt.status == case.user.journal_last_attempt_status == "success"
    assert case.user.journal_consolidated_revision == 4
    assert case.user.journal_last_consolidated_at > case.previous_at
    assert case.user.journal_consolidation_owner is None
    stored = case.user.journal_portrait_sources
    assert [claim["text"] for claim in stored["claims"]] == [
        case.payload["portrait_claims"][i]["text"] for i in APPROVED
    ]
    for claim, index in zip(stored["claims"], APPROVED, strict=True):
        row = case.rows[index]
        assert len(claim["supports"]) == 1
        assert claim["supports"][0]["source"] == "memories"
        assert row.content in claim["supports"][0]["quote"]
        assert "item_id" not in claim["supports"][0]
    approved = parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": stored["claims"]})
    )
    candidate = prepare_portrait_review(approved, [], case.sources)
    assert stored["portrait_review"]["digest"] == candidate.digest
    original = prepare_portrait_review(
        parse_maintenance_output(json.dumps(case.payload)), [], case.sources
    )
    assert original.digest != candidate.digest
    assert stored["portrait_review"]["reviewed_digest"] == original.digest
    assert stored["portrait_review"]["approved_indices"] == list(APPROVED)
    assert stored["portrait_review"]["rejected"] == [
        {"claim_index": 3, "criteria": ["scope_preserved"]},
        {"claim_index": 4, "criteria": ["supported"]},
        {"claim_index": 6, "criteria": ["supported"]},
    ]
    assert stored["portrait_pending"] is False
    assert consolidation._file_consolidation.await_args.kwargs["failed"] is False


@pytest.mark.parametrize("mode", ["all_refused", "malformed"])
async def test_refused_or_malformed_review_preserves_prior_words_and_success_watermark(
    isolated_runtime, monkeypatch, mode
):
    case = await _seed_case(isolated_runtime, monkeypatch)
    invoke, billed = _model_phases(monkeypatch, case, mode=mode)
    attempt = await _run(case)
    await _assert_billing_and_no_journal(case, invoke, billed)
    assert case.user.journal_portrait_full == "Earlier approved full portrait."
    assert case.user.journal_portrait_brief == "Earlier approved brief portrait."
    assert case.user.journal_portrait_compiled_at == case.previous_at
    assert case.user.journal_last_consolidated_at == case.previous_at
    assert case.user.journal_consolidated_revision == 3
    assert attempt.status == "invalid_output"
    assert case.user.journal_consolidation_owner is None
    assert consolidation._file_consolidation.await_args.kwargs["failed"] is True


@pytest.mark.parametrize("changed", ["source", "consent"])
async def test_late_change_rejects_even_a_partly_approved_source_only_portrait(
    isolated_runtime, monkeypatch, changed
):
    case = await _seed_case(isolated_runtime, monkeypatch)

    async def mutate():
        if changed == "source":
            case.rows[0].content = "A changed source proposition after review began."
        else:
            case.user.journals_enabled = False
            case.user.extraction_revision += 1
        await case.db.commit()

    invoke, billed = _model_phases(monkeypatch, case, on_review=mutate)
    attempt = await _run(case)
    await _assert_billing_and_no_journal(case, invoke, billed)
    assert attempt.status == "stale"
    assert case.user.journal_portrait_full == "Earlier approved full portrait."
    assert case.user.journal_portrait_brief == "Earlier approved brief portrait."
    assert case.user.journal_last_consolidated_at == case.previous_at
    assert case.user.journal_consolidated_revision == 3
    assert case.user.journal_consolidation_owner is None
    assert consolidation._file_consolidation.await_args.kwargs["failed"] is True
