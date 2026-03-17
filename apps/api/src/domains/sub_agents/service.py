"""
Sub-Agents service for business logic.

Handles CRUD operations, template instantiation, ownership verification,
per-user limits, and execution recording.
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    SUBAGENT_MAX_CONSECUTIVE_FAILURES_DEFAULT,
    SUBAGENT_MAX_PER_USER_DEFAULT,
)
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError, ValidationError
from src.domains.sub_agents.constants import (
    SUBAGENT_TEMPLATES,
    get_template_by_id,
)
from src.domains.sub_agents.models import SubAgent, SubAgentCreatedBy, SubAgentStatus
from src.domains.sub_agents.repository import SubAgentRepository
from src.domains.sub_agents.schemas import (
    SubAgentCreate,
    SubAgentCreateFromTemplate,
    SubAgentUpdate,
)

logger = structlog.get_logger(__name__)


class SubAgentService:
    """Service for sub-agent management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = SubAgentRepository(db)

    # ========================================================================
    # Ownership check
    # ========================================================================

    async def get_with_ownership_check(
        self,
        subagent_id: UUID,
        user_id: UUID,
    ) -> SubAgent:
        """Get sub-agent with ownership verification.

        Raises:
            ResourceNotFoundError: If sub-agent doesn't exist or belongs to another user.
        """
        subagent = await self.repository.get_by_id(subagent_id)
        if not subagent or subagent.user_id != user_id:
            raise ResourceNotFoundError("sub_agent", str(subagent_id))
        return subagent

    # ========================================================================
    # CRUD
    # ========================================================================

    async def create(
        self,
        user_id: UUID,
        data: SubAgentCreate,
        created_by: str = SubAgentCreatedBy.USER.value,
        template_id: str | None = None,
    ) -> SubAgent:
        """Create a new sub-agent.

        Enforces per-user limit and unique name constraint.

        Args:
            user_id: Owner user ID.
            data: Sub-agent creation data.
            created_by: Origin ('user' or 'assistant').
            template_id: Template ID if created from a template.

        Raises:
            ValidationError: If user has reached the maximum limit.
            ResourceConflictError: If name already exists for this user.
        """
        max_per_user = getattr(settings, "subagent_max_per_user", SUBAGENT_MAX_PER_USER_DEFAULT)

        count = await self.repository.count_for_user(user_id)
        if count >= max_per_user:
            raise ValidationError(f"Maximum of {max_per_user} sub-agents per user")

        existing = await self.repository.get_by_name_for_user(user_id, data.name)
        if existing:
            raise ResourceConflictError(
                "sub_agent", f"A sub-agent named '{data.name}' already exists"
            )

        subagent = await self.repository.create(
            {
                "user_id": user_id,
                "name": data.name,
                "description": data.description,
                "system_prompt": data.system_prompt,
                "personality_instruction": data.personality_instruction,
                "icon": data.icon,
                "llm_provider": data.llm_provider,
                "llm_model": data.llm_model,
                "llm_temperature": data.llm_temperature,
                "max_iterations": data.max_iterations,
                "timeout_seconds": data.timeout_seconds,
                "skill_ids": data.skill_ids,
                "allowed_tools": data.allowed_tools,
                "blocked_tools": data.blocked_tools,
                "context_instructions": data.context_instructions,
                "is_enabled": True,
                "status": SubAgentStatus.READY.value,
                "created_by": created_by,
                "template_id": template_id,
            }
        )

        logger.info(
            "subagent_created",
            subagent_id=str(subagent.id),
            user_id=str(user_id),
            name=data.name,
            created_by=created_by,
            template_id=template_id,
        )

        return subagent

    async def create_from_template(
        self,
        user_id: UUID,
        template_id: str,
        overrides: SubAgentCreateFromTemplate | None = None,
        created_by: str = SubAgentCreatedBy.USER.value,
    ) -> SubAgent:
        """Create a sub-agent from a pre-defined template.

        Raises:
            ValidationError: If template_id is unknown or limit reached.
            ResourceConflictError: If name already exists.
        """
        template = get_template_by_id(template_id)
        if template is None:
            raise ValidationError(f"Unknown template: '{template_id}'")

        name = template["name_default"]
        description = template["description_default"]
        system_prompt = template["system_prompt"]
        icon = template["icon"]

        if overrides:
            if overrides.name is not None:
                name = overrides.name
            if overrides.description is not None:
                description = overrides.description
            if overrides.system_prompt is not None:
                system_prompt = overrides.system_prompt
            if overrides.icon is not None:
                icon = overrides.icon

        data = SubAgentCreate(
            name=name,
            description=description,
            system_prompt=system_prompt,
            icon=icon,
            llm_provider=overrides.llm_provider if overrides else None,
            llm_model=overrides.llm_model if overrides else None,
            llm_temperature=overrides.llm_temperature if overrides else None,
            skill_ids=template.get("suggested_skill_ids", []),
            allowed_tools=template.get("suggested_tools", []),
            blocked_tools=template.get("default_blocked_tools", []),
            context_instructions=overrides.context_instructions if overrides else None,
        )

        subagent = await self.create(user_id, data, created_by=created_by, template_id=template_id)

        logger.info(
            "subagent_created_from_template",
            subagent_id=str(subagent.id),
            user_id=str(user_id),
            template_id=template_id,
        )

        return subagent

    async def update(
        self,
        subagent_id: UUID,
        user_id: UUID,
        data: SubAgentUpdate,
    ) -> SubAgent:
        """Update a sub-agent.

        Raises:
            ResourceNotFoundError: If sub-agent not found or wrong owner.
            ResourceConflictError: If new name conflicts with existing.
        """
        subagent = await self.get_with_ownership_check(subagent_id, user_id)

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return subagent

        # Check name uniqueness if changing
        if "name" in update_data and update_data["name"] != subagent.name:
            existing = await self.repository.get_by_name_for_user(user_id, update_data["name"])
            if existing:
                raise ResourceConflictError(
                    "sub_agent",
                    f"A sub-agent named '{update_data['name']}' already exists",
                )

        subagent = await self.repository.update(subagent, update_data)

        logger.info(
            "subagent_updated",
            subagent_id=str(subagent_id),
            user_id=str(user_id),
            updated_fields=list(update_data.keys()),
        )

        return subagent

    async def delete(self, subagent_id: UUID, user_id: UUID) -> None:
        """Delete a sub-agent (hard delete).

        Raises:
            ResourceNotFoundError: If sub-agent not found or wrong owner.
            ResourceConflictError: If sub-agent is currently executing.
        """
        subagent = await self.get_with_ownership_check(subagent_id, user_id)

        if subagent.status == SubAgentStatus.EXECUTING.value:
            raise ResourceConflictError(
                "sub_agent",
                f"Cannot delete sub-agent '{subagent.name}' while it is executing",
            )

        await self.repository.delete(subagent)

        logger.info(
            "subagent_deleted",
            subagent_id=str(subagent_id),
            user_id=str(user_id),
            name=subagent.name,
        )

    async def get(self, subagent_id: UUID, user_id: UUID) -> SubAgent:
        """Get a sub-agent by ID with ownership check."""
        return await self.get_with_ownership_check(subagent_id, user_id)

    async def list_for_user(
        self,
        user_id: UUID,
        include_disabled: bool = True,
    ) -> list[SubAgent]:
        """List all sub-agents for a user."""
        return await self.repository.get_all_for_user(user_id, include_disabled=include_disabled)

    async def get_by_name(self, user_id: UUID, name: str) -> SubAgent | None:
        """Get a sub-agent by name for a user (used by agent tools)."""
        return await self.repository.get_by_name_for_user(user_id, name)

    # ========================================================================
    # Templates
    # ========================================================================

    @staticmethod
    def list_templates() -> list[dict]:
        """Return all pre-defined templates."""
        return SUBAGENT_TEMPLATES

    # ========================================================================
    # Toggle
    # ========================================================================

    async def toggle(self, subagent_id: UUID, user_id: UUID) -> SubAgent:
        """Toggle is_enabled for a sub-agent.

        When re-enabling, resets error state.

        Raises:
            ResourceNotFoundError: If sub-agent not found or wrong owner.
            ResourceConflictError: If sub-agent is currently executing.
        """
        subagent = await self.get_with_ownership_check(subagent_id, user_id)

        if subagent.status == SubAgentStatus.EXECUTING.value:
            raise ResourceConflictError(
                "sub_agent",
                f"Cannot toggle sub-agent '{subagent.name}' while it is executing",
            )

        new_enabled = not subagent.is_enabled
        update_data: dict = {"is_enabled": new_enabled}

        if new_enabled:
            update_data["status"] = SubAgentStatus.READY.value
            update_data["consecutive_failures"] = 0
            update_data["last_error"] = None

        subagent = await self.repository.update(subagent, update_data)

        logger.info(
            "subagent_toggled",
            subagent_id=str(subagent_id),
            user_id=str(user_id),
            is_enabled=new_enabled,
        )

        return subagent

    # ========================================================================
    # Execution recording (called by SubAgentExecutor)
    # ========================================================================

    async def record_execution(
        self,
        subagent_id: UUID,
        success: bool,
        summary: str | None = None,
        error: str | None = None,
    ) -> SubAgent:
        """Record execution result. Auto-disables after consecutive failures threshold.

        Called by SubAgentExecutor after each execution completes.
        """
        from src.core.time_utils import now_utc

        subagent = await self.repository.get_by_id(subagent_id)
        if not subagent:
            raise ResourceNotFoundError("sub_agent", str(subagent_id))

        max_failures = getattr(
            settings,
            "subagent_max_consecutive_failures",
            SUBAGENT_MAX_CONSECUTIVE_FAILURES_DEFAULT,
        )

        update_data: dict = {
            "execution_count": subagent.execution_count + 1,
            "last_executed_at": now_utc(),
            "status": SubAgentStatus.READY.value,
        }

        if success:
            update_data["consecutive_failures"] = 0
            update_data["last_error"] = None
            if summary:
                update_data["last_execution_summary"] = summary
        else:
            new_failures = subagent.consecutive_failures + 1
            update_data["consecutive_failures"] = new_failures
            update_data["last_error"] = error

            if new_failures >= max_failures:
                update_data["is_enabled"] = False
                update_data["status"] = SubAgentStatus.ERROR.value
                logger.warning(
                    "subagent_auto_disabled",
                    subagent_id=str(subagent_id),
                    name=subagent.name,
                    consecutive_failures=new_failures,
                    threshold=max_failures,
                )

        subagent = await self.repository.update(subagent, update_data)

        logger.info(
            "subagent_execution_recorded",
            subagent_id=str(subagent_id),
            name=subagent.name,
            success=success,
            execution_count=subagent.execution_count,
            consecutive_failures=subagent.consecutive_failures,
        )

        return subagent
