"""Mark derived portraits stale and settle journal work by the revision read.

A change in the journal never WIPES the portrait (2026-10-12, ADR-269's
doctrine: a usable synthesis is never replaced by nothing): it moves the
revision, ``portrait_is_current`` reads the words as STALE, every surface
serves them dated, and the next consolidation replaces them. An ERASURE is
the one exception: a deleted entry takes with it every claim it supported
(``withdraw_journal_supports``) — a stale flag is no answer to « delete this ».

Every writer takes the owner lock before entry locks. No method commits: the
caller owns the transaction and its consent fence.
"""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import case, cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User


async def lock_journal_owner(db: AsyncSession, user_id: UUID) -> None:
    """Serialize short journal settlements in a single lock order."""
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())


async def mark_journal_changed(
    db: AsyncSession, user_id: UUID, *, invalidate_portrait: bool = True
) -> None:
    """Include creates, edits, evidence and deletions in the work revision.

    Args:
        db: The caller's session (it owns the transaction).
        user_id: The account.
        invalidate_portrait: True when the change moves what the portrait was
            compiled from — the words stay and read as STALE through the
            revision; False for a confirming reaction, which keeps an
            already-versioned portrait CURRENT.
    """
    values: dict[str, Any] = {"journal_revision": User.journal_revision + 1}
    if not invalidate_portrait:
        # A confirming reaction changes work/evidence, not the selected words.
        # Advance only an already-versioned portrait; never bless legacy prose.
        values["journal_portrait_sources"] = case(
            (
                User.journal_portrait_sources["journal_revision"]
                == func.to_jsonb(User.journal_revision),
                func.jsonb_set(
                    User.journal_portrait_sources,
                    array(["journal_revision"]),
                    func.to_jsonb(User.journal_revision + 1),
                ),
            ),
            else_=cast(User.journal_portrait_sources, JSONB),
        )
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )


def cites_removed_entry(claim: Any, entry_ids: Iterable[str] | None) -> bool:
    """Whether a stored claim rests on one of the removed entries (None = every entry).

    Args:
        claim: A stored claim (``PortraitClaim.model_dump()``); an unreadable shape
            is read as citing a removed entry — erasure fails safe.
        entry_ids: The removed entries, or None when the whole journal went.
    """
    if not isinstance(claim, dict) or not isinstance(claim.get("supports"), list):
        return True
    removed = None if entry_ids is None else set(entry_ids)
    for support in claim["supports"]:
        source = support.get("source") if isinstance(support, dict) else None
        if not isinstance(source, str) or not source.startswith("journal:"):
            continue
        if removed is None or source.removeprefix("journal:") in removed:
            return True
    return False


def _render_kept(claims: list[dict[str, Any]], placement: str) -> str | None:
    return (
        "\n\n".join(
            str(claim["text"]) for claim in claims if claim.get("placement", "full") == placement
        )
        or None
    )


async def withdraw_journal_supports(
    db: AsyncSession, user_id: UUID, entry_ids: Iterable[str] | None
) -> None:
    """Erase from the portrait every claim a removed entry supported.

    The claims the portrait was published from are stored with it, each with
    its supports: the ones resting on a removed entry go, the others keep the
    words they established, re-rendered per format. A portrait whose claims
    cannot be read (legacy prose) is wiped whole: erasure can only be surgical
    where the provenance says what rests on what. The revision moved already
    (``mark_journal_changed``), so what stays reads as stale and is recompiled.

    Args:
        db: The caller's session (it owns the transaction and the owner lock).
        user_id: The account.
        entry_ids: The removed entries' ids, or None when every entry went.
    """
    provenance, full, brief = (
        await db.execute(
            select(
                User.journal_portrait_sources,
                User.journal_portrait_full,
                User.journal_portrait_brief,
            ).where(User.id == user_id)
        )
    ).one()
    if full is None and brief is None:
        return
    stored = provenance.get("claims") if isinstance(provenance, dict) else None
    claims: list[Any] = stored if isinstance(stored, list) else []
    kept = [claim for claim in claims if not cites_removed_entry(claim, entry_ids)]
    values: dict[str, Any]
    if kept and all(isinstance(claim.get("text"), str) for claim in kept):
        values = {
            "journal_portrait_full": _render_kept(kept, "full"),
            "journal_portrait_brief": _render_kept(kept, "brief"),
            "journal_portrait_sources": {
                **provenance,
                "claims": kept,
                "withdrawn_claims": int(provenance.get("withdrawn_claims") or 0)
                + len(claims)
                - len(kept),
            },
        }
    else:
        values = {
            "journal_portrait_full": None,
            "journal_portrait_brief": None,
            "journal_portrait_compiled_at": None,
            "journal_portrait_sources": None,
        }
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )


async def portrait_is_current(db: AsyncSession, user: User) -> bool:
    """Reject an unversioned portrait or one whose authorized sources moved."""
    from src.domains.journals.source_state import portrait_source_state

    provenance: Any = user.journal_portrait_sources
    if not isinstance(provenance, dict):
        return False
    revision = provenance.get("journal_revision")
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision != user.journal_revision
    ):
        return False
    expected = provenance.get("source_state")
    if not isinstance(expected, dict):
        return False
    return expected == await portrait_source_state(db, user)
