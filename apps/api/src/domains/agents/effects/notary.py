"""One notary pass: find, order, chain, mark (ADR-263, lot 5).

Asynchronous on a measurement, not a preference. Notarising inside the write
path costs 6,0 ms per row against 0,21 ms for the write itself — ×28 on the
user's critical path, for a property nobody reads in that moment. Out of band,
the same work costs a job that ends in single-digit milliseconds and the
register keeps the latency it has today.

The price of asynchrony is a window: a row created at T is chained at T+δ, and
a rewrite inside δ leaves no trace. That is stated rather than hidden — δ is a
setting, it is measured (``lia_ledger_chain_lag_seconds``), and it is the
honest cost of not taxing every action for an audit nobody asked for yet.

Three properties this pass owes, each with a test that would fail without it:

- **Idempotent.** A second pass over the same rows appends nothing, because
  the marker — not a watermark — decides what is pending.
- **Serialisable.** Two passes racing on one account cannot fork it: the
  loser's ``INSERT`` is refused by ``UNIQUE (user_id, seq)``, its whole
  transaction rolls back, and the next tick redoes it.
- **Per account.** One account's failure notarises the others all the same.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.effects.chain_link import ChainBreak
from src.domains.agents.effects.chain_repository import ChainRepository, genesis_digest
from src.domains.agents.effects.chain_spec import GENESIS_KIND
from src.domains.agents.effects.integrity import IntegrityKind, record_integrity_event
from src.infrastructure.observability.metrics_effects import (
    ledger_chain_breaks_total,
    ledger_chain_entries_total,
    ledger_chain_pass_failures_total,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AccountPass:
    """What one account's transaction is about to commit.

    Returned rather than counted on the spot: a pass that loses its race is
    rolled back, and a metric incremented before the commit would count links
    that never existed. The caller increments once the write is durable.

    Attributes:
        entries: Links appended, the genesis included.
        opened: Whether this pass created the chain.
        kinds: The stage of each appended link, in order.
    """

    entries: int
    opened: bool
    kinds: tuple[str, ...]


@dataclass(frozen=True)
class NotaryReport:
    """What one pass did.

    Attributes:
        accounts: Accounts whose chain was extended.
        entries: Links appended, genesis entries included.
        chains_opened: Accounts whose chain did not exist before this pass.
        failed: Accounts whose transaction was rolled back — a lost race or a
            database error. Their work stays pending and the next tick redoes
            it, which is why this is a counter and not an exception.
    """

    accounts: int = 0
    entries: int = 0
    chains_opened: int = 0
    failed: int = 0


async def notarise_account(db: AsyncSession, user_id: uuid.UUID, *, limit: int) -> AccountPass:
    """Extend one account's chain with what is pending.

    The caller owns the transaction: everything here — the appended links AND
    the markers that say they were appended — must commit together, or a row
    could be marked notarised by an entry that was rolled back.

    Args:
        db: The session, already inside a transaction.
        user_id: Whose chain.
        limit: Ceiling for this pass.

    Returns:
        What the caller is about to commit — and must count only then.
    """
    repository = ChainRepository(db)
    pending = await repository.pending_for(user_id, limit=limit)
    if not pending:
        return AccountPass(entries=0, opened=False, kinds=())

    kinds: list[str] = []

    head = await repository.head(user_id)
    seq, previous = head.seq, head.entry_hash
    opened = seq == 0
    if opened:
        seq += 1
        previous = await repository.append(
            user_id,
            seq=seq,
            kind=GENESIS_KIND,
            subject_id=None,
            payload_digest=genesis_digest(
                user_id, uncovered=await repository.register_rows(user_id)
            ),
            prev_hash=None,
        )
        kinds.append(GENESIS_KIND)
    else:
        await _check_contiguity(repository, user_id, head_seq=seq)

    for item in pending:
        seq += 1
        previous = await repository.append(
            user_id,
            seq=seq,
            kind=item.subject.kind,
            subject_id=item.subject_id,
            payload_digest=item.digest,
            prev_hash=previous,
        )
        kinds.append(item.subject.kind)

    await repository.mark_notarised(pending)
    return AccountPass(entries=len(kinds), opened=opened, kinds=tuple(kinds))


async def _check_contiguity(
    repository: ChainRepository, user_id: uuid.UUID, *, head_seq: int
) -> None:
    """Notice a DELETED entry, for the price of one index-only scan.

    A contiguous chain holds exactly as many entries as its last position. The
    comparison is the only tampering detection that runs continuously — the
    other two need a full walk, which is on demand.

    The pass then keeps going on purpose. Refusing to append onto a chain with
    a gap would stop protecting everything that happens NEXT, which is the
    opposite of what an audit device owes: the gap stays visible to any walk,
    and new activity keeps being covered.

    Args:
        repository: The chain's persistence.
        user_id: Whose chain.
        head_seq: The chain's last position.
    """
    entries = await repository.entry_count(user_id)
    if entries != head_seq:
        ledger_chain_breaks_total.labels(reason=ChainBreak.SEQUENCE.value).inc()
        logger.error(
            "ledger_chain_gap_detected",
            user_id=str(user_id),
            head_seq=head_seq,
            entries=entries,
        )


async def run_notary_pass(db: AsyncSession) -> NotaryReport:
    """Notarise every account with pending work, up to this pass's ceilings.

    One transaction per account: a chain that cannot be appended — a lost race
    against a concurrent notary, most often — must not hold up anyone else's.

    Args:
        db: The session; the pass commits it once per account.

    Returns:
        What was done, for the metrics and the log.
    """
    repository = ChainRepository(db)
    accounts = await repository.accounts_with_pending(limit=settings.ledger_chain_accounts_per_pass)
    report = NotaryReport()
    for user_id in accounts:
        try:
            done = await notarise_account(db, user_id, limit=settings.ledger_chain_rows_per_account)
            await db.commit()
        except Exception:
            await db.rollback()
            report = NotaryReport(
                accounts=report.accounts,
                entries=report.entries,
                chains_opened=report.chains_opened,
                failed=report.failed + 1,
            )
            # ANY failure, not only a SQL one: the whole point of one
            # transaction per account is that one account's trouble does not
            # cost the others'. A `TypeError` from a column type the canonical
            # encoding does not know would otherwise abort the entire pass and
            # every account queued behind it, every tick, for as long as the
            # row exists. Expected here under concurrency (UNIQUE (user_id,
            # seq) refuses the loser) — not an error to raise on, since the
            # work stays pending and the next tick redoes it, but never silent
            # either, and `exception` keeps the traceback for the unexpected
            # kind.
            ledger_chain_pass_failures_total.inc()
            logger.exception("ledger_notary_account_failed", user_id=str(user_id))
            # The account's chain fell behind. Awaited here, unlike the read
            # paths: this loop is a background job with nobody waiting on it.
            await record_integrity_event(
                IntegrityKind.NOTARY_FAILED, user_id=user_id, detail="pass_rolled_back"
            )
            continue
        if done.entries:
            # Counted here and not inside the transaction: only a committed
            # link is a link.
            for kind in done.kinds:
                ledger_chain_entries_total.labels(kind=kind).inc()
            report = NotaryReport(
                accounts=report.accounts + 1,
                entries=report.entries + done.entries,
                chains_opened=report.chains_opened + (1 if done.opened else 0),
                failed=report.failed,
            )
    return report


__all__ = ["AccountPass", "NotaryReport", "notarise_account", "run_notary_pass"]
