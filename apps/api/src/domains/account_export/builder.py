"""Archive builder for full-account exports (security program D3).

Metadata-driven by design: the table set comes from ``user_data_map``
(ExportPolicy.FULL only — EXCLUDED tables can never leak by construction),
rows are serialized generically per table, secret-bearing columns are
redacted by an explicit, tested list, and encrypted location fields are
decrypted through their owning services (portability means readable data).
Binary files (attachments, RAG source uploads — arbitration A5) are copied
into the archive; derived data (chunks, vectors) is excluded.
"""

import asyncio
import json
import shutil
import tempfile
import zipfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.core.security.utils import decrypt_data
from src.domains.users.models import User
from src.domains.users.user_data_map import (
    TABLE_RULES,
    USER_COLUMNS,
    ExportPolicy,
    TableDataClass,
    UserColumnClass,
)
from src.infrastructure.database.session import Base, get_db_context

logger = structlog.get_logger(__name__)


class ExportTooLargeError(Exception):
    """The built archive exceeds the configured size cap (A5)."""


# Owner column when it is not ``user_id``.
_OWNER_COLUMN_OVERRIDES: dict[str, str] = {"skills": "owner_id"}

# Columns stripped from exported rows even on FULL tables: secrets, key
# material, or server-internal bookkeeping. Asserted by the exclusion test.
_REDACTED_COLUMNS: dict[str, frozenset[str]] = {
    "phone_calls": frozenset({"return_webhook_encrypted"}),
}

# Fernet-encrypted columns that MUST leave the archive decrypted
# (portability means readable data). Undecryptable values degrade to a
# marker instead of failing the whole export.
_DECRYPTED_COLUMNS: dict[str, frozenset[str]] = {
    "phone_calls": frozenset({"callee_phone"}),
}

# Tables whose rows resolve through a parent (no owner column of their own).
_VIA_PARENT: dict[str, tuple[str, str, str]] = {
    # table → (parent_table, local_fk_column, parent_owner_column)
    "conversation_messages": ("conversations", "conversation_id", "user_id"),
    "rag_drive_sources": ("rag_spaces", "space_id", "user_id"),
    "rag_documents": ("rag_spaces", "space_id", "user_id"),
}


def exportable_tables() -> list[str]:
    """Tables the archive must cover (FULL policy, user-scoped)."""
    return sorted(
        name
        for name, rule in TABLE_RULES.items()
        if rule.export is ExportPolicy.FULL
        and rule.data_class
        in (
            TableDataClass.USER_PURGED,
            TableDataClass.USER_CASCADE,
            TableDataClass.BILLING_RETAINED,
        )
    )


def _json_default(value: Any) -> str:
    """Serialize non-JSON scalars (UUID, datetime, bytes) readably."""
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _row_to_dict(table_name: str, row: Any) -> dict[str, Any]:
    """Serialize one SQLAlchemy Row with redaction + decryption applied."""
    redacted = _REDACTED_COLUMNS.get(table_name, frozenset())
    decrypted = _DECRYPTED_COLUMNS.get(table_name, frozenset())
    output: dict[str, Any] = {}
    for key, value in row._mapping.items():
        if key in redacted:
            continue
        if key in decrypted and isinstance(value, str) and value:
            # Best-effort decryption: an unreadable historical value must not
            # sink the whole archive.
            decrypted_value = "[undecryptable]"
            with suppress(Exception):
                decrypted_value = decrypt_data(value)
            output[key] = decrypted_value
            continue
        output[key] = value
    return output


async def _fetch_table_rows(table_name: str, user_id: UUID) -> list[dict[str, Any]]:
    """Fetch a user's rows for one exportable table (own session per call)."""
    table = Base.metadata.tables[table_name]

    async with get_db_context() as db:
        if table_name in _VIA_PARENT:
            parent_name, fk_column, parent_owner = _VIA_PARENT[table_name]
            parent = Base.metadata.tables[parent_name]
            subquery = select(parent.c.id).where(parent.c[parent_owner] == user_id)
            query = select(table).where(table.c[fk_column].in_(subquery))
        else:
            owner_column = _OWNER_COLUMN_OVERRIDES.get(table_name, "user_id")
            query = select(table).where(table.c[owner_column] == user_id)

        result = await db.execute(query)
        return [_row_to_dict(table_name, row) for row in result.fetchall()]


