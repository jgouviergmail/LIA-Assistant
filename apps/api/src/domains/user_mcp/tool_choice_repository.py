"""Reads and writes of the per-tool confirmation choices (spec 2026-10-30 D6).

A choice is written one tool at a time: the (server, tool) unique constraint is the
identity and an upsert honours it without a race between a read and an insert, so two
tabs on two tools both persist. Reads are forgiving — a stored value outside the
vocabulary is skipped, never a failed run — and serve every server of a run at once.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.user_mcp.tool_choices import UserMCPToolChoice
from src.infrastructure.mcp.confirmation import StoredToolChoice, ToolChoice


class UserMCPToolChoiceRepository(BaseRepository[UserMCPToolChoice]):
    """The per-tool choices of the person's servers."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, UserMCPToolChoice)

    async def choices_for(
        self, server_ids: Sequence[UUID]
    ) -> dict[UUID, dict[str, StoredToolChoice]]:
        """Every stored choice of these servers, by server then by tool name.

        Args:
            server_ids: The servers of a run, or of one synthesis.

        Returns:
            The readable choices; a server with none is absent.
        """
        if not server_ids:
            return {}
        statement = select(
            UserMCPToolChoice.server_id,
            UserMCPToolChoice.tool_name,
            UserMCPToolChoice.choice,
            UserMCPToolChoice.declaration_fingerprint,
        ).where(UserMCPToolChoice.server_id.in_(server_ids))
        choices: dict[UUID, dict[str, StoredToolChoice]] = {}
        for server_id, tool_name, choice, fingerprint in (await self.db.execute(statement)).all():
            if choice not in ToolChoice:
                continue
            choices.setdefault(server_id, {})[tool_name] = StoredToolChoice(
                ToolChoice(choice), fingerprint
            )
        return choices

    async def set_choice(
        self, server_id: UUID, tool_name: str, choice: ToolChoice, fingerprint: str
    ) -> None:
        """Record the person's choice for one tool, replacing an older one.

        Args:
            server_id: The server, already checked as the person's.
            tool_name: The tool's raw name, already checked against the catalogue.
            choice: Always or never.
            fingerprint: The tool's declaration fingerprint now.
        """
        statement = (
            pg_insert(UserMCPToolChoice)
            .values(
                server_id=server_id,
                tool_name=tool_name,
                choice=choice.value,
                declaration_fingerprint=fingerprint,
            )
            .on_conflict_do_update(
                constraint="uq_user_mcp_tool_choices_server_tool",
                set_={
                    "choice": choice.value,
                    "declaration_fingerprint": fingerprint,
                    "updated_at": datetime.now(UTC),
                },
            )
        )
        await self.db.execute(statement)

    async def clear_choice(self, server_id: UUID, tool_name: str) -> None:
        """Return one tool to the levels below (« by default »).

        Args:
            server_id: The server, already checked as the person's.
            tool_name: The tool's raw name.
        """
        await self.db.execute(
            delete(UserMCPToolChoice).where(
                UserMCPToolChoice.server_id == server_id,
                UserMCPToolChoice.tool_name == tool_name,
            )
        )
