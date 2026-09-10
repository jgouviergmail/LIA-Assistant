"""The dispatcher's adapter for the proactive seam (ADR-276, ADR-263).

One implementation of « claim the right to notify, send, settle from what came
back », shared by every surface that speaks of its own accord. It lives here
rather than in a domain because it imports the dispatcher, which imports
``agents`` — the edge ``domains/shared/proactive_sink`` exists to invert.

Installing itself is an import side effect, and ADR-270 measured what that
costs when nobody guarantees the import: a seam that answers a no-op in
silence. So the boot has a DECLARED step that imports this module and refuses
a mute seam (``startup/registries.py``).
"""

from __future__ import annotations

from typing import Any

import structlog

from src.domains.shared.proactive_sink import install_proactive_notifier

logger = structlog.get_logger(__name__)


async def dispatch_proactive_notification(
    *,
    db: Any,
    user: Any,
    content: str,
    task_type: str,
    target_id: str,
    metadata: dict[str, Any],
    run_id: str,
    title: str | None = None,
    occurrence: str | None = None,
) -> bool:
    """Claim the right to notify, send, and close the row from the result.

    Never raises: a notification that could not leave must not undo what the
    caller has already durably written — a settled ticket, an accepted
    assignment. It answers False, and the caller decides what to say about it.

    Args:
        db: The caller's session; the archived chat row is written on it.
        user: The account being notified.
        content: The body, already in that person's language.
        task_type: Which surface is speaking — a bounded word.
        target_id: What the notification is about.
        metadata: Bounded payload for the frontend's action row.
        title: An explicit title, or None for the localised default.
        run_id: The run this belongs to, shared with the registers.
        occurrence: Which of the run's notifications this is, when it speaks
            more than once — each is its own claimed action (ADR-263).

    Returns:
        True when at least one channel accepted it.
    """
    # Imported here, not at module level: this module is imported at boot to
    # claim the seam, and pulling the whole notification stack in at that
    # moment would make the seam's wiring depend on the dispatcher's own
    # import graph rather than on the declared step.
    from src.domains.agents.effects.out_of_turn_effects import proactive_notification_effect
    from src.infrastructure.proactive.notification import NotificationDispatcher

    try:
        async with proactive_notification_effect(
            user_id=user.id,
            run_id=run_id,
            task_type=task_type,
            occurrence=occurrence,
        ) as notified:
            result = await NotificationDispatcher().dispatch(
                user=user,
                content=content,
                task_type=task_type,
                target_id=target_id,
                metadata=metadata,
                db=db,
                title=title,
                run_id=run_id,
            )
            # The explicit result, never the absence of an exception: a
            # dispatch that reached no channel is a notification nobody got.
            delivered = bool(result.success)
            notified.delivered = delivered
            return delivered
    except Exception as dispatch_error:  # noqa: BLE001 — never undoes a durable write
        logger.warning(
            "proactive_notification_dispatch_failed",
            task_type=task_type,
            target_id=target_id,
            user_id=str(getattr(user, "id", "")),
            error=str(dispatch_error),
        )
        return False


install_proactive_notifier(dispatch_proactive_notification)
