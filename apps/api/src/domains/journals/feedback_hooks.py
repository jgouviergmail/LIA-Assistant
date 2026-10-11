"""Journal side-effects of response feedback (QW-5, ADR-138).

Implements the :class:`~src.domains.conversations.response_feedback.
JournalFeedbackHooks` port: the conversations domain must not import journals
(domain-cycle ratchet, F009), so this implementation is registered at startup
by ``infrastructure/startup/registries.init_response_feedback_hooks``.

Counters are the system-managed evidence/contradiction increments of
ADR-135 — the caller guarantees they are fed on the FIRST verdict only.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.users.extraction_consent import ExtractionKind, snapshot_extraction_consent
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class JournalResponseFeedbackHooks:
    """Journal-domain implementation of the response-feedback port."""

    async def apply_verdict(
        self,
        db: AsyncSession,
        user_id: UUID,
        entry_ids: list[str],
        outcome: str,
        *,
        expected_revisions: dict[str, int],
        event_key: str,
        evidence_source: str | None,
    ) -> int:
        """Increment ``outcome`` counters on the user's entries.

        Foreign, vanished, or malformed IDs are silently skipped — the
        feedback must succeed even when the injected entries moved on.

        Returns:
            Number of entries actually updated.
        """
        from src.domains.journals.service import JournalService

        if not await is_capability_enabled(PlatformCapability.JOURNALS):
            return 0
        if (
            await snapshot_extraction_consent(db, user_id, ExtractionKind.JOURNAL, lock=True)
            is None
        ):
            return 0
        service = JournalService(db)
        updated = 0
        # Sequential on the shared session by design (a handful of indexed rows).
        for raw_id in dict.fromkeys(entry_ids):
            try:
                entry_id = UUID(raw_id)
            except ValueError:
                continue
            expected_revision = expected_revisions.get(str(entry_id))
            if expected_revision is None:
                continue
            try:
                async with db.begin_nested():
                    entry = await service.get_entry_for_user(entry_id, user_id)
                    if entry is None or entry.revision != expected_revision:
                        continue
                    previous = (entry.evidence_count, entry.contradiction_count)
                    result = await service.update_entry(
                        entry,
                        evidence_outcome=outcome,
                        expected_revision=expected_revision,
                        event_key=event_key,
                        evidence_source=evidence_source,
                    )
                    updated += int(previous != (result.evidence_count, result.contradiction_count))
            except Exception as exc:
                logger.warning(
                    "journal_response_verdict_skipped",
                    entry_id=str(entry_id),
                    error_type=type(exc).__name__,
                )
        return updated

    async def record_correction(self, db: AsyncSession, user_id: UUID, comment: str) -> None:
        """Land the correction as an L0 ``user_correction`` entry.

        Same source/level as the portrait-feedback lever so the next
        consolidation prioritizes it — deliberately WITHOUT the synchronous
        recompilation. The theme differs by subject: feedback on a response is
        a lesson about what the assistant did.
        """
        from src.domains.journals.constants import (
            JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH,
            JOURNAL_RESPONSE_FEEDBACK_THEME,
        )
        from src.domains.journals.service import JournalService

        if not await is_capability_enabled(PlatformCapability.JOURNALS):
            return
        if (
            await snapshot_extraction_consent(db, user_id, ExtractionKind.JOURNAL, lock=True)
            is None
        ):
            return
        # This is verbatim user input, not a generated operational rule. Its
        # closing restrictions must remain intact for later consolidation.
        if len(comment) > JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH:
            raise ValidationError("User correction exceeds the complete-input limit")
        await JournalService(db).create_entry(
            user_id=user_id,
            theme=JOURNAL_RESPONSE_FEEDBACK_THEME,
            title="User feedback on a response",
            content=comment,
            source="user_correction",
            max_entry_chars=JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH,
            confidence="high",
            level="L0",
            # Raw corrections are read by consolidation, never operationally
            # injected. Do not call a provider in the borrowed owner transaction.
            precomputed_embeddings=(None, None),
        )
