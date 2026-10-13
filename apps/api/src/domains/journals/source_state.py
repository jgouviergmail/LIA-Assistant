"""Cheap source lineage, including deletion, gates and time-based expiry.

No source domain is imported: each installs its table and permission probe.
Qualified content describes the whole source; exposure bookkeeping does not
invalidate it. A source may also bind related tables. The whole record is
read (2026-10-12), so no selection page exists to bind.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import String, Table, cast, func, literal, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.config import settings
from src.core.time_utils import resolve_user_timezone
from src.domains.journals.constants import JOURNAL_PORTRAIT_POLICY_VERSION
from src.domains.shared.portrait_sources import FreshnessProbe, installed_portrait_sources
from src.domains.users.models import User
from src.infrastructure.database.models import Base


def _semantic_value(table: Table, field: str | tuple[str, ...]) -> ColumnElement[Any]:
    """Resolve a declared column or JSON path without importing its domain."""
    if isinstance(field, str):
        return table.c[field]
    value: ColumnElement[Any] = table.c[field[0]]
    for key in field[1:]:
        value = value[key]
    return value


def _identity_columns(table: Table, probe: FreshnessProbe) -> list[ColumnElement[Any]]:
    """Canonical per-row hashes preserve all edits and distinguish NULL from text."""
    if probe.semantic_columns is not None:
        values = [table.c.id, *(_semantic_value(table, field) for field in probe.semantic_columns)]
        row_hash = func.md5(cast(func.jsonb_build_array(*values), String))
        digest = func.md5(func.string_agg(row_hash, aggregate_order_by(literal(""), table.c.id)))
        return [func.count(), digest]
    columns: list[ColumnElement[Any]] = [func.count(), func.max(table.c[probe.stamp_column])]
    if "updated_at" in table.c and probe.stamp_column != "updated_at":
        columns.append(func.max(table.c.updated_at))
    versions = [table.c.id, table.c[probe.stamp_column]]
    versions.extend(
        table.c[name]
        for name in ("updated_at", "status", "generated_for")
        if name in table.c and name != probe.stamp_column
    )
    row_version = func.concat_ws("|", *[cast(column, String) for column in versions])
    columns.append(
        func.md5(func.string_agg(row_version, aggregate_order_by(literal(","), table.c.id)))
    )
    return columns


async def _source_identity(
    db: AsyncSession, user_id: UUID, probe: FreshnessProbe
) -> dict[str, Any]:
    """Read the whole record's identity on the owning transaction."""
    table = Base.metadata.tables[probe.table]
    row = (
        await db.execute(
            select(*_identity_columns(table, probe)).where(table.c[probe.user_column] == user_id)
        )
    ).one()
    identity: dict[str, Any] = {"count": row[0], "versions": row[-1]}
    if probe.semantic_columns is None:
        identity["stamps"] = [stamp.isoformat() if stamp else None for stamp in row[1:-1]]
    if probe.related_probes:
        identity["related"] = {
            related.table: await _source_identity(db, user_id, related)
            for related in probe.related_probes
        }
    return identity


async def portrait_source_state(db: AsyncSession, user: User) -> dict[str, Any]:
    """Return a JSON-serializable identity of all currently authorized sources."""
    state: dict[str, Any] = {
        "_rendering": {
            "language": user.language,
            "timezone": user.timezone,
            "portrait_policy": JOURNAL_PORTRAIT_POLICY_VERSION,
            "full_max_tokens": settings.journal_portrait_full_max_tokens,
            "brief_max_tokens": settings.journal_portrait_brief_max_tokens,
            "with_history": user.journal_consolidation_with_history,
            "max_total_chars": user.journal_max_total_chars,
            "max_entry_chars": user.journal_max_entry_chars,
            "personality_id": str(user.personality_id) if user.personality_id else None,
            "sources_window_fraction": settings.journal_consolidation_sources_window_fraction,
        }
    }
    for key, (_reader, probe) in installed_portrait_sources().items():
        allowed = await probe.allowed(user.id) if probe.allowed else True
        item: dict[str, Any] = {"allowed": allowed}
        if allowed:
            item.update(await _source_identity(db, user.id, probe))
            if probe.expires_daily:
                item["local_day"] = datetime.now(resolve_user_timezone(user)).date().isoformat()
                item["max_age_days"] = settings.relation_debrief_injection_max_age_days
        state[key] = item
    return state
