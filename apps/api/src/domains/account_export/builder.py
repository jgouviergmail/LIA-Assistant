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
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import or_, select

from src.core.config import settings
from src.core.constants import DEFAULT_LANGUAGE
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
_OWNER_COLUMN_OVERRIDES: dict[str, str] = {
    "skills": "owner_id",
    # Peers: deliberately ONE-sided scopes where the other side would leak.
    # peer_blocks by blocker only — an archive must never reveal who blocked
    # the requester (hide-existence, peers spec §12.2). Shares by owner only —
    # incoming shares are the OTHER user's choices, not the requester's data.
    "peer_blocks": "blocker_id",
    "peer_domain_shares": "owner_user_id",
}

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
    # ADR-258: the meeting transcript rests encrypted (third parties' speech)
    # and leaves the archive readable — it is the user's own record.
    "meetings": frozenset({"transcript_encrypted"}),
    # ADR-263: the ledger rests encrypted (a label names people, a result can
    # quote a third party) and leaves the archive readable — portability means
    # readable data, and these are the user's own actions.
    "agent_effects": frozenset({"label", "result_payload"}),
}

# Tables whose rows resolve through a parent (no owner column of their own).
_VIA_PARENT: dict[str, tuple[str, str, str]] = {
    # table → (parent_table, local_fk_column, parent_owner_column)
    "conversation_messages": ("conversations", "conversation_id", "user_id"),
    "rag_drive_sources": ("rag_spaces", "space_id", "user_id"),
    "rag_documents": ("rag_spaces", "space_id", "user_id"),
}

# Columns of a two-sided row that belong to ONE participant only. The archive
# gives each side THEIR OWN words and never the other's: on a relayed message
# the sender wrote the directive and the recipient received their assistant's
# rendering, and crossing the two would undo the relay itself (ADR-186 §2) —
# the recipient would read the raw instruction instead of the wording they
# actually got, and the sender would discover the other assistant's tone.
# Same doctrine as `_OWNER_COLUMN_OVERRIDES` above, one column finer.
_SIDE_SCOPED_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    # table → ((column, the column naming its rightful owner), …)
    "peer_messages": (("content", "sender_id"), ("delivered_text", "recipient_id")),
}

