#!/usr/bin/env python
"""
Scaffolding CLI for LIA API.

Sprint 18.2 - Developer Experience Tooling
Created: 2025-12-18

Generates boilerplate code for:
- New connectors (OAuth or API Key based)
- New agents with tools
- New tools for existing agents

Usage:
    python scripts/scaffold.py connector --name stripe --auth api_key
    python scripts/scaffold.py connector --name microsoft_graph --auth oauth
    python scripts/scaffold.py agent --name weather --domain weather --tools 3
    python scripts/scaffold.py tool --agent weather --name get_forecast

Templates follow existing code patterns and best practices.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from string import Template

# Configure UTF-8 encoding for Windows console
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


# ============================================================================
# TEMPLATES - CONNECTOR (API KEY)
# ============================================================================

CONNECTOR_API_KEY_CLIENT_TEMPLATE = '''"""
${name_title} API client implementation.

Provides integration with ${name_title} API using API key authentication.

Sprint XX - ${name_title} Integration
Created: ${date}
"""

import asyncio
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status

from src.core.config import settings
from src.core.constants import DEFAULT_RATE_LIMIT_PER_SECOND
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials

logger = structlog.get_logger(__name__)


class ${name_class}Client(BaseAPIKeyClient):
    """
    ${name_title} API client.

    Inherits from BaseAPIKeyClient for:
    - API key authentication
    - Rate limiting
    - Retry logic with exponential backoff
    - Circuit breaker pattern
    - Connection pooling

    Configuration:
        - API key stored in connector credentials
        - Rate limit: ${rate_limit} requests/second (configurable)

    Example:
        client = ${name_class}Client(user_id, credentials)
        result = await client.get_resource("resource_id")
    """

    # Required class attributes
    connector_type = ConnectorType.${name_upper}
    api_base_url = "${api_base_url}"

    # Authentication configuration
    auth_header_name = "Authorization"
    auth_header_prefix = "Bearer"  # or "" for raw API key, "Api-Key" for some APIs
    auth_method = "header"  # or "query" for query parameter auth

    def __init__(
        self,
        user_id: UUID,
        credentials: APIKeyCredentials,
        rate_limit_per_second: int = DEFAULT_RATE_LIMIT_PER_SECOND,
    ) -> None:
        """
        Initialize ${name_title} client.

        Args:
            user_id: User ID for logging and tracking.
            credentials: API key credentials (decrypted).
            rate_limit_per_second: Maximum requests per second.
        """
        super().__init__(user_id, credentials, rate_limit_per_second)

        logger.debug(
            "${name_snake}_client_initialized",
            user_id=str(user_id),
            masked_key=self._mask_api_key(credentials.api_key),
        )

    async def validate_api_key(self) -> bool:
        """
        Validate that the API key is functional.

        Makes a lightweight API call to verify the key works.

        Returns:
            True if key is valid, False otherwise.
        """
        try:
            # TODO: Replace with actual validation endpoint
            # Example: await self._make_request("GET", "account")
            return await super().validate_api_key()
        except HTTPException:
            return False

    # =========================================================================
    # API METHODS - Implement your specific API calls here
    # =========================================================================

    async def get_resource(self, resource_id: str) -> dict[str, Any]:
        """
        Get a specific resource by ID.

        Args:
            resource_id: The resource identifier.

        Returns:
            Resource data as dictionary.

        Raises:
            HTTPException: On API errors.
        """
        return await self._make_request(
            "GET",
            f"resources/{resource_id}",
        )

    async def list_resources(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        List resources with pagination.

        Args:
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of resources with pagination metadata.

        Raises:
            HTTPException: On API errors.
        """
        return await self._make_request(
            "GET",
            "resources",
            params={"limit": limit, "offset": offset},
        )

    async def search_resources(
        self,
        query: str,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """
        Search resources by query.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            Search results.

        Raises:
            HTTPException: On API errors.
        """
        return await self._make_request(
            "GET",
            "resources/search",
            params={"q": query, "limit": max_results},
        )

    async def create_resource(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create a new resource.

        Args:
            data: Resource data to create.

        Returns:
            Created resource data.

        Raises:
            HTTPException: On API errors.
        """
        return await self._make_request(
            "POST",
            "resources",
            json_data=data,
        )

    async def update_resource(
        self,
        resource_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Update an existing resource.

        Args:
            resource_id: The resource identifier.
            data: Updated resource data.

        Returns:
            Updated resource data.

        Raises:
            HTTPException: On API errors.
        """
        return await self._make_request(
            "PATCH",
            f"resources/{resource_id}",
            json_data=data,
        )

    async def delete_resource(self, resource_id: str) -> dict[str, Any]:
        """
        Delete a resource.

        Args:
            resource_id: The resource identifier.

        Returns:
            Deletion confirmation.

        Raises:
            HTTPException: On API errors.
        """
        return await self._make_request(
            "DELETE",
            f"resources/{resource_id}",
        )
'''

# ============================================================================
# TEMPLATES - CONNECTOR (OAUTH)
# ============================================================================

CONNECTOR_OAUTH_CLIENT_TEMPLATE = '''"""
${name_title} OAuth client implementation.

Provides integration with ${name_title} API using OAuth 2.0 authentication.

Sprint XX - ${name_title} Integration
Created: ${date}
"""

import asyncio
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status

from src.core.config import settings
from src.domains.connectors.clients.base_oauth_client import BaseOAuthClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


class ${name_class}Client(BaseOAuthClient):
    """
    ${name_title} OAuth API client.

    Inherits from BaseOAuthClient for:
    - OAuth 2.0 token management
    - Automatic token refresh
    - Rate limiting
    - Retry logic with exponential backoff
    - Circuit breaker pattern
    - Connection pooling

    Configuration:
        - OAuth credentials from connector configuration
        - Rate limit: ${rate_limit} requests/second (configurable)

    Example:
        client = ${name_class}Client(user_id, connector)
        result = await client.get_resource("resource_id")
    """

    # Required class attributes
    connector_type = ConnectorType.${name_upper}
    api_base_url = "${api_base_url}"

    # OAuth configuration
    token_url = "${token_url}"
    scopes = [
        "${scope_prefix}/read",
        "${scope_prefix}/write",
    ]

    async def _refresh_access_token(self, refresh_token: str) -> str:
        """
        Refresh the OAuth access token.

        Args:
            refresh_token: The refresh token to use.

        Returns:
            New access token.

        Raises:
            HTTPException: If token refresh fails.
        """
        # TODO: Implement provider-specific token refresh
        # This is typically handled by the OAuth provider configuration
        raise NotImplementedError(
            "Token refresh should be handled by OAuth provider"
        )

    # =========================================================================
    # API METHODS - Implement your specific API calls here
    # =========================================================================

    async def get_resource(self, resource_id: str) -> dict[str, Any]:
        """
        Get a specific resource by ID.

        Args:
            resource_id: The resource identifier.

        Returns:
            Resource data as dictionary.

        Raises:
            HTTPException: On API errors.
        """
        return await self._make_authenticated_request(
            "GET",
            f"resources/{resource_id}",
        )

    async def list_resources(
        self,
        limit: int = 10,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        List resources with pagination.

        Args:
            limit: Maximum number of results.
            page_token: Token for next page.

        Returns:
            List of resources with pagination metadata.

        Raises:
            HTTPException: On API errors.
        """
        params: dict[str, Any] = {"maxResults": limit}
        if page_token:
            params["pageToken"] = page_token

        return await self._make_authenticated_request(
            "GET",
            "resources",
            params=params,
        )

    async def search_resources(
        self,
        query: str,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """
        Search resources by query.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            Search results.

        Raises:
            HTTPException: On API errors.
        """
        return await self._make_authenticated_request(
            "GET",
            "resources/search",
            params={"q": query, "maxResults": max_results},
        )
'''

# ============================================================================
# TEMPLATES - CONNECTOR TYPE ENUM
# ============================================================================

CONNECTOR_TYPE_ADDITION = """
    # Add to ConnectorType enum in src/domains/connectors/models.py:
    ${name_upper} = "${name_snake}"
"""

# ============================================================================
# TEMPLATES - AGENT
# ============================================================================

AGENT_INIT_TEMPLATE = '''"""
${name_title} Agent - ${domain_title} domain tools.

Provides tools for ${description}.

Sprint XX - ${name_title} Agent
Created: ${date}
"""

from src.domains.agents.${name_snake}.catalogue_manifests import (
    ${name_upper}_TOOL_MANIFESTS,
)
from src.domains.agents.${name_snake}.tools import (
${tool_imports}
)

__all__ = [
    "${name_upper}_TOOL_MANIFESTS",
${tool_exports}
]
'''

AGENT_MANIFESTS_TEMPLATE = '''"""
${name_title} Agent Tool Manifests.

Defines tool capabilities, schemas, and metadata for ${name_title} tools.

Sprint XX - ${name_title} Agent
Created: ${date}
"""

from src.domains.agents.core.manifest import (
    Complexity,
    Manifest,
    ManifestInput,
    ManifestPermissions,
    ManifestSchema,
    ParamType,
)
from src.domains.connectors.models import ConnectorType


# ============================================================================
# TOOL MANIFESTS
# ============================================================================

${manifests}


# ============================================================================
# MANIFEST REGISTRY
# ============================================================================

${name_upper}_TOOL_MANIFESTS: dict[str, Manifest] = {
${manifest_registry}
}
'''

AGENT_TOOLS_TEMPLATE = '''"""
${name_title} Agent Tools Implementation.

Sprint XX - ${name_title} Agent
Created: ${date}
"""

from typing import Any
from uuid import UUID

import structlog

from src.domains.agents.core.tool_base import ConnectorTool
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


${tool_classes}
'''

TOOL_CLASS_TEMPLATE = '''
class ${tool_class}(ConnectorTool):
    """
    ${tool_description}

    Inherits from ConnectorTool for:
    - Automatic connector resolution
    - Rate limiting
    - Error handling
    - Observability

    Args:
        ${args_doc}

    Returns:
        ${returns_doc}
    """

    name = "${tool_name}"
    description = "${tool_description}"
    connector_type = ConnectorType.${connector_type}

    async def _execute(
        self,
        user_id: UUID,
        ${args_signature}
    ) -> dict[str, Any]:
        """Execute the tool."""
        # TODO: Implement tool logic
        # client = await self._get_client(user_id)
        # result = await client.some_method(...)
        # return {"status": "success", "data": result}

        return {
            "status": "not_implemented",
            "message": "TODO: Implement ${tool_name}",
        }
'''

MANIFEST_TEMPLATE = """
${manifest_name}_MANIFEST = Manifest(
    name="${tool_name}",
    display_name="${tool_display_name}",
    description="${tool_description}",
    domain="${domain}",
    connector_type=ConnectorType.${connector_type},
    complexity=Complexity.${complexity},
    schema=ManifestSchema(
        inputs=[
            ManifestInput(
                name="query",
                type=ParamType.STRING,
                description="Search query",
                required=True,
            ),
            ManifestInput(
                name="max_results",
                type=ParamType.INTEGER,
                description="Maximum number of results",
                required=False,
                default=10,
            ),
        ],
        output_format="${output_format}",
        output_fields=["id", "name", "description"],
    ),
    permissions=ManifestPermissions(
        read=True,
        write=False,
        delete=False,
        hitl_required=False,
    ),
    examples=[
        "Search for ${example_entity}",
        "Find ${example_entity} matching X",
    ],
)
"""

# ============================================================================
# TEMPLATES - TEST
# ============================================================================

TEST_CLIENT_TEMPLATE = '''"""
Tests for ${name_title} client.

Sprint XX - ${name_title} Integration
Created: ${date}
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.domains.connectors.clients.${name_snake}_client import ${name_class}Client
from src.domains.connectors.schemas import APIKeyCredentials


class Test${name_class}Client:
    """Tests for ${name_class}Client."""

    @pytest.fixture
    def user_id(self):
        return uuid4()

    @pytest.fixture
    def credentials(self):
        return APIKeyCredentials(api_key="test_api_key_12345678")

    @pytest.fixture
    def client(self, user_id, credentials):
        return ${name_class}Client(user_id, credentials)

    @pytest.mark.asyncio
    async def test_initialization(self, client, user_id):
        """Client should initialize correctly."""
        assert client.user_id == user_id
        assert client.connector_type.value == "${name_snake}"

    @pytest.mark.asyncio
    async def test_validate_api_key_valid(self, client):
        """Should return True for valid API key."""
        result = await client.validate_api_key()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_resource(self, client):
        """Should get resource by ID."""
        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "123", "name": "Test"}

            result = await client.get_resource("123")

            assert result["id"] == "123"
            mock.assert_called_once_with("GET", "resources/123")

    @pytest.mark.asyncio
    async def test_list_resources(self, client):
        """Should list resources with pagination."""
        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"items": [], "total": 0}

            result = await client.list_resources(limit=10, offset=0)

            assert "items" in result
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_resources(self, client):
        """Should search resources."""
        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock:
            mock.return_value = {"results": []}

            result = await client.search_resources("test query")

            assert "results" in result

    @pytest.mark.asyncio
    async def test_cleanup(self, client):
        """Should cleanup resources on close."""
        await client.close()
        assert client._http_client is None
'''

TEST_TOOLS_TEMPLATE = '''"""
Tests for ${name_title} agent tools.

Sprint XX - ${name_title} Agent
Created: ${date}
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

${test_imports}


class Test${name_class}Tools:
    """Tests for ${name_title} agent tools."""

    @pytest.fixture
    def user_id(self):
        return uuid4()

${test_classes}
'''


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def to_snake_case(name: str) -> str:
    """Convert name to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result).replace("-", "_").replace(" ", "_")


