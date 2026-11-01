"""What the page reads about a server's confirmations, and a tool's own choice (spec 2026-10-30).

The synthesis is computed by ``behavior.py`` from what is stored; this service reads it
— the server row through its ownership check, the tools' choices in one query — and
records a tool's choice: bound to the declaration the server's last catalogue lists
now, refused for a tool it does not list (a renamed tool's choice applies to nothing).
The caller commits.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, raise_structured_validation_error
from src.domains.user_mcp.behavior import (
    BehaviorInputs,
    behavior_inputs,
    catalogue_tool,
    describe_server_behavior,
    server_preview,
    strategy_preview,
)
from src.domains.user_mcp.behavior_schemas import (
    BehaviorPreview,
    BehaviorPreviewRequest,
    ServerBehavior,
    StrategyPreview,
)
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.service import UserMCPServerService
from src.domains.user_mcp.tool_choice_repository import UserMCPToolChoiceRepository
from src.domains.users.models import User
from src.infrastructure.mcp.confirmation import (
    StoredToolChoice,
    ToolChoice,
    declaration_fingerprint,
)

logger = structlog.get_logger(__name__)


class MCPBehaviorService:
    """The synthesis of the person's servers, and the choices it is made of."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.servers = UserMCPServerService(db)
        self.choices = UserMCPToolChoiceRepository(db)

    async def inputs(self, server: UserMCPServer) -> BehaviorInputs:
        """What the synthesis of one server reads: the row and its tools' choices."""
        stored: Mapping[UUID, dict[str, StoredToolChoice]] = await self.choices.choices_for(
            [server.id]
        )
        return behavior_inputs(server, stored.get(server.id))

    async def account_inputs(self, owner_id: UUID) -> list[BehaviorInputs]:
        """Every server of the account (a disabled one may be enabled later), choices read once."""
        servers = await self.servers.list_servers(owner_id)
        stored = await self.choices.choices_for([server.id for server in servers])
        return [behavior_inputs(server, stored.get(server.id)) for server in servers]

    async def behavior(self, server_id: UUID, user: User) -> ServerBehavior:
        """What one of the person's servers will do, as stored.

        Args:
            server_id: The server.
            user: The person, owner of the server.

        Returns:
            The synthesis.
        """
        server = await self.servers.get_with_ownership_check(server_id, user.id)
        return describe_server_behavior(await self.inputs(server), user.mcp_hitl_required)

    async def server_preview(
        self, server_id: UUID, user: User, request: BehaviorPreviewRequest
    ) -> BehaviorPreview:
        """What one server would do under the form's candidates; nothing is written.

        Args:
            server_id: The server.
            user: The person, owner of the server.
            request: The candidate values.

        Returns:
            The candidate synthesis and the questions it would lose.
        """
        server = await self.servers.get_with_ownership_check(server_id, user.id)
        return server_preview(await self.inputs(server), user.mcp_hitl_required, request)

    async def strategy_preview(self, user: User, candidate: bool | None) -> StrategyPreview:
        """What a change of the account's strategy would stop LIA asking; nothing is written.

        Args:
            user: The person.
            candidate: The candidate strategy (None: back to the instance default).

        Returns:
            The questions lost across every server of the account.
        """
        return strategy_preview(
            await self.account_inputs(user.id), user.mcp_hitl_required, candidate
        )

    async def ask_always(self, server: UserMCPServer, tool_names: Iterable[str]) -> bool:
        """Record « always ask » for tools of the server's last catalogue (spec 2026-10-30 D7).

        The assistant's card writes no other choice; the caller has judged the change.

        Args:
            server: The person's server, locked by the caller.
            tool_names: Raw tool names, as the last catalogue lists them.

        Returns:
            Whether a choice changed.

        Raises:
            ResourceConflictError: The catalogue no longer lists one of them.
        """
        names = tuple(tool_names)
        if not names:
            return False
        inputs = await self.inputs(server)
        changed = False
        for name in names:
            tool = catalogue_tool(inputs, name)
            if tool is None:
                raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
            stored = inputs.tool_choices.get(name)
            if stored is not None and stored.choice is ToolChoice.ALWAYS:
                continue
            await self.choices.set_choice(
                server.id, name, ToolChoice.ALWAYS, declaration_fingerprint(tool)
            )
            changed = True
        return changed

    async def set_tool_choice(
        self, server_id: UUID, user: User, tool_name: str, choice: ToolChoice | None
    ) -> ServerBehavior:
        """Record the person's choice for one tool, then say what the server will do.

        Args:
            server_id: The server.
            user: The person, owner of the server.
            tool_name: The tool's raw name, as the last catalogue lists it.
            choice: Always or never; None returns the tool to the levels below.

        Returns:
            The synthesis with the choice applied.

        Raises:
            StructuredValidationError: The last catalogue lists no such tool.
        """
        server = await self.servers.get_with_ownership_check(server_id, user.id)
        tool = catalogue_tool(await self.inputs(server), tool_name)
        if tool is None:
            raise_structured_validation_error(
                error_type="tool_not_in_catalogue",
                loc=["body", "tool_name"],
                msg="The server's last catalogue lists no tool of this name.",
                input_value=None,
                ctx={},
            )
        if choice is None:
            await self.choices.clear_choice(server.id, tool_name)
        else:
            await self.choices.set_choice(
                server.id, tool_name, choice, declaration_fingerprint(tool)
            )
        logger.info(
            "mcp_tool_choice_recorded",
            server_id=str(server.id),
            choice=choice.value if choice else "default",
        )
        return describe_server_behavior(await self.inputs(server), user.mcp_hitl_required)
