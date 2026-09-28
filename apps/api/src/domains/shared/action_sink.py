"""Recording an act a person asked for, without depending on the register.

Some acts communicate to a third party at the person's click, outside any
turn and through no tool: sharing a generated image with a connection
(ADR-316), sending a file or an answer by e-mail (ADR-321). The effect
register is fed by the tool gate, so neither ever reached « Actions » — and
the domains that perform them cannot import the register: ``agents`` imports
``peers`` (its tools read connections), so ``peers`` reaching for
``agents/effects`` would close a runtime cycle, and the coupling ratchet
counts local imports too.

So the dependency is inverted, as ``proactive_sink`` inverts the dispatcher's:
this module holds the seam, the register INSTALLS itself into it, and any
domain may call it. Nothing here imports anything.

Two properties the seam owes its callers, and neither is optional (ADR-263):

- **an act is CLAIMED before it happens and SETTLED from its result** — a
  claim written afterwards would be lost by the very crash it exists to
  survive, and an act that never said it succeeded settles as a FAILURE (the
  safe direction: a message that may not have left must not read as sent);
- **the register never costs the person their act** — with nothing installed,
  or when the register refuses the claim, the act still happens.

A silent no-op in production is the failure ADR-270 was written about, so the
boot DECLARES the wiring and refuses a mute seam (``startup/registries.py``);
``action_recorder_is_installed`` exists for that guard, never for a caller to
branch on.
"""

from __future__ import annotations

from typing import Any, Protocol

#: A generated image shared with a connection (ADR-316) — a synthetic, bounded
#: capability name: no tool performs it, so nothing else would name it.
PEER_IMAGE_SHARE_CAPABILITY = "peer_image_share"
#: A generated file or an answer sent by e-mail (ADR-321).
EMAIL_SHARE_CAPABILITY = "email_share"
#: Every act this seam records — the register refuses any other name.
USER_ACTION_CAPABILITIES = frozenset({PEER_IMAGE_SHARE_CAPABILITY, EMAIL_SHARE_CAPABILITY})


class ActionRecorder(Protocol):
    """What the register offers a domain whose person acts through it.

    The fields are NAMED rather than opaque: a seam accepting ``**Any`` would
    let a caller misspell one and write a row with a missing piece.
    """

    async def claim(self, *, user_id: Any, capability: str, arguments: dict[str, str]) -> Any:
        """Take the right to act; the ticket, or None when the register refused.

        Args:
            user_id: The person who asked.
            capability: One of ``USER_ACTION_CAPABILITIES``.
            arguments: Bounded values the row's label reads (a count, never
                an address or the person's words).
        """
        ...

    async def settle(self, ticket: Any, *, succeeded: bool) -> None:
        """Close the claimed row from what the act reported (None: nothing claimed)."""
        ...


class _Ignore:
    """The seam before the register claims it: nothing is recorded."""

    async def claim(self, *, user_id: Any, capability: str, arguments: dict[str, str]) -> Any:
        return None

    async def settle(self, ticket: Any, *, succeeded: bool) -> None:
        return None


_IGNORE: ActionRecorder = _Ignore()
_recorder: ActionRecorder = _IGNORE


def install_action_recorder(recorder: ActionRecorder) -> None:
    """Let the register record the acts the domains perform for a person.

    Called by the register's own module at import, and by the boot.

    Args:
        recorder: The implementation that claims and settles.
    """
    global _recorder  # noqa: PLW0603 — one seam, installed once, by its owner
    _recorder = recorder


def action_recorder_is_installed() -> bool:
    """Whether the register claimed the seam — for the boot's guard only."""
    return _recorder is not _IGNORE


class recorded_action:  # noqa: N801 — used as a context manager, named like one
    """One act, claimed on entry and settled on exit from ``succeeded``.

    Usage::

        async with recorded_action(user_id=..., capability=..., arguments={}) as act:
            ...  # the act
            act.succeeded = True

    An exception leaves ``succeeded`` False: the row settles as a failure and
    the exception goes on.
    """

    def __init__(self, *, user_id: Any, capability: str, arguments: dict[str, str]) -> None:
        """Name the act.

        Args:
            user_id: The person who asked.
            capability: One of ``USER_ACTION_CAPABILITIES``.
            arguments: Bounded values the label reads.
        """
        self._user_id = user_id
        self._capability = capability
        self._arguments = arguments
        self._recorder = _recorder
        self._ticket: Any = None
        self.succeeded = False

    async def __aenter__(self) -> recorded_action:
        self._ticket = await self._recorder.claim(
            user_id=self._user_id, capability=self._capability, arguments=self._arguments
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self._recorder.settle(self._ticket, succeeded=self.succeeded)


__all__ = [
    "EMAIL_SHARE_CAPABILITY",
    "PEER_IMAGE_SHARE_CAPABILITY",
    "USER_ACTION_CAPABILITIES",
    "ActionRecorder",
    "action_recorder_is_installed",
    "install_action_recorder",
    "recorded_action",
]
