"""
Template for creating a new connector tool.

This template uses the ConnectorTool base class pattern (Phase 5).
Simply fill in the TODOs and you'll have a working tool in ~30 lines of code.

Example usage: Gmail send_email tool
Copy this file to: apps/api/src/domains/agents/tools/{service}_tools.py
"""

import time
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel

from src.core.config import get_settings
from src.core.field_names import FIELD_METADATA  # TODO: Add other field names as needed

# TODO: Define your agent constants in src.domains.agents.constants:
# from src.domains.agents.constants import AGENT_YOUR_SERVICE, CONTEXT_DOMAIN_YOUR_SERVICE
from src.domains.agents.context import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.runtime_helpers import (
    handle_tool_exception,
    validate_runtime_config,
)
from src.domains.agents.tools.schemas import ToolResponse
# TODO: Import your client class
# from src.domains.connectors.clients import YourServiceClient
from src.domains.connectors.models import ConnectorType
# TODO: Define your metrics in src.infrastructure.observability.metrics_agents
# from src.infrastructure.observability.metrics_agents import (
#     your_service_api_calls,
#     your_service_api_latency,
#     your_service_results_count,
# )

logger = structlog.get_logger(__name__)


# ============================================================================
# CONTEXT ITEM SCHEMA
# ============================================================================


class YourServiceItem(BaseModel):
    """
    Schema for context items (e.g., emails, events, files).

    TODO: Define fields for your service's items.
    Example for Gmail:
        message_id: str
        subject: str
        from_email: str
        to_emails: list[str]
        body_preview: str
    """

    # TODO: Add your fields
    id: str  # Primary identifier
    name: str  # Display name


# Register context type at module import
# This enables LLM references like "the 2nd email", "subject about meeting"
ContextTypeRegistry.register(
    ContextTypeDefinition(
        # TODO: Update these values for your service
        domain="your_service",  # CONTEXT_DOMAIN_YOUR_SERVICE
        agent_name="your_agent",  # AGENT_YOUR_SERVICE
        item_schema=YourServiceItem,
        primary_id_field="id",  # Unique identifier field
        display_name_field="name",  # Human-readable field
        reference_fields=["name", "id"],  # Fields for fuzzy matching
        icon="📧",  # TODO: Choose an emoji for UI
    )
)


# ============================================================================
# TOOL IMPLEMENTATION CLASS
# ============================================================================


