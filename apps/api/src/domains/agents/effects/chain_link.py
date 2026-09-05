"""The link, and the walk that decides a chain holds (ADR-263, lot 5).

Pure by design: everything the chain promises reduces to two functions — how an
entry is hashed, and how a walk decides the chain holds — and both must be
verifiable without a database, so the property can be PINNED rather than
observed on a happy path.

The verdict is rich rather than boolean. An audit device that answers "broken"
without saying where and why sends an operator to guess, and a guess is how a
real break gets waved away as a false alarm.

One subtlety worth stating: ``seq`` orders NOTARISATION, not chronology. A row
whose transaction committed late is notarised after rows with newer timestamps,
so a reader comparing ``seq`` with ``occurred_at`` will occasionally see them
disagree. That is correct, and both are recorded.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.domains.agents.effects.chain_digest import row_digest


class ChainBreak(str, Enum):
    """Why a chain stopped verifying.

    Attributes:
        SEQUENCE: A missing, duplicated or out-of-order position — an entry was
            deleted, or the chain does not start at one.
        PREV_HASH: An entry points at a predecessor it does not follow.
        ENTRY_HASH: An entry's own hash does not match its content — it was
            rewritten.
        PAYLOAD: The covered row no longer matches the digest that was taken of
            it, or has been deleted.
    """

    SEQUENCE = "sequence"
    PREV_HASH = "prev_hash"
    ENTRY_HASH = "entry_hash"
    PAYLOAD = "payload"


@dataclass(frozen=True)
class ChainLink:
    """One entry, as verification reads it.

    A plain record rather than the ORM row, so the walk can be exercised
    without a database and so a future storage change cannot alter what
    verification means.
    """

    seq: int
    kind: str
    subject_id: uuid.UUID | None
    payload_digest: str
    prev_hash: str | None
    entry_hash: str
    digest_version: int
    occurred_at: datetime


@dataclass(frozen=True)
class ChainVerdict:
    """What a walk concluded.

    Attributes:
        ok: Whether every link held.
        entries_checked: How far the walk got — it STOPS at the first break.
        broken_at_seq: The position that failed, when one did.
        reason: What failed there.
        head_hash: The chain's last hash when it holds. This is what an
            operator writes down: comparing it later is the only defence
            against someone able to rewrite a row AND its entry.
    """

    ok: bool
    entries_checked: int
    broken_at_seq: int | None = None
    reason: ChainBreak | None = None
    head_hash: str | None = None


#: Written where a predecessor would be, for the first entry of a chain. A
#: distinct token rather than an empty string: otherwise a chain could be
#: re-rooted at an arbitrary point by blanking one ``prev_hash``.
_NO_PREDECESSOR = "\x00root"


def link_hash(
    *,
    seq: int,
    kind: str,
    subject_id: uuid.UUID | None,
    payload_digest: str,
    prev_hash: str | None,
) -> str:
    """The hash binding one entry to its predecessor.

    Args:
        seq: Position in the account's chain.
        kind: Which stage this entry covers.
        subject_id: The register row covered, or None for the genesis entry.
        payload_digest: Digest of that row's business columns.
        prev_hash: The previous entry's hash, or None for the first.

    Returns:
        Lowercase hexadecimal SHA-256, over the same canonical encoding the row
        digests use — so the whole chain has ONE encoding to reason about.
    """
    return row_digest(
        {
            "seq": seq,
            "kind": kind,
            "subject": subject_id,
            "payload": payload_digest,
            "prev": prev_hash if prev_hash is not None else _NO_PREDECESSOR,
        }
    )


def walk(
    links: list[ChainLink], *, start_seq: int = 1, previous: str | None = None
) -> ChainVerdict:
    """Verify a chain, stopping at the first break.

    Resumable on purpose: a chain has no upper length, so verification reads it
    in pages and carries the two values that bind one page to the next — the
    position it expects and the hash it must follow.

    Args:
        links: One account's entries, ordered by ``seq``.
        start_seq: The position the first of these links must carry.
        previous: The hash the first of these links must follow; None only at
            the very beginning of a chain.

    Returns:
        The verdict, counting only the links in THIS page. An EMPTY chain is
        valid: an account that has done nothing has nothing to prove, and
        treating that as a failure would make every fresh account an incident.
    """
    checked = 0
    for expected_seq, link in enumerate(links, start=start_seq):
        if link.seq != expected_seq:
            return ChainVerdict(
                ok=False,
                entries_checked=checked,
                broken_at_seq=link.seq,
                reason=ChainBreak.SEQUENCE,
            )
        if link.prev_hash != previous:
            return ChainVerdict(
                ok=False,
                entries_checked=checked,
                broken_at_seq=link.seq,
                reason=ChainBreak.PREV_HASH,
            )
        recomputed = link_hash(
            seq=link.seq,
            kind=link.kind,
            subject_id=link.subject_id,
            payload_digest=link.payload_digest,
            prev_hash=link.prev_hash,
        )
        if recomputed != link.entry_hash:
            return ChainVerdict(
                ok=False,
                entries_checked=checked,
                broken_at_seq=link.seq,
                reason=ChainBreak.ENTRY_HASH,
            )
        previous = link.entry_hash
        checked += 1
    return ChainVerdict(ok=True, entries_checked=checked, head_hash=previous)
