"""Bounded external metadata excerpts for the original MCP description slot."""

from collections.abc import Mapping

from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.agents.utils.token_utils import count_tokens

MCP_DESCRIPTION_INPUT_MAX_TOKENS = 4096
MCP_DESCRIPTION_MAX_TOOLS = 64


def description_input_cost(text: str) -> int:
    """A local token estimate plus a conservative ceiling for other tokenizers."""
    return max(count_tokens(text), len(text.encode("utf-8")))


def public_tool_excerpts(tool_list: list[dict]) -> list[dict[str, str]]:
    result = []
    for tool in tool_list[:MCP_DESCRIPTION_MAX_TOOLS]:
        if not isinstance(tool, Mapping):
            continue
        name, description = tool.get("name", ""), tool.get("description", "")
        if not isinstance(name, str) or not name:
            continue
        result.append(
            {
                "name": name[:256],
                "description": description[:512] if isinstance(description, str) else "",
            }
        )
    return result


def build_description_prompt(
    tool_list: list[dict],
    server_name: str,
    account_scoped: bool,
    *,
    max_tokens: int = MCP_DESCRIPTION_INPUT_MAX_TOKENS,
) -> str:
    max_tokens = min(max_tokens, MCP_DESCRIPTION_INPUT_MAX_TOKENS)
    auth_line = (
        "Authentication: calls are authenticated with the user's own account "
        "credentials - capabilities operate on the user's own data, never "
        "describe this server as public-only."
        if account_scoped
        else "Authentication: none - the server serves public or anonymous data."
    )
    lines: list[str] = []

    def render() -> str:
        data = f"Server name: {server_name[:100]}\n\nAvailable tools:\n" + "\n".join(lines)
        frame = wrap_external_content(
            data, source_url="personal_mcp_metadata", source_type="mcp_metadata"
        )
        return f"{auth_line}\nTools shown: {len(lines)} of {len(tool_list)}; metadata excerpts. Unshown capabilities are unknown.\n{frame}"

    if description_input_cost(render()) > max_tokens:
        raise ValueError("MCP description input cannot fit its configured slot")
    for tool in public_tool_excerpts(tool_list):
        name, description = tool["name"], tool["description"]
        lines.append(f"- {name}: {description}" if description else f"- {name}")
        if description_input_cost(render()) > max_tokens:
            lines.pop()
            break
    if tool_list and not lines:
        raise ValueError("No MCP tool metadata fits the configured slot")
    return render()
