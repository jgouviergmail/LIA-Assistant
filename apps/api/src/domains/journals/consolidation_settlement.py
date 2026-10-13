"""Prepare provider work outside locks; publish one consistent maintenance result."""

from contextlib import suppress
from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy import select

from src.domains.journals.consolidation_controls import commit_consolidation
from src.domains.journals.consolidation_lifecycle import ConsolidationSnapshot, current_snapshot
from src.domains.journals.consolidation_output import (
    MaintenanceOutput,
    PortraitClaim,
    admit_portrait_claims,
    grounded_portraits,
)
from src.domains.journals.maintenance_actions import (
    PreparedEmbeddings,
    apply_action,
    prepare_action,
)
from src.domains.journals.maintenance_actions import validate_maintenance as validate_maintenance
from src.domains.journals.models import JournalEntry
from src.domains.journals.portrait_sources import PortraitSourceBundle
from src.domains.journals.service import JournalService
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_journals import (
    journal_consolidation_deletes_total,
    journal_portrait_compile_duration_seconds,
)


async def settle_maintenance(
    user_id: UUID,
    snapshot: ConsolidationSnapshot,
    output: MaintenanceOutput,
    entries: list[JournalEntry],
    sources: PortraitSourceBundle,
    *,
    manual: bool,
    personality_code: str | None,
    max_entry_chars: int,
) -> tuple[int, str]:
    """Any failed action rolls back this result, including its derived portrait."""
    validate_maintenance(output, entries, max_entry_chars)
    by_id = {str(entry.id): entry for entry in entries}
    prepared: list[PreparedEmbeddings] = []
    # All provider work precedes the consent/owner lock. Preparation can be
    # discarded if any journal/source/consent revision changed meanwhile.
    async with get_db_context() as preparation_db:
        if await current_snapshot(preparation_db, user_id, snapshot, manual=manual) is None:
            return 0, "stale"
        await preparation_db.commit()  # end the read transaction before provider work
        service = JournalService(preparation_db)
        for action in output.actions:
            prepared.append(await prepare_action(service, action, by_id))
    async with get_db_context() as db:
        try:
            user = await current_snapshot(db, user_id, snapshot, manual=manual, lock=True)
            if user is None:
                await db.rollback()
                return 0, "stale"
            previous_provenance = user.journal_portrait_sources
            previous_is_current = _previous_is_current(previous_provenance, snapshot)
            service = JournalService(db)
            applied_count, changed = await _apply_actions(
                service,
                output,
                prepared,
                user_id,
                by_id,
                entries,
                personality_code=personality_code,
                max_entry_chars=max_entry_chars,
            )
            # Fresh SQL sees this run's invalidation revision; identity-map
            # User objects deliberately do not follow bulk update arithmetic.
            revision = await db.scalar(select(User.journal_revision).where(User.id == user_id))
            compiled = await _publish_portrait(
                user,
                service,
                output,
                sources,
                snapshot,
                revision,
                previous_is_current,
                previous_provenance,
                applied_count,
                changed,
            )
            user.journal_consolidated_revision = revision
            # Source deltas during settlement remain after this READ timestamp.
            user.journal_last_consolidated_at = snapshot.captured_at
            # A batch that applied nothing and compiled nothing changed nothing.
            status = "success" if applied_count or compiled else "no_op"
            await commit_consolidation(db, applied_count, status)
            _record_deletions(output)
            return applied_count, status
        except BaseException:
            await db.rollback()
            raise


async def _apply_actions(
    service: JournalService,
    output: MaintenanceOutput,
    prepared: list[PreparedEmbeddings],
    user_id: UUID,
    by_id: dict[str, JournalEntry],
    entries: list[JournalEntry],
    *,
    personality_code: str | None,
    max_entry_chars: int,
) -> tuple[int, set[str]]:
    """Apply every action; return how many applied and which entries CHANGED.

    Only an action that changed its entry bars the claims citing it: a zero-effect
    update is no change (review 2026-10-12 b).
    """
    applied_count = 0
    changed: set[str] = set()
    revisions = {str(entry.id): entry.revision for entry in entries}
    for action, embeddings in zip(output.actions, prepared, strict=True):
        applied = await apply_action(
            service,
            action,
            user_id,
            by_id,
            revisions,
            embeddings,
            personality_code=personality_code,
            limit=max_entry_chars,
        )
        applied_count += applied
        if applied:
            if action.entry_id:
                changed.add(action.entry_id)
            changed.update(str(identifier) for identifier in action.merge_source_ids)
    return applied_count, changed


