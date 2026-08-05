"""Product analytics service — seam-facing, best-effort, off the hot path.

Called fire-and-forget from two chokepoints (ADR-178):

1. Chat run finalization (``agents/api/service.py``) — records the produced
   outcome (E3) once the assistant response has been archived.
2. Response feedback (``conversations/router.py``) — upgrades to E1 on
   thumbs_up, rejects on thumbs_down.

Every entry point is guarded by ``product_analytics_enabled``, opens its OWN
database session (never a shared one — concurrency rule), and NEVER raises:
losing one telemetry row must never degrade a user-facing request.
"""

from uuid import UUID

import structlog

from src.core.config import settings
from src.core.i18n import DEFAULT_LANGUAGE, normalize_language
from src.domains.product.constants import (
    ProductEventType,
    derive_channel,
    derive_device_class,
    derive_result_type,
)

logger = structlog.get_logger(__name__)


def schedule_outcome_recording(
    *,
    archived_message_id: UUID | None,
    user_id: UUID,
    run_id: str,
    session_id: str | None,
    intention: str | None,
    execution_mode: str,
    user_language: str | None,
    user_agent: str | None,
    duration_seconds: float,
    domain: str | None = None,
) -> None:
    """Fire-and-forget the outcome recording for a finalized run.

    Keeps the (frozen, CC-capped) SSE service seam to a single unconditional
    call: the no-result guard lives HERE, not at the call site.

    Args:
        archived_message_id: The archived assistant row id — None means no
            result was presented, so nothing is recorded.
        user_id: Run owner.
        run_id: Unique run identifier.
        session_id: Session identifier (channel derivation).
        intention: Router intention from the assistant metadata, if any.
        execution_mode: ``pipeline`` | ``react``.
        user_language: Raw user language (normalized downstream).
        user_agent: Raw request User-Agent (reduced downstream, ADR-144).
        duration_seconds: Request-to-presentation duration.
        domain: Primary domain resolved by query intelligence, if any —
            validated downstream against ``DOMAIN_REGISTRY``.
    """
    if archived_message_id is None:
        return
    from src.infrastructure.async_utils import safe_fire_and_forget

    safe_fire_and_forget(
        record_outcome_produced(
            user_id=user_id,
            run_id=run_id,
            session_id=session_id,
            intention=intention,
            execution_mode=execution_mode,
            user_language=user_language,
            user_agent=user_agent,
            latency_ms=int(duration_seconds * 1000),
            domain=domain,
        ),
        name="product_outcome_record",
    )


async def record_outcome_produced(
    *,
    user_id: UUID,
    run_id: str,
    session_id: str | None,
    intention: str | None,
    execution_mode: str,
    user_language: str | None,
    user_agent: str | None,
    latency_ms: int | None,
    turn_count: int | None = None,
    app_version: str | None = None,
    domain: str | None = None,
) -> None:
    """Record a produced outcome (E3) for a finalized run — best-effort.

    Args:
        user_id: Run owner.
        run_id: Unique run identifier (one principal outcome per run).
        session_id: Session identifier (channel derivation).
        intention: Router intention from the assistant metadata, if any.
        execution_mode: ``pipeline`` | ``react`` (ADR-070).
        user_language: Raw user language — normalized through the single
            ``normalize_language`` chokepoint (zh → zh-CN rule).
        user_agent: Raw request User-Agent — reduced to a bounded device
            class via ``core.client_metadata`` families (ADR-144); the raw
            value is never stored.
        latency_ms: Request-to-presentation latency, if measured.
        turn_count: Turns consumed, if known.
        app_version: Backend string version, if known.
        domain: Primary domain, if any. The bounded-vocabulary invariant is
            enforced at the single PRODUCER (the streaming capture filters
            against ``DOMAIN_REGISTRY`` — importing the registry here would
            create the agents<->product runtime cycle the coupling ratchet
            forbids); this seam only defaults absence to ``unknown``.
    """
    if not getattr(settings, "product_analytics_enabled", False):
        return
    try:
        from src.core.client_metadata import parse_user_agent
        from src.domains.product.repository import ProductRepository
        from src.infrastructure.database import get_db_context
        from src.infrastructure.observability.metrics_product import track_outcome_event

        channel = derive_channel(session_id)
        result_type = derive_result_type(intention, channel)
        _, os_family = parse_user_agent(user_agent)
        device_class = derive_device_class(os_family)
        locale = normalize_language(user_language) if user_language else DEFAULT_LANGUAGE
        bounded_domain = domain if domain and isinstance(domain, str) else "unknown"

        async with get_db_context() as db:
            repo = ProductRepository(db)
            await repo.upsert_produced(
                user_id=user_id,
                run_id=run_id,
                result_type=result_type,
                domain=bounded_domain,
                execution_mode=execution_mode,
                channel=channel,
                device_class=device_class,
                locale=locale,
                latency_ms=latency_ms,
                turn_count=turn_count,
                app_version=app_version,
            )
            await repo.record_event(
                user_id=user_id,
                event_type=ProductEventType.OUTCOME_PRODUCED,
                run_id=run_id,
                channel=channel,
                payload={"result_type": result_type},
            )
            await db.commit()

        track_outcome_event(result_type, "unknown", "E3")
        logger.debug(
            "product_outcome_recorded",
            run_id=run_id,
            result_type=result_type,
            channel=channel,
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break a run
        logger.warning(
            "product_outcome_record_failed",
            run_id=run_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def record_response_feedback(*, user_id: UUID, run_id: str | None, verdict: str) -> None:
    """Apply an explicit verdict to the run's outcome (E1 path) — best-effort.

    Args:
        user_id: Feedback author.
        run_id: Run of the judged assistant message (from its metadata);
            silently ignored when the message predates run tracking.
        verdict: ``thumbs_up`` | ``thumbs_down``.
    """
    if not getattr(settings, "product_analytics_enabled", False):
        return
    if not run_id:
        return
    try:
        from src.domains.product.repository import ProductRepository
        from src.infrastructure.database import get_db_context
        from src.infrastructure.observability.metrics_product import track_outcome_event

        event_type = (
            ProductEventType.OUTCOME_VALIDATED
            if verdict == "thumbs_up"
            else ProductEventType.OUTCOME_REJECTED
        )
        async with get_db_context() as db:
            repo = ProductRepository(db)
            transitions = await repo.apply_feedback(user_id=user_id, run_id=run_id, verdict=verdict)
            if transitions:
                await repo.record_event(
                    user_id=user_id,
                    event_type=event_type,
                    run_id=run_id,
                    channel="web",
                    payload={"verdict": verdict},
                )
            await db.commit()

        if verdict == "thumbs_up":
            for result_type, domain in transitions:
                track_outcome_event(result_type, domain, "E1")
        logger.debug(
            "product_feedback_recorded",
            run_id=run_id,
            verdict=verdict,
            transitions=len(transitions),
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break a request
        logger.warning(
            "product_feedback_record_failed",
            run_id=run_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
