"""Provider call blocks have one vocabulary for history repair and answer guards."""

from typing import Final

# Responses and Anthropic serialize these independently of AIMessage.tool_calls.
CALL_BLOCK_TYPES: Final = frozenset({"function_call", "custom_tool_call", "tool_use"})


def has_tool_call_block(content: object) -> bool:
    """Whether list-shaped content proposes a call, including one with no usable ID."""
    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict)
        and isinstance(block.get("type"), str)
        and block["type"] in CALL_BLOCK_TYPES
        for block in content
    )