class YourToolClass(ConnectorTool):  # TODO: Rename class (e.g., SendEmailTool)
    """
    TODO: Add docstring describing what this tool does.

    Example for Gmail:
        Sends an email using Gmail API.

    Benefits of ConnectorTool base class:
    - Automatic OAuth credentials retrieval
    - API client caching
    - Error handling and metrics tracking
    - User ID extraction and validation
    """

    # TODO: Set connector type and client class
    connector_type = ConnectorType.GOOGLE_GMAIL  # Update to your connector type
    client_class = None  # YourServiceClient  # Update to your client class

    def __init__(self) -> None:
        """Initialize tool."""
        # TODO: Update tool_name and operation
        super().__init__(tool_name="your_tool_name", operation="your_operation")

    async def execute_api_call(
        self,
        client,  # TODO: Type hint with your client class
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute API call - ONLY business logic here.

        All boilerplate (DI, OAuth, error handling) is handled by ConnectorTool base class.

        Args:
            client: API client instance (already authenticated)
            user_id: User UUID
            **kwargs: Tool-specific parameters

        Returns:
            Dict with API results (will be passed to format_response)

        Example for Gmail send_email:
            to = kwargs["to"]
            subject = kwargs["subject"]
            body = kwargs["body"]

            result = await client.send_email(to, subject, body)

            return {
                "message_id": result.id,
                "sent_at": result.sent_at,
                "to": to,
                "subject": subject,
            }
        """
        # TODO: Implement your API call logic
        settings = get_settings()

        # Example: Extract parameters
        # param1 = kwargs["param1"]
        # param2 = kwargs.get("param2", settings.default_value)

        # Example: Track API call timing
        api_start = time.time()

        # TODO: Call your API client method
        # result = await client.your_method(param1, param2)

        api_duration = time.time() - api_start

        # Example: Track metrics (optional but recommended)
        # your_service_api_latency.labels(operation=self.operation).observe(api_duration)
        # your_service_api_calls.labels(operation=self.operation, status="success").inc()

        logger.info(
            f"{self.operation}_success",
            user_id=str(user_id),
            api_duration_ms=int(api_duration * 1000),
            # TODO: Add relevant fields for logging
        )

        # TODO: Return result dict
        return {
            "success": True,
            # Add your result fields here
        }

    def format_response(self, result: dict[str, Any]) -> str:
        """
        Format API result as JSON string.

        Override this if you need custom formatting.
        Default implementation returns JSON string.

        Args:
            result: Dict returned by execute_api_call

        Returns:
            JSON string for LLM consumption
        """
        # TODO: Optionally customize formatting
        # For simple cases, default JSON formatting is fine
        import json

        return json.dumps(result, ensure_ascii=False)


# Create tool instance (singleton)
# TODO: Rename variable
_your_tool_instance = YourToolClass()


# ============================================================================
# TOOL FUNCTION (LangChain Registration)
# ============================================================================


@connector_tool(
    # TODO: Update these values
    name="your_tool",  # Tool identifier (snake_case)
    agent_name="your_agent",  # AGENT_YOUR_SERVICE
    context_domain="your_service",  # CONTEXT_DOMAIN_YOUR_SERVICE
    category="read",  # "read" or "write"
)
async def your_tool_function(
    # TODO: Define your tool parameters
    # All parameters should have type hints and docstrings
    param1: str,
    param2: int | None = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    TODO: Add tool docstring (used by LLM for understanding the tool).

    This docstring should:
    - Describe what the tool does
    - Explain when to use it
    - Document all parameters
    - Provide usage examples

    Example for Gmail send_email:
        Envoie un email via Gmail.

        Utilise l'API Gmail pour envoyer un message à un ou plusieurs destinataires.

        Args:
            to: Adresse email du destinataire (ou liste séparée par virgules)
            subject: Sujet de l'email
            body: Corps du message (texte brut ou HTML)
            runtime: Runtime dependencies (injected automatically)

        Returns:
            JSON string contenant message_id et confirmation d'envoi

        Examples:
            >>> result = await send_email_tool("john@example.com", "Meeting", "See you at 3pm", runtime)
    """
    # Delegate to tool instance (ConnectorTool handles all boilerplate)
    return await _your_tool_instance.execute(
        runtime=runtime,
        param1=param1,
        param2=param2,
        # TODO: Pass your parameters
    )


# ============================================================================
# EXAMPLE USAGE (for reference)
# ============================================================================

"""
Example: Gmail send_email tool

class SendEmailTool(ConnectorTool[GmailClient]):
    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GmailClient

    def __init__(self) -> None:
        super().__init__(tool_name="send_email_tool", operation="send")

    async def execute_api_call(
        self,
        client: GmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        to = kwargs["to"]
        subject = kwargs["subject"]
        body = kwargs["body"]
        cc = kwargs.get("cc")
        bcc = kwargs.get("bcc")

        result = await client.send_email(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
        )

        return {
            "message_id": result.id,
            "sent_at": result.sent_at,
            "to": to,
            "subject": subject,
        }

_send_email_tool_instance = SendEmailTool()

@connector_tool(
    name="send_email",
    agent_name=AGENT_GMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def send_email_tool(
    to: str,
    subject: str,
    body: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    cc: str | None = None,
    bcc: str | None = None,
) -> str:
    return await _send_email_tool_instance.execute(
        runtime=runtime,
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
    )
"""