def _previous_is_current(provenance: Any, snapshot: ConsolidationSnapshot) -> bool:
    return bool(
        isinstance(provenance, dict)
        and provenance.get("journal_revision") == snapshot.journal_revision
        and provenance.get("source_state") == snapshot.sources
    )


def _record_deletions(output: MaintenanceOutput) -> None:
    with suppress(Exception):
        journal_consolidation_deletes_total.inc(
            sum(
                (
                    1
                    if action.action == "delete"
                    else len(action.merge_source_ids) if action.action == "merge" else 0
                )
                for action in output.actions
            )
        )


async def _publish_portrait(
    user: User,
    service: JournalService,
    output: MaintenanceOutput,
    sources: PortraitSourceBundle,
    snapshot: ConsolidationSnapshot,
    revision: int | None,
    previous_is_current: bool,
    previous_provenance: Any,
    applied_count: int,
    changed: set[str] | None = None,
) -> bool:
    """Publish the compiled portrait, or keep the previous words; say which.

    Returns:
        True when the words were REPLACED (a publication or an explicit empty
        compilation), False when the previous synthesis stays.
    """
    provenance: dict[str, Any] = {
        **sources.provenance,
        "journal_revision": revision,
        "source_state": snapshot.sources,
    }
    compiled = False
    if output.portrait_claims is not None:
        remaining = await service.get_all_active(user.id)
        admitted = admit_portrait_claims(output, remaining, sources.sections, changed=changed)
        published: list[PortraitClaim] = []
        started = monotonic()
        full, brief = grounded_portraits(admitted, remaining, sources.sections, published=published)
        with suppress(Exception):
            journal_portrait_compile_duration_seconds.observe(monotonic() - started)
        # A publication, or an explicit EMPTY compilation (the model said the material
        # is insufficient), replaces the words. A batch whose every proposed claim was
        # dropped — at resolution OR at parsing — compiled NOTHING: it must not wipe
        # the words and call that a success (reviews 2026-10-12, 2026-10-12 c) — and a
        # brief alone is no publication either: it would replace a good full with
        # nothing (review 2026-10-12 b).
        compiled = bool(full) or not (output.portrait_claims or output.rejected_claims)
        if compiled:
            user.journal_portrait_full, user.journal_portrait_brief = full, brief
            user.journal_portrait_compiled_at = snapshot.captured_at
            provenance["claims"] = [claim.model_dump() for claim in published]
            provenance["omitted_claims"] = (
                len(output.portrait_claims) + len(output.rejected_claims) - len(published)
            )
    if not compiled:
        # The words STAY (2026-10-12) under the provenance they were compiled with:
        # a rewritten provenance would read old words as CURRENT, so the previous one
        # is kept whole (an unversioned one keeps no revision and therefore reads as
        # stale), and the next publication replaces them — never an empty panel.
        # Maintenance can create new evidence; compile that evidence on the next
        # stable pass rather than grounding prose on this call's own inventions.
        provenance = dict(previous_provenance) if isinstance(previous_provenance, dict) else {}
    provenance["portrait_pending"] = _portrait_pending(
        compiled, previous_is_current, previous_provenance, applied_count
    )
    user.journal_portrait_sources = provenance
    return compiled


def _portrait_pending(
    compiled: bool,
    previous_is_current: bool,
    previous_provenance: Any,
    applied_count: int,
) -> bool:
    if applied_count:
        return True
    if compiled:
        return False
    previously_pending = (
        isinstance(previous_provenance, dict)
        and previous_provenance.get("portrait_pending") is True
    )
    return not previous_is_current or previously_pending
