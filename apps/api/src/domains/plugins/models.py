"""Agent Plugins persistence models (ADR-225).

``user_plugins`` records each installed plugin instance (one row per
(user, plugin name)); the components it brought in are ordinary rows in
``skills`` and ``user_mcp_servers`` carrying a nullable ``plugin_id``
provenance link (declared on their own models).

``ON DELETE SET NULL`` on the provenance link is the deliberate safety net: a
raw ``user_plugins`` row deletion turns plugin components back into ordinary
manual components instead of silently cascading user data away. The clean
group uninstall (DB rows + disk trees) is service-driven.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import AGENT_PLUGINS_NAME_MAX_LENGTH
from src.infrastructure.database.models import BaseModel


class UserPlugin(BaseModel):
    """One installed Agent Plugins package for one user.

    The plugin root directory is kept on disk under
    ``{plugins_users_path}/{user_id}/{name}/`` (ADR-225 arbitrage D); this row
    is the DB source of truth for its identity, displayed metadata and the
    spec version it targets.
    """

    __tablename__ = "user_plugins"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Owner of this installed plugin instance",
    )
    name: Mapped[str] = mapped_column(
        String(AGENT_PLUGINS_NAME_MAX_LENGTH),
        nullable=False,
        comment="Plugin name from the manifest (agent-plugins.org §5.5)",
        doc="Plugin name from the manifest (§5.5 constraints, unique per user)",
    )
    version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Manifest version string (SemVer recommended, not enforced — §5.4)",
    )
    description: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Manifest description for display",
    )
    manifest: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full validated plugin.json manifest (unknown fields stripped)",
        doc="Full validated plugin.json manifest (unknown fields stripped)",
    )
    spec_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Agent Plugins specification version targeted by the package",
        doc="Agent Plugins specification version targeted by the package",
    )

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_plugins_user_name"),)

    def __repr__(self) -> str:
        return (
            f"<UserPlugin(id={self.id}, user_id={self.user_id}, "
            f"name='{self.name}', version='{self.version}')>"
        )
