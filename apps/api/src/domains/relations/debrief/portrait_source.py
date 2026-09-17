"""The relationship debriefs, as the user portrait reads them (2026-09-16, part B).

Three gates (the deployment ceiling, the operator switch, the person's own
preference); READY rows only, under the injection age the settings publish,
measured against the reader's LOCAL day (ADR-269); the headline and where
things stand, clamped; the date, so the model treats the line as DATED. A
read that fails is ``unavailable``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.time_utils import resolve_user_timezone
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.relations.debrief.repository import RelationDebriefRepository
from src.domains.relations.debrief.service import read_of
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    SourceBudget,
    clamp_item,
    empty_section,
    install_portrait_source,
    portrait_lines,
)
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "relation_debriefs"


async def read_relation_debriefs(
    *, user_id: UUID, language: str, budget: SourceBudget
) -> PortraitSourceSection:
    """Render the person's fresh relationship debriefs for the consolidation prompt.

    Args:
        user_id: The account.
        language: Unused — a debrief is already written in the person's language.
        budget: How many items, how long each.

    Returns:
        The section; never raises.
    """
    try:
        if not (
            settings.relation_debrief_enabled
            and await is_capability_enabled(PlatformCapability.RELATION_DEBRIEF)
        ):
            return empty_section(KEY, "disabled")
        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if user is None or not getattr(user, "relation_debrief_enabled", True):
                return empty_section(KEY, "disabled")
            today = datetime.now(resolve_user_timezone(user)).date()
            rows = await RelationDebriefRepository(db).list_injectable(
                user_id,
                not_before=today - timedelta(days=settings.relation_debrief_injection_max_age_days),
            )
        total = len(rows)
        if not total or budget.max_items <= 0:
            return empty_section(KEY, "empty", total=total)
        lines = portrait_lines()
        items: list[str] = []
        for row in rows[: budget.max_items]:
            body = read_of(row).body
            if body is None:
                continue
            items.append(
                lines["debriefs_item"].format(
                    person=clamp_item(row.display_name, budget.item_max_chars),
                    date=row.generated_for.isoformat(),
                    headline=clamp_item(body.headline, budget.item_max_chars),
                    where_we_stand=clamp_item(body.where_we_stand, budget.item_max_chars),
                )
            )
        if not items:
            return empty_section(KEY, "empty", total=total)
        header = lines["debriefs_header"].format(shown=len(items), total=total)
        return PortraitSourceSection(
            key=KEY, status="used", text="\n".join([header, *items]), used=len(items), total=total
        )
    except Exception as exc:  # noqa: BLE001 — a blind source is named, never read as empty
        logger.warning("portrait_source_unavailable", source=KEY, error_type=type(exc).__name__)
        return empty_section(KEY, "unavailable")


#: Where this source's freshness is read (the consolidation's eligibility).
FRESHNESS = FreshnessProbe(
    table="relation_debriefs", user_column="user_id", stamp_column="generated_at"
)

# Installed at import for every path that does not go through the boot; the
# boot INSTALLS explicitly too, because an already-imported module wires
# nothing (ADR-270, the ticket-release precedent).
install_portrait_source(KEY, read_relation_debriefs, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_relation_debriefs"]
