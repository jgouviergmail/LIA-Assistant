"""Initial operator settings a demonstrator starts with.

Some defaults that are right for a private instance are wrong for one whose
purpose is to be looked at. The debug panel is the clearest case: off
everywhere else because it exposes a run's internals, and exactly what a
visitor should see here — the routing, the plan, the tokens spent.

These are INITIAL values, written once when nothing has been decided. They are
never re-applied: an operator who switches one off must find it off after a
restart, or the switch is a decoration. That is the difference with the LLM
configuration, which is rewritten at every boot because the instance cannot
answer at all without it.

Created: 2026-08-07 (live-demonstrator programme, first bring-up)
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select

from src.domains.system_settings.models import SystemSetting, SystemSettingKey

logger = structlog.get_logger(__name__)

#: Settings a demonstrator starts with, and why each differs from the product
#: default. Adding one is a decision about what visitors see.
DEMO_SETTING_DEFAULTS: dict[SystemSettingKey, str] = {
    # Showing the reasoning IS the demonstration.
    SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED: "true",
}


async def apply_demo_setting_defaults(session: Any) -> int:
    """Write the demonstrator's initial settings, without overwriting choices.

    Args:
        session: Database session; the caller owns the transaction.

    Returns:
        How many settings were created. Zero once an operator has decided.
    """
    rows = (await session.execute(select(SystemSetting))).scalars().all()
    known = {str(row.key) for row in rows}

    written = 0
    for key, value in DEMO_SETTING_DEFAULTS.items():
        if str(key.value) in known or str(key) in known:
            continue
        session.add(
            SystemSetting(
                key=key,
                value=value,
                change_reason="demo instance initial default",
            )
        )
        written += 1

    if written:
        logger.info("demo_setting_defaults_applied", settings=written)
    return written
