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
    grounded_portraits,
)
from src.domains.journals.maintenance_actions import (
    PreparedEmbeddings,
    apply_action,
    prepare_action,
)
from src.domains.journals.maintenance_actions import validate_maintenance as validate_maintenance
from src.domains.journals.models import JournalEntry
from src.domains.journals.portrait_review import (
    PortraitReviewReceipt,
    require_portrait_review,
    reviewed_portrait,
)
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
    review: PortraitReviewReceipt | None = None,
) -> tuple[int, str]:
    """Any failed action rolls back this result, including its derived portrait."""
    validate_maintenance(output, entries, max_entry_chars)
    require_portrait_review(output, entries, sources, review)
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
            applied_count = 0
            revisions = {str(entry.id): entry.revision for entry in entries}
            for action, embeddings in zip(output.actions, prepared, strict=True):
                applied_count += await apply_action(
                    service,
                    action,
                    user_id,
                    by_id,
                    revisions,
                    embeddings,
                    personality_code=personality_code,
                    limit=max_entry_chars,
                )
            # Fresh SQL sees this run's invalidation revision; identity-map
            # User objects deliberately do not follow bulk update arithmetic.
            revision = await db.scalar(select(User.journal_revision).where(User.id == user_id))
            await _publish_portrait(
                user,
                service,
                output,
                sources,
                snapshot,
                revision,
                previous_is_current,
                previous_provenance,
                review,
                applied_count,
            )
            user.journal_consolidated_revision = revision
            # Source deltas during settlement remain after this READ timestamp.
            user.journal_last_consolidated_at = snapshot.captured_at
            await commit_consolidation(
                db,
                applied_count,
                "success" if applied_count or output.portrait_claims is not None else "no_op",
            )
            _record_deletions(output)
            return applied_count, (
                "success" if applied_count or output.portrait_claims is not None else "no_op"
            )
        except BaseException:
            await db.rollback()
            raise


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
    review: PortraitReviewReceipt | None,
    applied_count: int,
) -> None:
    provenance: dict[str, Any] = {
        **sources.provenance,
        "journal_revision": revision,
        "source_state": snapshot.sources,
    }
    if output.portrait_claims is not None:
        remaining = await service.get_all_active(user.id)
        accepted = reviewed_portrait(output, remaining, sources, review)
        published: list[PortraitClaim] = []
        started = monotonic()
        full, brief = grounded_portraits(
            accepted.portrait_claims or [], remaining, sources.sections, published=published
        )
        with suppress(Exception):
            journal_portrait_compile_duration_seconds.observe(monotonic() - started)
        user.journal_portrait_full, user.journal_portrait_brief = full, brief
        user.journal_portrait_compiled_at = snapshot.captured_at
        provenance["claims"] = [claim.model_dump() for claim in published]
        provenance["omitted_claims"] = len(output.portrait_claims) - len(published)
        if published:
            assert review is not None
            provenance["portrait_review"] = review.provenance()
    elif applied_count or not previous_is_current:
        user.journal_portrait_full = user.journal_portrait_brief = None
        user.journal_portrait_compiled_at = None
    else:
        assert isinstance(previous_provenance, dict)
        provenance = dict(previous_provenance)
    # Maintenance can create new evidence; compile that evidence on the next
    # stable pass rather than grounding prose on this call's own inventions.
    provenance["portrait_pending"] = _portrait_pending(
        output, previous_is_current, previous_provenance, applied_count
    )
    user.journal_portrait_sources = provenance


def _portrait_pending(
    output: MaintenanceOutput,
    previous_is_current: bool,
    previous_provenance: Any,
    applied_count: int,
) -> bool:
    if applied_count:
        return True
    if output.portrait_claims is not None:
        return False
    previously_pending = (
        isinstance(previous_provenance, dict)
        and previous_provenance.get("portrait_pending") is True
    )
    return not previous_is_current or previously_pending
