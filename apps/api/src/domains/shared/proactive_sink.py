"""Notifying somebody without depending on what does the notifying.

The dispatcher lives in ``infrastructure/proactive`` and imports
``domains.agents``; ``agents`` imports ``domains.workboard`` (its tools), so a
feature domain that reached for the dispatcher would close a runtime cycle —
and the coupling ratchet counts LOCAL imports too, so hiding it inside a
function would not help, it would only make the edge harder to see.

So the dependency is inverted, exactly as ``consultation_sink`` inverts the
effect register's: this module holds a seam, the dispatcher's adapter INSTALLS
itself into it, and any domain may call the seam. Nothing here imports
anything.

Two properties this seam owes its callers, and neither is optional:

- **an action is CLAIMED before it happens and SETTLED from its result**
  (ADR-263). Sending a notification is the one act of LIA's own initiative a
  person actually experiences, and the ledger had never held a single row for
  it. The claim belongs to the implementation, not to each caller: a second
  caller writing it itself is a second chance to forget.
- **the answer is what the dispatch REPORTED**, never the absence of an
  exception. A dispatch that reached no channel is a notification nobody got,
  and it must read as such.

With nothing installed the call is a no-op that answers False rather than
raising: a script, a probe or a narrow unit test has no dispatcher, and a
helper that raised there would turn a notification into an outage. **But a
silent no-op in production is exactly the failure ADR-270 was written about**,
so the boot DECLARES the wiring and refuses a mute seam
(``startup/registries.py``); ``notifier_is_installed`` exists for that guard,
never for a caller to branch on.
"""

from __future__ import annotations

from typing import Any, Protocol


class ProactiveNotifier(Protocol):
    """What the dispatcher offers a domain that has something to say.

    The fields are NAMED rather than opaque: a seam accepting ``**Any`` would
    let a caller misspell one and send a notification with a missing piece —
    the very silence this inversion exists to avoid.
    """

    async def __call__(
        self,
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
        """Send one notification and say whether it reached anybody.

        Args:
            db: The caller's session; the archived chat row is written on it.
            user: The account row being notified.
            content: The body, already in that person's language.
            task_type: Which surface is speaking — a bounded word, never user
                text. It names the notification's kind on every channel.
            target_id: What the notification is about.
            metadata: Bounded payload the frontend renders its actions from.
            title: An explicit title, or None to take the localised one for
                ``task_type``.
            run_id: The run this belongs to, shared with the registers: the
                sweep's, or the act's own (a ticket event). Required — a
                default would file rows under a placeholder.
            occurrence: Which of the run's notifications this is, when it
                speaks more than once; None for a surface that speaks once.

        Returns:
            True when at least one channel accepted it.
        """


async def _ignore(
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
    """The seam before the dispatcher claims it: nothing is sent."""
    return False


_notifier: ProactiveNotifier = _ignore


def install_proactive_notifier(notifier: ProactiveNotifier) -> None:
    """Let the dispatcher receive what the domains want to say.

    Called once, by the dispatcher's own adapter at import.

    Args:
        notifier: The adapter that claims, dispatches and settles.
    """
    global _notifier  # noqa: PLW0603 — one seam, installed once, by its owner
    _notifier = notifier


async def send_proactive_notification(
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
    """Send one notification through the installed dispatcher, or do nothing.

    Args:
        db: The caller's session.
        user: The account being notified.
        content: The body, already in that person's language.
        task_type: Which surface is speaking.
        target_id: What the notification is about.
        metadata: Bounded payload for the frontend's action row.
        title: An explicit title, or None for the localised default.
        run_id: The run this belongs to — the sweep's, or the act's own.
        occurrence: Which of the run's notifications this is, when it speaks
            more than once.

    Returns:
        True when at least one channel accepted it; False when none did, and
        False when no dispatcher is installed.
    """
    return await _notifier(
        db=db,
        user=user,
        content=content,
        task_type=task_type,
        target_id=target_id,
        metadata=metadata,
        title=title,
        run_id=run_id,
        occurrence=occurrence,
    )


def notifier_is_installed() -> bool:
    """Whether a dispatcher has claimed the seam — for the boot guard only."""
    return _notifier is not _ignore


__all__ = [
    "ProactiveNotifier",
    "install_proactive_notifier",
    "notifier_is_installed",
    "send_proactive_notification",
]