def to_class_case(name: str) -> str:
    """Convert name to ClassCase."""
    parts = name.replace("-", "_").replace(" ", "_").split("_")
    return "".join(part.capitalize() for part in parts)


def to_title_case(name: str) -> str:
    """Convert name to Title Case."""
    parts = name.replace("-", "_").replace(" ", "_").split("_")
    return " ".join(part.capitalize() for part in parts)


def create_file(path: Path, content: str, overwrite: bool = False) -> bool:
    """Create a file with content."""
    if path.exists() and not overwrite:
        print(f"  SKIP: {path} (already exists)")
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  CREATE: {path}")
    return True


# ============================================================================
# SCAFFOLD FUNCTIONS
# ============================================================================


def scaffold_connector(
    name: str,
    auth_type: str,
    api_url: str,
    base_path: Path,
    overwrite: bool = False,
) -> None:
    """
    Scaffold a new connector.

    Args:
        name: Connector name (e.g., "stripe", "twilio")
        auth_type: Authentication type ("api_key" or "oauth")
        api_url: Base API URL
        base_path: Base path for the project
        overwrite: Whether to overwrite existing files
    """
    print(f"\nScaffolding connector: {name} ({auth_type})")
    print("=" * 50)

    # Prepare template variables
    vars = {
        "name_snake": to_snake_case(name),
        "name_class": to_class_case(name),
        "name_title": to_title_case(name),
        "name_upper": to_snake_case(name).upper(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "api_base_url": api_url or f"https://api.{to_snake_case(name)}.com/v1",
        "rate_limit": "10",
        "token_url": f"https://auth.{to_snake_case(name)}.com/oauth/token",
        "scope_prefix": f"https://api.{to_snake_case(name)}.com",
    }

    # Select template based on auth type
    if auth_type == "api_key":
        template = Template(CONNECTOR_API_KEY_CLIENT_TEMPLATE)
    else:
        template = Template(CONNECTOR_OAUTH_CLIENT_TEMPLATE)

    # Create client file
    client_path = (
        base_path / "src" / "domains" / "connectors" / "clients" / f"{vars['name_snake']}_client.py"
    )
    create_file(client_path, template.substitute(vars), overwrite)

    # Create test file
    test_path = (
        base_path
        / "tests"
        / "domains"
        / "connectors"
        / "clients"
        / f"test_{vars['name_snake']}_client.py"
    )
    test_template = Template(TEST_CLIENT_TEMPLATE)
    create_file(test_path, test_template.substitute(vars), overwrite)

    # Print instructions
    print("\n" + "=" * 50)
    print("Next steps:")
    print(f"  1. Add ConnectorType.{vars['name_upper']} to models.py")
    print(f"  2. Update {vars['name_snake']}_client.py with actual API endpoints")
    print(f"  3. Run tests: pytest {test_path.relative_to(base_path)}")
    print("=" * 50)


def scaffold_agent(
    name: str,
    domain: str,
    num_tools: int,
    connector_type: str,
    base_path: Path,
    overwrite: bool = False,
) -> None:
    """
    Scaffold a new agent with tools.

    Args:
        name: Agent name (e.g., "weather", "news")
        domain: Domain name (e.g., "weather", "news")
        num_tools: Number of tools to generate
        connector_type: Connector type for the tools
        base_path: Base path for the project
        overwrite: Whether to overwrite existing files
    """
    print(f"\nScaffolding agent: {name} (domain: {domain}, tools: {num_tools})")
    print("=" * 50)

    # Prepare template variables
    vars = {
        "name_snake": to_snake_case(name),
        "name_class": to_class_case(name),
        "name_title": to_title_case(name),
        "name_upper": to_snake_case(name).upper(),
        "domain": domain,
        "domain_title": to_title_case(domain),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "description": f"interacting with {to_title_case(name)} services",
        "connector_type": connector_type.upper(),
    }

    # Generate tool names
    tool_templates = [
        ("search", "Search {domain}", "SIMPLE"),
        ("get_details", "Get {domain} Details", "SIMPLE"),
        ("list", "List {domain}", "SIMPLE"),
        ("create", "Create {domain}", "MODERATE"),
        ("update", "Update {domain}", "MODERATE"),
        ("delete", "Delete {domain}", "CRITICAL"),
    ]

    tools = []
    for i in range(min(num_tools, len(tool_templates))):
        base_name, display_template, complexity = tool_templates[i]
        tool_name = f"{base_name}_{to_snake_case(name)}_tool"
        tools.append(
            {
                "name": tool_name,
                "class": to_class_case(tool_name),
                "display": display_template.format(domain=vars["domain_title"]),
                "description": f"{display_template.format(domain=vars['domain_title'])} from {vars['name_title']}",
                "complexity": complexity,
                "manifest_name": f"{base_name.upper()}_{vars['name_upper']}",
            }
        )

    # Generate tool imports
    vars["tool_imports"] = "\n".join(f"    {t['class']}," for t in tools)
    vars["tool_exports"] = "\n".join(f'    "{t["class"]}",' for t in tools)

    # Generate tool classes
    tool_classes = []
    for tool in tools:
        tool_vars = {
            **vars,
            "tool_name": tool["name"],
            "tool_class": tool["class"],
            "tool_description": tool["description"],
            "args_doc": "query: Search query string",
            "returns_doc": "Dictionary with results",
            "args_signature": "query: str,",
        }
        tool_template = Template(TOOL_CLASS_TEMPLATE)
        tool_classes.append(tool_template.substitute(tool_vars))

    vars["tool_classes"] = "\n".join(tool_classes)

    # Generate manifests
    manifests = []
    manifest_registry = []
    for tool in tools:
        manifest_vars = {
            **vars,
            "manifest_name": tool["manifest_name"],
            "tool_name": tool["name"],
            "tool_display_name": tool["display"],
            "tool_description": tool["description"],
            "complexity": tool["complexity"],
            "output_format": "structured",
            "example_entity": vars["domain"],
        }
        manifest_template = Template(MANIFEST_TEMPLATE)
        manifests.append(manifest_template.substitute(manifest_vars))
        manifest_registry.append(f'    "{tool["name"]}": {tool["manifest_name"]}_MANIFEST,')

    vars["manifests"] = "\n".join(manifests)
    vars["manifest_registry"] = "\n".join(manifest_registry)

    # Create agent directory
    agent_dir = base_path / "src" / "domains" / "agents" / vars["name_snake"]
    agent_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py
    init_template = Template(AGENT_INIT_TEMPLATE)
    create_file(agent_dir / "__init__.py", init_template.substitute(vars), overwrite)

    # Create catalogue_manifests.py
    manifests_template = Template(AGENT_MANIFESTS_TEMPLATE)
    create_file(
        agent_dir / "catalogue_manifests.py",
        manifests_template.substitute(vars),
        overwrite,
    )

    # Create tools.py
    tools_template = Template(AGENT_TOOLS_TEMPLATE)
    create_file(agent_dir / "tools.py", tools_template.substitute(vars), overwrite)

    # Create test file
    test_dir = base_path / "tests" / "domains" / "agents" / vars["name_snake"]
    test_dir.mkdir(parents=True, exist_ok=True)

    test_imports = "\n".join(
        f"from src.domains.agents.{vars['name_snake']}.tools import {t['class']}" for t in tools
    )

    test_classes = []
    for tool in tools:
        test_classes.append(f'''
    @pytest.mark.asyncio
    async def test_{tool["name"]}(self, user_id):
        """Test {tool["display"]} tool."""
        tool = {tool["class"]}()
        # TODO: Add proper test implementation
        assert tool.name == "{tool["name"]}"
''')

    test_vars = {
        **vars,
        "test_imports": test_imports,
        "test_classes": "\n".join(test_classes),
    }
    test_template = Template(TEST_TOOLS_TEMPLATE)
    create_file(
        test_dir / f"test_{vars['name_snake']}_tools.py",
        test_template.substitute(test_vars),
        overwrite,
    )

    # Print instructions
    print("\n" + "=" * 50)
    print("Next steps:")
    print(f"  1. Update tool implementations in {agent_dir / 'tools.py'}")
    print(f"  2. Update manifests in {agent_dir / 'catalogue_manifests.py'}")
    print("  3. Register agent in src/domains/agents/__init__.py")
    print(f"  4. Run tests: pytest {test_dir.relative_to(base_path)}")
    print("=" * 50)


def scaffold_tool(
    agent: str,
    tool_name: str,
    base_path: Path,
) -> None:
    """
    Scaffold a new tool for an existing agent.

    Args:
        agent: Agent name (e.g., "weather")
        tool_name: Tool name (e.g., "get_forecast")
        base_path: Base path for the project
    """
    print(f"\nScaffolding tool: {tool_name} for agent: {agent}")
    print("=" * 50)

    agent_dir = base_path / "src" / "domains" / "agents" / to_snake_case(agent)

    if not agent_dir.exists():
        print(f"ERROR: Agent directory not found: {agent_dir}")
        print(f"  Create agent first: python scaffold.py agent --name {agent}")
        return

    vars = {
        "name_snake": to_snake_case(agent),
        "name_class": to_class_case(agent),
        "name_title": to_title_case(agent),
        "name_upper": to_snake_case(agent).upper(),
        "tool_name": f"{to_snake_case(tool_name)}_{to_snake_case(agent)}_tool",
        "tool_class": to_class_case(f"{tool_name}_{agent}_tool"),
        "tool_description": f"{to_title_case(tool_name)} for {to_title_case(agent)}",
        "connector_type": to_snake_case(agent).upper(),
        "args_doc": "# TODO: Document arguments",
        "returns_doc": "Dictionary with results",
        "args_signature": "# TODO: Add arguments",
        "domain": to_snake_case(agent),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

    # Generate tool class
    tool_template = Template(TOOL_CLASS_TEMPLATE)
    tool_code = tool_template.substitute(vars)

    # Generate manifest
    manifest_vars = {
        **vars,
        "manifest_name": f"{to_snake_case(tool_name).upper()}_{vars['name_upper']}",
        "tool_display_name": to_title_case(tool_name),
        "complexity": "SIMPLE",
        "output_format": "structured",
        "example_entity": vars["domain"],
    }
    manifest_template = Template(MANIFEST_TEMPLATE)
    manifest_code = manifest_template.substitute(manifest_vars)

    print("\nAdd to tools.py:")
    print("-" * 40)
    print(tool_code)

    print("\nAdd to catalogue_manifests.py:")
    print("-" * 40)
    print(manifest_code)

    print("\nAdd to manifest registry:")
    print("-" * 40)
    print(f'    "{vars["tool_name"]}": {manifest_vars["manifest_name"]}_MANIFEST,')

    print("\n" + "=" * 50)
    print("Copy the code above to the appropriate files.")
    print("=" * 50)


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    """Run scaffolding CLI."""

    parser = argparse.ArgumentParser(
        description="Scaffold new components for LIA API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s connector --name stripe --auth api_key
  %(prog)s connector --name microsoft_graph --auth oauth --api-url https://graph.microsoft.com/v1.0
  %(prog)s agent --name weather --domain weather --tools 3
  %(prog)s tool --agent weather --name get_forecast
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Connector subcommand
    connector_parser = subparsers.add_parser("connector", help="Scaffold a new connector")
    connector_parser.add_argument("--name", required=True, help="Connector name (e.g., stripe)")
    connector_parser.add_argument(
        "--auth",
        choices=["api_key", "oauth"],
        default="api_key",
        help="Authentication type",
    )
    connector_parser.add_argument("--api-url", help="Base API URL")
    connector_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing files"
    )

    # Agent subcommand
    agent_parser = subparsers.add_parser("agent", help="Scaffold a new agent")
    agent_parser.add_argument("--name", required=True, help="Agent name (e.g., weather)")
    agent_parser.add_argument("--domain", help="Domain name (defaults to agent name)")
    agent_parser.add_argument("--tools", type=int, default=3, help="Number of tools to generate")
    agent_parser.add_argument("--connector", help="Connector type for tools")
    agent_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")

    # Tool subcommand
    tool_parser = subparsers.add_parser("tool", help="Scaffold a new tool for existing agent")
    tool_parser.add_argument("--agent", required=True, help="Agent name (e.g., weather)")
    tool_parser.add_argument("--name", required=True, help="Tool name (e.g., get_forecast)")

    args = parser.parse_args()

    # Determine base path
    base_path = Path(__file__).parent.parent

    if args.command == "connector":
        scaffold_connector(
            name=args.name,
            auth_type=args.auth,
            api_url=args.api_url,
            base_path=base_path,
            overwrite=args.overwrite,
        )
    elif args.command == "agent":
        scaffold_agent(
            name=args.name,
            domain=args.domain or args.name,
            num_tools=args.tools,
            connector_type=args.connector or args.name,
            base_path=base_path,
            overwrite=args.overwrite,
        )
    elif args.command == "tool":
        scaffold_tool(
            agent=args.agent,
            tool_name=args.name,
            base_path=base_path,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
