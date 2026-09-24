"""How long Telegram's flood control asked us to wait.

python-telegram-bot 22.2 deprecated reading ``RetryAfter.retry_after`` as a
number: a future major version returns a ``datetime.timedelta``, and until then
every numeric read emits a ``PTBDeprecationWarning``. The package opts in to the
new shape once (``PTB_TIMEDELTA``, see the package docstring); this module is
the one reader of the delay and accepts both shapes, because an operator may
still set the variable to ``false``.
"""

from __future__ import annotations

from datetime import timedelta

from telegram.error import RetryAfter


def retry_after_seconds(exc: RetryAfter) -> float:
    """Return the delay Telegram asked for, in seconds.

    Args:
        exc: The flood-control error Telegram raised.

    Returns:
        The delay in seconds, whichever representation python-telegram-bot
        uses for it.
    """
    delay = exc.retry_after
    if isinstance(delay, timedelta):
        return delay.total_seconds()
    return float(delay)
