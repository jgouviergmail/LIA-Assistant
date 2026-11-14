"""Consent- and source-fenced automatic psyche updates after a person's answer."""

from uuid import UUID

import structlog

from src.domains.psyche.engine import PsycheAppraisal
from src.domains.psyche.service import PsycheService, store_psyche_summary
from src.domains.users.extraction_consent import ExtractionKind, snapshot_extraction_consent
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def psyche_post_response_background(
    user_id: str,
    appraisal: PsycheAppraisal | None,
    run_id: str,
    *,
    extraction_revision: int | None,
) -> None:
    """Apply only while the original source and captured account consent remain current.

    The final consent/source locks and all state/history writes share one short
    SQL transaction. This computation calls no model, provider or Redis client.
    """
    if extraction_revision is None:
        return
    try:
        async with get_db_context() as db:
            if (
                await snapshot_extraction_consent(
                    db,
                    UUID(user_id),
                    ExtractionKind.PSYCHE,
                    expected_revision=extraction_revision,
                    lock=True,
                )
                is None
            ):
                return
            summary = await PsycheService(db).process_post_response(UUID(user_id), appraisal)
            await db.commit()
        if summary:
            store_psyche_summary(run_id, summary.model_dump())
    except Exception as exc:
        logger.warning(
            "psyche_post_response_background_failed",
            user_id=user_id,
            run_id=run_id,
            error_type=type(exc).__name__,
        )
