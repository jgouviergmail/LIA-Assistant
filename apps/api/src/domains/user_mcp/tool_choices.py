"""A person's choice for one tool of their MCP server (spec 2026-10-30 D6).

One row per (server, tool name): always ask, or never ask — the latter bound to the
declaration it was chosen against (``declaration_fingerprint``). Written one tool at a
time (an upsert per row, so two tabs on two tools never overwrite each other), never
copied by an install or a share (a copy is a new server, with no row here), removed
with its server (``ondelete=CASCADE``). A row for a tool the server no longer lists
stays, inert and unshown: it applies again only to the same tool with the same
declaration.
"""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import MCP_TOOL_CHOICE_NAME_MAX_LENGTH
from src.infrastructure.database.models import BaseModel


class UserMCPToolChoice(BaseModel):
    """The person's « always ask » or « never ask » for one tool of one server."""

    __tablename__ = "user_mcp_tool_choices"

    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
        comment="The server whose tool this is; the choice leaves with it.",
    )
    tool_name: Mapped[str] = mapped_column(
        String(MCP_TOOL_CHOICE_NAME_MAX_LENGTH),
        nullable=False,
        comment="The tool's raw name, as the server lists it.",
    )
    choice: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="always: ask before every call; never: follow the declaration, unasked.",
    )
    declaration_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="The tool's annotations and input schema when chosen; another one suspends a never.",
    )

    __table_args__ = (
        UniqueConstraint("server_id", "tool_name", name="uq_user_mcp_tool_choices_server_tool"),
        CheckConstraint("choice IN ('always', 'never')", name="ck_user_mcp_tool_choices_choice"),
    )
