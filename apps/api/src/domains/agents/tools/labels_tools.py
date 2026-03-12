"""
Gmail Labels Management Tools.

Provides tools for managing Gmail labels:
- list_labels_tool: List all labels with hierarchical structure
- create_label_tool: Create new label (supports hierarchy with /)
- update_label_tool: Rename a label
- delete_label_tool: Delete a label (with HITL for sublabels)
- apply_labels_tool: Apply labels to emails
- remove_labels_tool: Remove labels from emails

Architecture (Phase 3.2 / LOT 5.4):
- Tools follow ConnectorTool[GoogleGmailClient] pattern
- Delete uses Draft pattern for HITL confirmation
- Uses AGENT_EMAIL (labels are part of email domain)

Created: 2026-01
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.i18n_api_messages import APIMessages
from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.exceptions import (
    ConnectorNotEnabledError,
    LabelAlreadyExistsError,
    LabelAmbiguousError,
    LabelNotFoundError,
    LabelToolError,
    SystemLabelError,
)
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


# ============================================================================
# 1. LIST LABELS TOOL
# ============================================================================


class ListLabelsTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    List all Gmail labels with hierarchical structure.

    Returns user labels organized by path (e.g., pro/capge/2024).
    Excludes system labels (INBOX, SENT, etc.) by default.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    registry_enabled = True  # Return UnifiedToolOutput

    def __init__(self) -> None:
        super().__init__(tool_name="list_labels_tool", operation="list")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """List all labels with hierarchical structure."""
        include_system: bool = kwargs.get("include_system", False)
        name_filter: str | None = kwargs.get("name_filter")

        labels = await client.list_labels_full(use_cache=True)

        # Filter and structure labels
        user_labels = []
        system_labels = []

        for label in labels:
            label_type = label.get("type", "user")
            label_name = label.get("name", "")

            # Apply name filter if provided (case-insensitive partial match)
            if name_filter:
                if name_filter.lower() not in label_name.lower():
                    continue

            label_info = {
                "id": label.get("id"),
                "name": label_name,
                "type": label_type,
            }

            if label_type == "system":
                system_labels.append(label_info)
            else:
                user_labels.append(label_info)

        # Sort user labels by name for hierarchical display
        user_labels.sort(key=lambda x: x.get("name", "").lower())

        result = {
            "labels": user_labels,
            "total_user_labels": len(user_labels),
            "name_filter": name_filter,
        }

        if include_system:
            result["system_labels"] = system_labels
            result["total_system_labels"] = len(system_labels)

        logger.info(
            "labels_listed",
            user_id=str(user_id),
            user_labels_count=len(user_labels),
            system_labels_count=len(system_labels) if include_system else 0,
            name_filter=name_filter,
        )

        return result

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format as UnifiedToolOutput for Data Registry."""
        labels = result.get("labels", [])
        total = result.get("total_user_labels", 0)
        name_filter = result.get("name_filter")

        # Build summary for LLM
        if total == 0:
            if name_filter:
                summary = f"No labels found matching '{name_filter}'."
            else:
                summary = "No user labels found."
        else:
            # Show all matching labels (up to 20) for filtered results
            max_display = 20 if name_filter else 10
            label_names = [lbl.get("name", "") for lbl in labels[:max_display]]

            if name_filter:
                summary = f"Found {total} labels matching '{name_filter}': {', '.join(label_names)}"
            else:
                summary = f"Found {total} labels: {', '.join(label_names)}"

            if total > max_display:
                summary += f" (and {total - max_display} more)"

        return UnifiedToolOutput.data_success(
            message=summary,
            structured_data=result,
        )


@connector_tool(
    name="list_labels",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="read",
)
async def list_labels_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    name_filter: str | None = None,
    include_system: bool = False,
) -> UnifiedToolOutput:
    """
    List Gmail labels, optionally filtered by name.

    Args:
        runtime: Tool runtime with user context
        name_filter: Filter labels by name (case-insensitive partial match).
                     Example: "famille" matches "Famille", "Famille/Oncles", etc.
        include_system: Include system labels (INBOX, SENT, etc.)

    Returns:
        UnifiedToolOutput with list of labels
    """
    tool = ListLabelsTool()
    return await tool.execute(runtime, name_filter=name_filter, include_system=include_system)


# ============================================================================
# 2. CREATE LABEL TOOL
# ============================================================================


class CreateLabelTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Create a new Gmail label.

    Supports hierarchical labels using "/" separator.
    Example: "pro/capge/2024" creates nested structure.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="create_label_tool", operation="create")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a new label."""
        name: str = kwargs.get("name", "")
        language: str = kwargs.get("language", "fr")

        if not name or not name.strip():
            raise LabelToolError("Label name is required")

        name = name.strip()

        # Check if it's a system label name
        if client.is_system_label(name):
            raise SystemLabelError(
                APIMessages.label_is_system(name, language),
                label_name=name,
            )

        # Check if label already exists
        existing = await client.resolve_label_with_disambiguation(name, use_cache=False)
        if existing.get("resolved"):
            raise LabelAlreadyExistsError(
                APIMessages.label_already_exists(name, language),
                label_name=name,
            )

        # Create the label
        created_label = await client.create_label(name)

        logger.info(
            "label_created",
            user_id=str(user_id),
            label_id=created_label.get("id"),
            label_name=name,
        )

        return {
            "success": True,
            "label": created_label,
            "message": APIMessages.label_created_success(name, language),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format as UnifiedToolOutput."""
        return UnifiedToolOutput.action_success(
            message=result.get("message", "Label created"),
            structured_data=result,
        )


@connector_tool(
    name="create_label",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def create_label_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    name: str,
) -> UnifiedToolOutput:
    """
    Create a new Gmail label.

    Args:
        runtime: Tool runtime with user context
        name: Label name (use "/" for hierarchy, e.g., "pro/capge/2024")

    Returns:
        UnifiedToolOutput with created label info
    """
    tool = CreateLabelTool()
    return await tool.execute(runtime, name=name)


# ============================================================================
# 3. UPDATE LABEL TOOL
# ============================================================================


class UpdateLabelTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Rename a Gmail label.

    Note: Renaming a parent label may or may not automatically
    update sublabel paths depending on Gmail's behavior.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="update_label_tool", operation="update")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Rename a label."""
        label_name: str = kwargs.get("label_name", "")
        new_name: str = kwargs.get("new_name", "")
        language: str = kwargs.get("language", "fr")

        if not label_name or not label_name.strip():
            raise LabelToolError("Current label name is required")
        if not new_name or not new_name.strip():
            raise LabelToolError("New label name is required")

        label_name = label_name.strip()
        new_name = new_name.strip()

        # Check if source label is system
        if client.is_system_label(label_name):
            raise SystemLabelError(
                APIMessages.label_is_system(label_name, language),
                label_name=label_name,
            )

        # Resolve the source label
        resolution = await client.resolve_label_with_disambiguation(label_name, use_cache=False)

        if not resolution.get("resolved"):
            candidates = resolution.get("candidates", [])
            if candidates:
                raise LabelAmbiguousError(
                    APIMessages.label_ambiguous(label_name, len(candidates), language),
                    candidates=candidates,
                )
            raise LabelNotFoundError(
                APIMessages.label_not_found(label_name, language),
                label_name=label_name,
            )

        label = resolution["label"]
        label_id = label.get("id")
        old_name = label.get("name")

        # Check if new name already exists
        new_resolution = await client.resolve_label_with_disambiguation(new_name, use_cache=False)
        if new_resolution.get("resolved"):
            raise LabelAlreadyExistsError(
                APIMessages.label_already_exists(new_name, language),
                label_name=new_name,
            )

        # Update the label
        updated_label = await client.update_label(label_id, new_name)

        logger.info(
            "label_updated",
            user_id=str(user_id),
            label_id=label_id,
            old_name=old_name,
            new_name=new_name,
        )

        return {
            "success": True,
            "label": updated_label,
            "old_name": old_name,
            "new_name": new_name,
            "message": APIMessages.label_updated_success(old_name, new_name, language),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format as UnifiedToolOutput."""
        return UnifiedToolOutput.action_success(
            message=result.get("message", "Label updated"),
            structured_data=result,
        )


@connector_tool(
    name="update_label",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def update_label_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    label_name: str,
    new_name: str,
) -> UnifiedToolOutput:
    """
    Rename a Gmail label.

    Args:
        runtime: Tool runtime with user context
        label_name: Current label name (or path)
        new_name: New label name

    Returns:
        UnifiedToolOutput with updated label info
    """
    tool = UpdateLabelTool()
    return await tool.execute(runtime, label_name=label_name, new_name=new_name)


# ============================================================================
# 4. DELETE LABEL TOOLS (Draft + Direct pattern)
# ============================================================================


class DeleteLabelDraftTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Create a draft for deleting a Gmail label.

    Uses HITL Draft pattern (LOT 5.4) for confirmation.
    If the label has sublabels, they will be listed for user awareness.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="delete_label_tool", operation="delete_draft")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a delete label draft for HITL confirmation."""
        label_name: str = kwargs.get("label_name", "")
        children_only: bool = kwargs.get("children_only", False)
        language: str = kwargs.get("language", "fr")

        if not label_name or not label_name.strip():
            raise LabelToolError("Label name is required")

        label_name = label_name.strip()

        # Check if it's a system label
        if client.is_system_label(label_name):
            raise SystemLabelError(
                APIMessages.label_is_system(label_name, language),
                label_name=label_name,
            )

        # Resolve the label
        resolution = await client.resolve_label_with_disambiguation(label_name, use_cache=False)

        if not resolution.get("resolved"):
            candidates = resolution.get("candidates", [])
            if candidates:
                # Return disambiguation needed
                return {
                    "success": False,
                    "requires_disambiguation": True,
                    "candidates": candidates,
                    "message": APIMessages.label_ambiguous(label_name, len(candidates), language),
                }
            raise LabelNotFoundError(
                APIMessages.label_not_found(label_name, language),
                label_name=label_name,
            )

        label = resolution["label"]
        label_id = label.get("id")
        full_label_name = label.get("name")

        # Get sublabels
        sublabels = await client.get_sublabels(full_label_name)

        # For children_only mode, we need sublabels to exist
        if children_only and not sublabels:
            raise LabelToolError(
                APIMessages.label_no_children(full_label_name, language),
            )

        logger.info(
            "delete_label_draft_prepared",
            user_id=str(user_id),
            label_id=label_id,
            label_name=full_label_name,
            sublabels_count=len(sublabels),
            children_only=children_only,
        )

        # Return data for format_registry_response
        return {
            "label_id": label_id,
            "label_name": full_label_name,
            "sublabels": [{"id": s.get("id"), "name": s.get("name")} for s in sublabels],
            "children_only": children_only,
            "language": language,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create label deletion draft via DraftService.

        Returns UnifiedToolOutput with HITL metadata (requires_confirmation=True).
        """
        from src.domains.agents.drafts import create_label_delete_draft

        return create_label_delete_draft(
            label_id=result["label_id"],
            label_name=result["label_name"],
            sublabels=result.get("sublabels", []),
            children_only=result.get("children_only", False),
            source_tool="delete_label_tool",
            user_language=result.get("language", "fr"),
        )


class DeleteLabelDirectTool(ConnectorTool[GoogleGmailClient]):
    """
    Execute label deletion after HITL confirmation.

    Called by draft execution system after user confirms.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient

    def __init__(self) -> None:
        super().__init__(tool_name="delete_label_direct_tool", operation="delete")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute the actual label deletion."""
        label_id: str = kwargs.get("label_id", "")
        label_name: str = kwargs.get("label_name", "")
        children_only: bool = kwargs.get("children_only", False)
        sublabels: list[dict] = kwargs.get("sublabels", [])
        language: str = kwargs.get("language", "fr")

        deleted_count = 0

        if children_only:
            # Delete only sublabels, keep parent
            for sublabel in sublabels:
                sublabel_id = sublabel.get("id")
                if sublabel_id:
                    await client.delete_label(sublabel_id)
                    deleted_count += 1

            logger.info(
                "label_children_deleted",
                user_id=str(user_id),
                parent_label=label_name,
                deleted_count=deleted_count,
            )

            return {
                "success": True,
                "deleted_count": deleted_count,
                "parent_preserved": True,
                "message": APIMessages.labels_deleted_success(deleted_count, language),
            }
        else:
            # Delete the label (and Gmail will delete sublabels automatically)
            await client.delete_label(label_id)
            deleted_count = 1 + len(sublabels)

            logger.info(
                "label_deleted",
                user_id=str(user_id),
                label_id=label_id,
                label_name=label_name,
                sublabels_deleted=len(sublabels),
            )

            return {
                "success": True,
                "deleted_count": deleted_count,
                "message": APIMessages.label_deleted_success(label_name, language),
            }


@connector_tool(
    name="delete_label",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def delete_label_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    label_name: str,
    children_only: bool = False,
) -> UnifiedToolOutput:
    """
    Delete a Gmail label.

    Triggers HITL confirmation before deletion.
    If the label has sublabels, they will be deleted too.

    Args:
        runtime: Tool runtime with user context
        label_name: Label name to delete (or path like "pro/capge")
        children_only: If True, only delete sublabels, keep parent

    Returns:
        UnifiedToolOutput with draft for HITL confirmation
    """
    tool = DeleteLabelDraftTool()
    return await tool.execute(runtime, label_name=label_name, children_only=children_only)


# ============================================================================
# 5. APPLY LABELS TOOL
# ============================================================================


class ApplyLabelsTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Apply labels to one or more emails.

    Supports auto-creation of labels if they don't exist.
    For bulk operations (3+ emails), uses FOR_EACH confirmation.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="apply_labels_tool", operation="apply")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Apply labels to emails."""
        message_id: str | None = kwargs.get("message_id")
        message_ids: list[str] | None = kwargs.get("message_ids")
        label_names: list[str] = kwargs.get("label_names", [])
        auto_create: bool = kwargs.get("auto_create", True)
        language: str = kwargs.get("language", "fr")

        # Normalize message IDs
        if message_id and not message_ids:
            message_ids = [message_id]
        elif not message_ids:
            raise LabelToolError("message_id or message_ids is required")

        if not label_names:
            raise LabelToolError("label_names is required")

        # Resolve all labels (with auto-create if enabled)
        resolved_label_ids = []
        for label_name in label_names:
            label_name = label_name.strip()

            # Check for disambiguation
            resolution = await client.resolve_label_with_disambiguation(label_name, use_cache=False)

            if resolution.get("resolved"):
                resolved_label_ids.append(resolution["label"]["id"])
            elif resolution.get("candidates"):
                # Ambiguous - return for HITL disambiguation
                return {
                    "success": False,
                    "requires_disambiguation": True,
                    "label_name": label_name,
                    "candidates": resolution["candidates"],
                    "message": APIMessages.label_ambiguous(
                        label_name, len(resolution["candidates"]), language
                    ),
                }
            elif auto_create:
                # Create the label
                new_label = await client.create_label(label_name)
                resolved_label_ids.append(new_label["id"])
                logger.info(
                    "label_auto_created",
                    user_id=str(user_id),
                    label_name=label_name,
                )
            else:
                raise LabelNotFoundError(
                    APIMessages.label_not_found(label_name, language),
                    label_name=label_name,
                )

        # Apply labels to messages
        if len(message_ids) == 1:
            await client.modify_message_labels(
                message_ids[0],
                add_label_ids=resolved_label_ids,
            )
        else:
            await client.batch_modify_labels(
                message_ids,
                add_label_ids=resolved_label_ids,
            )

        logger.info(
            "labels_applied",
            user_id=str(user_id),
            message_count=len(message_ids),
            label_count=len(resolved_label_ids),
            label_names=label_names,
        )

        return {
            "success": True,
            "message_count": len(message_ids),
            "labels_applied": label_names,
            "message": APIMessages.labels_applied_success(len(message_ids), label_names, language),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format as UnifiedToolOutput."""
        return UnifiedToolOutput.action_success(
            message=result.get("message", "Labels applied"),
            structured_data=result,
        )


@connector_tool(
    name="apply_labels",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def apply_labels_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    label_names: list[str],
    message_id: str | None = None,
    message_ids: list[str] | None = None,
    auto_create: bool = True,
) -> UnifiedToolOutput:
    """
    Apply labels to email(s).

    Args:
        runtime: Tool runtime with user context
        label_names: List of label names to apply
        message_id: Single message ID (optional if message_ids provided)
        message_ids: Multiple message IDs (optional if message_id provided)
        auto_create: Create labels if they don't exist (default: True)

    Returns:
        UnifiedToolOutput with result
    """
    tool = ApplyLabelsTool()
    return await tool.execute(
        runtime,
        label_names=label_names,
        message_id=message_id,
        message_ids=message_ids,
        auto_create=auto_create,
    )


# ============================================================================
# 6. REMOVE LABELS TOOL
# ============================================================================


class RemoveLabelsTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Remove labels from one or more emails.

    For bulk operations (3+ emails), uses FOR_EACH confirmation.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="remove_labels_tool", operation="remove")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Remove labels from emails."""
        message_id: str | None = kwargs.get("message_id")
        message_ids: list[str] | None = kwargs.get("message_ids")
        label_names: list[str] = kwargs.get("label_names", [])
        language: str = kwargs.get("language", "fr")

        # Normalize message IDs
        if message_id and not message_ids:
            message_ids = [message_id]
        elif not message_ids:
            raise LabelToolError("message_id or message_ids is required")

        if not label_names:
            raise LabelToolError("label_names is required")

        # Resolve all labels
        resolved_label_ids = []
        for label_name in label_names:
            label_name = label_name.strip()

            resolution = await client.resolve_label_with_disambiguation(label_name, use_cache=False)

            if resolution.get("resolved"):
                resolved_label_ids.append(resolution["label"]["id"])
            elif resolution.get("candidates"):
                # Ambiguous - return for HITL disambiguation
                return {
                    "success": False,
                    "requires_disambiguation": True,
                    "label_name": label_name,
                    "candidates": resolution["candidates"],
                    "message": APIMessages.label_ambiguous(
                        label_name, len(resolution["candidates"]), language
                    ),
                }
            else:
                raise LabelNotFoundError(
                    APIMessages.label_not_found(label_name, language),
                    label_name=label_name,
                )

        # Remove labels from messages
        if len(message_ids) == 1:
            await client.modify_message_labels(
                message_ids[0],
                remove_label_ids=resolved_label_ids,
            )
        else:
            await client.batch_modify_labels(
                message_ids,
                remove_label_ids=resolved_label_ids,
            )

        logger.info(
            "labels_removed",
            user_id=str(user_id),
            message_count=len(message_ids),
            label_count=len(resolved_label_ids),
            label_names=label_names,
        )

        return {
            "success": True,
            "message_count": len(message_ids),
            "labels_removed": label_names,
            "message": APIMessages.labels_removed_success(len(message_ids), label_names, language),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format as UnifiedToolOutput."""
        return UnifiedToolOutput.action_success(
            message=result.get("message", "Labels removed"),
            structured_data=result,
        )


@connector_tool(
    name="remove_labels",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def remove_labels_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    label_names: list[str],
    message_id: str | None = None,
    message_ids: list[str] | None = None,
) -> UnifiedToolOutput:
    """
    Remove labels from email(s).

    Args:
        runtime: Tool runtime with user context
        label_names: List of label names to remove
        message_id: Single message ID (optional if message_ids provided)
        message_ids: Multiple message IDs (optional if message_id provided)

    Returns:
        UnifiedToolOutput with result
    """
    tool = RemoveLabelsTool()
    return await tool.execute(
        runtime,
        label_names=label_names,
        message_id=message_id,
        message_ids=message_ids,
    )


# ============================================================================
# DRAFT EXECUTION HELPER
# ============================================================================


async def execute_label_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a label delete draft after HITL confirmation.

    Called by DraftExecutor when user confirms label deletion.

    Args:
        draft_content: LabelDeleteDraftInput as dict
        user_id: User ID
        deps: ToolDependencies with connector access

    Returns:
        Execution result dict
    """
    connector_service = await deps.get_connector_service()

    # Get credentials
    credentials = await connector_service.get_connector_credentials(
        user_id, ConnectorType.GOOGLE_GMAIL
    )
    if not credentials:
        raise ConnectorNotEnabledError(
            APIMessages.connector_not_enabled("Google Gmail"),
            connector_name="Google Gmail",
        )

    client = GoogleGmailClient(user_id, credentials, connector_service)

    tool = DeleteLabelDirectTool()
    return await tool.execute_api_call(
        client,
        user_id,
        label_id=draft_content.get("label_id"),
        label_name=draft_content.get("label_name"),
        children_only=draft_content.get("children_only", False),
        sublabels=draft_content.get("sublabels", []),
        language=draft_content.get("user_language", "fr"),
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Tool functions
    "list_labels_tool",
    "create_label_tool",
    "update_label_tool",
    "delete_label_tool",
    "apply_labels_tool",
    "remove_labels_tool",
    # Tool classes
    "ListLabelsTool",
    "CreateLabelTool",
    "UpdateLabelTool",
    "DeleteLabelDraftTool",
    "DeleteLabelDirectTool",
    "ApplyLabelsTool",
    "RemoveLabelsTool",
    # Draft execution
    "execute_label_delete_draft",
]
