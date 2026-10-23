"""The ``users`` columns a brand-new account starts with, on every sign-up door.

Three doors create an account — an e-mail registration and a first Google
sign-in (``AuthService``), and the installer's first account
(``scripts/data/create_admin.ensure_admin``, raw SQL). The first two used to
restate the same defaults inline and the third left them to the column
defaults — NULL for the rhythm and the grid. They now spread ONE declaration,
so a default added here reaches all three: a default one door forgets is a
default some accounts never get.

Owner decision 2026-10-22: a new account opens on a dashboard showing the
weather card alone, and with OCCASIONAL exchanges (ADR-311) whatever
``REACT_CROSS_TURN_CACHE_ENABLED`` says for the accounts that never chose —
measured that day, dev and production both resolved them to frequent. The
value is stored like a choice: the settings show it selected, and the person
changes it there. Accounts created before this decision keep what they had.
"""

from __future__ import annotations

from typing import Any

from src.core.exchange_rhythm import ExchangeRhythm
from src.domains.briefing.preferences import new_account_briefing_preferences

#: The exchange rhythm a brand-new account starts with (ADR-311 amendment 2026-10-22).
NEW_ACCOUNT_EXCHANGE_RHYTHM = ExchangeRhythm.OCCASIONAL


def new_account_columns() -> dict[str, Any]:
    """The column values every new account is created with.

    Returns:
        A new dict on every call: the JSONB value it carries is never shared
        between two accounts.
    """
    return {
        # Long-term memory enabled by default.
        "memory_enabled": True,
        # Default display mode: HTML data cards.
        "response_display_mode": "cards",
        "exchange_rhythm": NEW_ACCOUNT_EXCHANGE_RHYTHM.value,
        "briefing_preferences": new_account_briefing_preferences(),
    }


__all__ = ["NEW_ACCOUNT_EXCHANGE_RHYTHM", "new_account_columns"]