async def _fetch_user_profile(user_id: UUID) -> dict[str, Any]:
    """Export the users row: everything except SCRUBBED (secret/PII-heavy) columns."""
    async with get_db_context() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()
        exported: dict[str, Any] = {}
        for name, cls in USER_COLUMNS.items():
            if cls is UserColumnClass.SCRUBBED:
                continue
            exported[name] = getattr(user, name)
        return exported


def _render_markdown(table_name: str, rows: list[dict[str, Any]]) -> str | None:
    """Human-readable rendering for the narrative domains (spec: dual format)."""
    if table_name == "conversation_messages":
        lines = ["# Conversations\n"]
        for row in rows:
            role = row.get("role", "?")
            content = row.get("content") or ""
            stamp = row.get("created_at", "")
            lines.append(f"**{role}** ({stamp}):\n\n{content}\n\n---\n")
        return "\n".join(lines)
    if table_name == "journal_entries":
        lines = ["# Journal\n"]
        for row in rows:
            lines.append(f"## {row.get('created_at', '')}\n\n{row.get('content', '')}\n")
        return "\n".join(lines)
    if table_name == "memories":
        lines = ["# Memories\n"]
        for row in rows:
            lines.append(f"- {row.get('content', '')}\n")
        return "\n".join(lines)
    return None


def _copy_user_files(archive: zipfile.ZipFile, user_id: UUID) -> None:
    """Copy attachment + RAG source files into the archive (A5)."""
    for label, base_path in (
        ("files/attachments", settings.attachments_storage_path),
        ("files/rag_documents", settings.rag_spaces_storage_path),
    ):
        user_dir = Path(base_path) / str(user_id)
        if not user_dir.is_dir():
            continue
        for file_path in user_dir.rglob("*"):
            # Symlinks are excluded: uploads never create them, and following
            # one would embed content from OUTSIDE the user's directory.
            if file_path.is_file() and not file_path.is_symlink():
                arcname = f"{label}/{file_path.relative_to(user_dir)}"
                # Media is usually already compressed — store, don't deflate.
                archive.write(file_path, arcname=arcname, compress_type=zipfile.ZIP_STORED)


def _write_archive(
    tmp_path: Path,
    tables_payload: dict[str, list[dict[str, Any]]],
    profile: dict[str, Any],
    user_id: UUID,
) -> None:
    """Assemble the ZIP on disk (CPU/disk-bound — runs in a thread)."""
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "profile.json",
            json.dumps(profile, indent=2, ensure_ascii=False, default=_json_default),
        )
        for table_name, rows in tables_payload.items():
            archive.writestr(
                f"data/{table_name}.json",
                json.dumps(rows, indent=2, ensure_ascii=False, default=_json_default),
            )
            markdown = _render_markdown(table_name, rows)
            if markdown is not None:
                archive.writestr(f"readable/{table_name}.md", markdown)
        _copy_user_files(archive, user_id)


async def build_export_archive(user_id: UUID, job_id: UUID) -> tuple[Path, int]:
    """Build the full export archive for one user.

    Args:
        user_id: Account being exported.
        job_id: Export job id (names the archive).

    Returns:
        (final archive path, size in bytes).

    Raises:
        ExportTooLargeError: When the archive exceeds the configured cap.
    """
    tables_payload: dict[str, list[dict[str, Any]]] = {}
    for table_name in exportable_tables():
        tables_payload[table_name] = await _fetch_table_rows(table_name, user_id)
    profile = await _fetch_user_profile(user_id)

    exports_dir = Path(settings.exports_storage_path) / str(user_id)
    exports_dir.mkdir(parents=True, exist_ok=True)
    final_path = exports_dir / f"{job_id}.zip"

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        await asyncio.to_thread(_write_archive, tmp_path, tables_payload, profile, user_id)

        size = tmp_path.stat().st_size
        if size > settings.account_export_max_bytes:
            raise ExportTooLargeError(
                f"archive is {size} bytes > cap {settings.account_export_max_bytes}"
            )

        # Atomic hand-over: the download endpoint only ever sees complete files.
        await asyncio.to_thread(shutil.move, str(tmp_path), str(final_path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    logger.info(
        "account_export_archive_built",
        user_id=str(user_id),
        job_id=str(job_id),
        size_bytes=size,
        tables=len(tables_payload),
        built_at=datetime.now(UTC).isoformat(),
    )
    return final_path, size
