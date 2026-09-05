"""Verifying one account's chain against the database (ADR-263, lot 5).

Two depths, and the difference between them matters:

- **shallow** reads the chain alone. It answers « was an ENTRY rewritten,
  deleted or re-rooted » and costs one indexed scan.
- **deep** also re-digests every covered row. It answers the question the
  chain exists for — « was a REGISTER ROW rewritten or deleted » — and is the
  only depth that detects a silent ``UPDATE agent_effects SET label = …``.

A shallow pass alone would be a chain that verifies itself and nothing else.

One honesty rule is enforced here rather than assumed: an entry written under
an older ``digest_version`` is **not** deep-checked, and the count says so.
Recomputing it with today's encoding would report a break that never happened —
an audit device whose false positives train an operator to ignore it is worse
than none.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.effects.chain_digest import DIGEST_VERSION
from src.domains.agents.effects.chain_link import ChainBreak, ChainLink, ChainVerdict, walk
from src.domains.agents.effects.chain_repository import ChainRepository
from src.domains.agents.effects.chain_spec import CHAIN_SUBJECTS, ChainSubject, digest_of
from src.domains.agents.effects.models import AgentEffect, AgentTreatment
from src.infrastructure.observability.metrics_effects import ledger_chain_breaks_total

_BY_KIND: dict[str, ChainSubject] = {subject.kind: subject for subject in CHAIN_SUBJECTS}
_MODELS: dict[str, Any] = {"AgentEffect": AgentEffect, "AgentTreatment": AgentTreatment}


@dataclass(frozen=True)
class ChainAudit:
    """What a verification concluded about one account.

    Attributes:
        ok: Whether everything checked held.
        entries: Links walked before stopping.
        payloads_checked: Covered rows re-digested — 0 in shallow mode.
        payloads_skipped: Entries written under a superseded encoding, which
            deep mode declines to judge rather than judge wrongly.
        broken_at_seq: Where it stopped, when it did.
        reason: What failed there.
        head_hash: The chain's last hash when it holds — what an operator
            writes down to detect a later rewrite of the chain AND its rows.
        deep: Whether payloads were checked at all.
    """

    ok: bool
    entries: int
    payloads_checked: int = 0
    payloads_skipped: int = 0
    broken_at_seq: int | None = None
    reason: ChainBreak | None = None
    head_hash: str | None = None
    deep: bool = False


async def verify_chain(db: AsyncSession, user_id: uuid.UUID, *, deep: bool = False) -> ChainAudit:
    """Walk an account's chain, page by page, and report the first break.

    Args:
        db: The session.
        user_id: Whose chain.
        deep: Also re-digest every covered row.

    Returns:
        The audit. An account with no chain verifies OK with zero entries —
        it has done nothing, or its notary has not run yet; either way there is
        nothing to prove and reporting a break would make silence an incident.
    """
    repository = ChainRepository(db)
    page_size = settings.ledger_chain_verify_page
    after = 0
    previous: str | None = None
    entries = 0
    checked = 0
    skipped = 0

    while True:
        links = await repository.links_for(user_id, after_seq=after, limit=page_size)
        if not links:
            return ChainAudit(
                ok=True,
                entries=entries,
                payloads_checked=checked,
                payloads_skipped=skipped,
                head_hash=previous,
                deep=deep,
            )

        verdict = walk(links, start_seq=after + 1, previous=previous)
        entries += verdict.entries_checked
        if not verdict.ok:
            return _broken(verdict, entries, checked, skipped, deep, user_id=user_id)

        if deep:
            page_checked, page_skipped, broken = await _check_payloads(db, links)
            checked += page_checked
            skipped += page_skipped
            if broken is not None:
                ledger_chain_breaks_total.labels(reason=ChainBreak.PAYLOAD.value).inc()
                _note_break(ChainBreak.PAYLOAD.value, broken, user_id=user_id)
                return ChainAudit(
                    ok=False,
                    entries=entries,
                    payloads_checked=checked,
                    payloads_skipped=skipped,
                    broken_at_seq=broken,
                    reason=ChainBreak.PAYLOAD,
                    deep=True,
                )

        previous = verdict.head_hash
        after = links[-1].seq


def _broken(
    verdict: ChainVerdict,
    entries: int,
    checked: int,
    skipped: int,
    deep: bool,
    *,
    user_id: uuid.UUID | None = None,
) -> ChainAudit:
    """Turn a page's walk failure into the account's audit.

    Args:
        verdict: The failing page verdict.
        entries: Links walked across every page, this one included.
        checked: Payloads re-digested so far.
        skipped: Payloads declined so far.
        deep: The requested depth.
        user_id: Whose chain, for the integrity row.

    Returns:
        The audit.
    """
    if verdict.reason is not None:
        ledger_chain_breaks_total.labels(reason=verdict.reason.value).inc()
        _note_break(verdict.reason.value, verdict.broken_at_seq)
    return ChainAudit(
        ok=False,
        entries=entries,
        payloads_checked=checked,
        payloads_skipped=skipped,
        broken_at_seq=verdict.broken_at_seq,
        reason=verdict.reason,
        deep=deep,
    )


async def _check_payloads(db: AsyncSession, links: list[ChainLink]) -> tuple[int, int, int | None]:
    """Re-digest the rows one page of entries covers.

    Loaded in BULK per model rather than row by row: a deep verification of a
    long chain would otherwise be one query per entry, which is how an audit
    endpoint becomes the outage it was meant to detect.

    Args:
        db: The session.
        links: The page, already walked and sound.

    Returns:
        ``(checked, skipped, broken_at_seq)`` — the position of the first entry
        whose covered row no longer matches, or None when they all do.
    """
    wanted: dict[str, set[uuid.UUID]] = {}
    for link in links:
        subject = _BY_KIND.get(link.kind)
        if subject is None or link.subject_id is None:
            continue  # the genesis entry covers no row, by construction
        if link.digest_version != DIGEST_VERSION:
            continue
        wanted.setdefault(subject.model, set()).add(link.subject_id)

    rows: dict[tuple[str, uuid.UUID], Any] = {}
    for model_name, ids in wanted.items():
        model = _MODELS[model_name]
        found = await db.execute(select(model).where(model.id.in_(ids)))
        for row in found.scalars().all():
            rows[(model_name, row.id)] = row

    checked = 0
    skipped = 0
    for link in links:
        subject = _BY_KIND.get(link.kind)
        if subject is None or link.subject_id is None:
            continue
        if link.digest_version != DIGEST_VERSION:
            skipped += 1
            continue
        row = rows.get((subject.model, link.subject_id))
        # A missing row is a break, not a skip: the register row this entry
        # covers was deleted, which is exactly what the chain exists to expose.
        if row is None or digest_of(row, subject) != link.payload_digest:
            return checked, skipped, link.seq
        checked += 1
    return checked, skipped, None


def _note_break(reason: str, seq: int | None, *, user_id: uuid.UUID | None = None) -> None:
    """Persist a chain break beside the metric that already counts it.

    Scheduled rather than awaited: verification is a read path a user or an
    operator is waiting on, and recording the finding must not add a write to
    their latency. The metric fires either way, so the alert never depends on
    this landing (ADR-263 lot 8).

    Args:
        reason: The break's classification.
        seq: Where the walk stopped.
        user_id: Whose chain, when the caller knew.
    """
    from src.domains.agents.effects.integrity import IntegrityKind, record_integrity_event
    from src.infrastructure.async_utils import safe_fire_and_forget

    safe_fire_and_forget(
        record_integrity_event(
            IntegrityKind.CHAIN_BROKEN,
            user_id=user_id,
            detail=f"{reason}@{seq}" if seq is not None else reason,
        ),
        name="integrity_chain_broken",
    )


__all__ = ["ChainAudit", "verify_chain"]