# Two-sided tables (peers program): a row belongs to the archive when the
# requester sits on EITHER column — connections, relayed correspondence and
# the cross-user read audit are genuinely shared records.
_TWO_SIDED: dict[str, tuple[str, str]] = {
    # table → (side_a_column, side_b_column)
    "peer_connections": ("user_a_id", "user_b_id"),
    "peer_messages": ("sender_id", "recipient_id"),
    "peer_access_log": ("accessor_id", "owner_id"),
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


def _row_to_dict(table_name: str, row: Any, user_id: UUID) -> dict[str, Any]:
    """Serialize one SQLAlchemy Row with redaction + decryption applied.

    Args:
        table_name: Table the row came from.
        row: The SQLAlchemy Row.
        user_id: The requester — decides which side-scoped columns are theirs.
    """
    redacted = _REDACTED_COLUMNS.get(table_name, frozenset())
    decrypted = _DECRYPTED_COLUMNS.get(table_name, frozenset())
    # Columns of this row that belong to the OTHER participant.
    not_mine = {
        column
        for column, owner_column in _SIDE_SCOPED_COLUMNS.get(table_name, ())
        if row._mapping.get(owner_column) != user_id
    }
    output: dict[str, Any] = {}
    for key, value in row._mapping.items():
        if key in redacted or key in not_mine:
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
        elif table_name in _TWO_SIDED:
            side_a, side_b = _TWO_SIDED[table_name]
            query = select(table).where(or_(table.c[side_a] == user_id, table.c[side_b] == user_id))
        else:
            owner_column = _OWNER_COLUMN_OVERRIDES.get(table_name, "user_id")
            query = select(table).where(table.c[owner_column] == user_id)

        result = await db.execute(query)
        return [_row_to_dict(table_name, row, user_id) for row in result.fetchall()]


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


def _render_conversations(rows: list[dict[str, Any]], language: str) -> str:
    """The conversation, as it was read."""
    lines = ["# Conversations\n"]
    for row in rows:
        role = row.get("role", "?")
        content = row.get("content") or ""
        stamp = row.get("created_at", "")
        lines.append(f"**{role}** ({stamp}):\n\n{content}\n\n---\n")
    return "\n".join(lines)


def _render_journal(rows: list[dict[str, Any]], language: str) -> str:
    """The personal journal, newest entries as written."""
    lines = ["# Journal\n"]
    for row in rows:
        lines.append(f"## {row.get('created_at', '')}\n\n{row.get('content', '')}\n")
    return "\n".join(lines)


def _render_memories(rows: list[dict[str, Any]], language: str) -> str:
    """What LIA remembers, one line each."""
    lines = ["# Memories\n"]
    for row in rows:
        lines.append(f"- {row.get('content', '')}\n")
    return "\n".join(lines)


def _render_effects(rows: list[dict[str, Any]], language: str) -> str:
    """The action register, in the reader's language (ADR-263).

    The stored label is ``{i18n_key, values}``, never a sentence, so it is
    rendered HERE — an archive requested in German reads in German about an
    action taken while the interface was in French.

    Refused and abandoned effects are kept: a register that showed only what
    succeeded would be an advertisement, not a record.
    """
    from src.core.i18n_effects import render_effect_heading, render_effect_label

    lines = [f"# {render_effect_heading(language)}\n"]
    for row in rows:
        label = row.get("label")
        if isinstance(label, str):
            try:
                label = json.loads(label)
            except TypeError, ValueError:
                label = None
        sentence = render_effect_label(label, language)
        status = row.get("status", "?")
        stamp = row.get("claimed_at", "")
        marker = {"succeeded": "✓", "failed": "✗", "refused": "⊘"}.get(str(status), "·")
        lines.append(f"- {marker} {stamp} — {sentence} ({status})")
    return "\n".join(lines) + "\n"


def _render_treatments(rows: list[dict[str, Any]], language: str) -> str:
    """The consultation register, in the reader's language (ADR-263, lot 4).

    The companion of :func:`_render_effects`, and the one that answers the
    question a person actually asks: not *what did the assistant do* but *what
    did it look at*. Its wording is the DOMAIN — "E-mails", never
    ``get_email_details_tool`` — because a consultation records the capability
    and nothing of the call. The tool name travels beside it, so the technical
    half is present without being the half a reader must decode.

    Args:
        rows: The register's rows, oldest first.
        language: The reader's language.

    Returns:
        One markdown line per consultation.
    """
    from src.core.i18n_treatments import render_treatment_domain, render_treatment_heading
    from src.domains.agents.effects.treatment_labels import treatment_domain

    lines = [f"# {render_treatment_heading(language)}\n"]
    for row in rows:
        tool_name = str(row.get("tool_name", ""))
        domain = render_treatment_domain(treatment_domain(tool_name), language)
        marker = "✓" if row.get("outcome") == "ok" else "✗"
        duration = row.get("duration_ms")
        suffix = f" — {duration} ms" if isinstance(duration, int) else ""
        lines.append(f"- {marker} {row.get('occurred_at', '')} — {domain} ({tool_name}){suffix}")
    return "\n".join(lines) + "\n"


def _render_decisions(rows: list[dict[str, Any]], language: str) -> str:
    """The turns themselves, in the reader's language (ADR-263, lot 6).

    The archive already carries the conversations; what this adds is what a
    transcript shows badly — the turns that did NOT end in an answer, and the
    ones that were stopped for a confirmation and resumed.

    Args:
        rows: The register's rows, oldest first.
        language: The reader's language.

    Returns:
        One markdown line per turn.
    """
    from src.core.i18n_treatments import (
        render_decision_heading,
        render_decision_outcome,
        render_stop_reason,
    )

    lines = [f"# {render_decision_heading(language)}\n"]
    for row in rows:
        outcome = render_decision_outcome(str(row.get("outcome", "")), language)
        stopped = row.get("stop_reason")
        if stopped:
            outcome = f"{outcome} ({render_stop_reason(str(stopped), language)})"
        segments = row.get("segments")
        resumed = f" ×{segments}" if isinstance(segments, int) and segments > 1 else ""
        steps = row.get("plan_step_count")
        plan = f" — {steps}" if isinstance(steps, int) and steps else ""
        lines.append(
            f"- {row.get('started_at', '')} — {row.get('execution_mode', '')}"
            f"{plan} → {outcome}{resumed}"
        )
    return "\n".join(lines) + "\n"


def _render_chain(rows: list[dict[str, Any]], language: str) -> str:
    """The chain, as an ATTESTATION rather than ten thousand hashes.

    The raw entries travel in the structured half of the archive, where a tool
    can walk them. What a person needs from them is three facts: how much of
    their history is sealed, until when, and the one value to write down —
    comparing that head hash later is what detects a rewrite of the chain AND
    its rows at once.

    Args:
        rows: The chain's entries, oldest first.
        language: The reader's language.

    Returns:
        A short attestation; hash lines would be noise nobody can act on.
    """
    from src.core.i18n_treatments import render_chain_attestation

    return render_chain_attestation(
        language,
        entries=len(rows),
        sealed_until=str(rows[-1].get("occurred_at", "")) if rows else "",
        head_hash=str(rows[-1].get("entry_hash", "")) if rows else "",
    )


#: table → renderer. A dispatch table rather than an ``if`` cascade, the same
#: shape ``drafts/preview_renderer`` uses: a fourth branch is where a cascade
#: starts costing complexity, and every renderer here is one small function.
_MARKDOWN_RENDERERS: dict[str, Callable[[list[dict[str, Any]], str], str]] = {
    "conversation_messages": _render_conversations,
    "journal_entries": _render_journal,
    "memories": _render_memories,
    "agent_effects": _render_effects,
    "agent_treatments": _render_treatments,
    "agent_decisions": _render_decisions,
    "ledger_chain": _render_chain,
}


def _render_markdown(
    table_name: str, rows: list[dict[str, Any]], language: str = DEFAULT_LANGUAGE
) -> str | None:
    """Human-readable rendering for the narrative domains (spec: dual format).

    Args:
        table_name: The exported table.
        rows: Its rows, already decrypted and redacted.
        language: The reader's language — only the two registers vary with it
            (their wording is ours); the other domains export the user's own
            words unchanged.

    Returns:
        The markdown, or None for a table with no readable form.
    """
    renderer = _MARKDOWN_RENDERERS.get(table_name)
    return renderer(rows, language) if renderer else None


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
            markdown = _render_markdown(
                table_name, rows, str(profile.get("language") or DEFAULT_LANGUAGE)
            )
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
