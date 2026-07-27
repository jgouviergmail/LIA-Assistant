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

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class JournalResponseFeedbackHooks:
    """Journal-domain implementation of the response-feedback port."""

    async def apply_verdict(
        self, db: AsyncSession, user_id: UUID, entry_ids: list[str], outcome: str
    ) -> int:
        """Increment ``outcome`` counters on the user's entries.

        Foreign, vanished, or malformed IDs are silently skipped — the
        feedback must succeed even when the injected entries moved on.

        Returns:
            Number of entries actually updated.
        """
        from src.domains.journals.service import JournalService

        service = JournalService(db)
        updated = 0
        # Sequential on the shared session by design (a handful of indexed rows).
        for raw_id in entry_ids:
            try:
                entry_id = UUID(raw_id)
            except ValueError:
                continue
            entry = await service.get_entry_for_user(entry_id, user_id)
            if entry is None:
                continue  # deleted since, or not this user's
            await service.update_entry(entry, evidence_outcome=outcome)
            updated += 1
        return updated

    async def record_correction(self, db: AsyncSession, user_id: UUID, comment: str) -> None:
        """Land the correction as an L0 ``user_correction`` entry.

        Same source/level as the portrait-feedback lever so the next
        consolidation prioritizes it — deliberately WITHOUT the synchronous
        recompilation. The theme differs by subject: feedback on a response is
        a lesson about what the assistant did.
        """
        from src.domains.journals.constants import JOURNAL_RESPONSE_FEEDBACK_THEME
        from src.domains.journals.service import JournalService

        await JournalService(db).create_entry(
            user_id=user_id,
            theme=JOURNAL_RESPONSE_FEEDBACK_THEME,
            title="User feedback on a response",
            content=comment[: settings.journal_max_entry_chars],
            source="user_correction",
            max_entry_chars=settings.journal_max_entry_chars,
            confidence="high",
            level="L0",
        )
