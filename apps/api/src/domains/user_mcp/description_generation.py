"""Describing a user's MCP server for the query router.

Extracted from :mod:`service` on 2026-09-07, when the accounting wiring pushed
that module two logical lines past its ratchet cap. The cap is shrink-only by
doctrine, so the answer is an extraction rather than a bump — and this is a
cohesive unit: one question (what queries can this server answer?), one model
call, one algorithmic fallback.
"""

from __future__ import annotations

from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


async def _account_description_spend(
    user_id: UUID | None,
    server_name: str,
    llm: object,
    response: object,
) -> None:
    """Bill one description generation to the account whose server it is.

    Args:
        user_id: The owner, or None where no owner is in scope — the spend is
            then simply not accounted rather than charged to someone else.
        server_name: The server, for the run's target id.
        llm: The client, for the model name.
        response: The model's reply, carrying its usage.
    """
    if user_id is None:
        return
    from src.infrastructure.llm.usage_metadata import model_name_of, tokens_from_response
    from src.infrastructure.proactive.tracking import track_proactive_tokens

    usage = tokens_from_response(response)
    await track_proactive_tokens(
        user_id=user_id,
        task_type="mcp_description",
        target_id=server_name[:12],
        conversation_id=None,
        tokens_in=usage.prompt,
        tokens_out=usage.completion,
        tokens_cache=usage.cached,
        model_name=model_name_of(llm),
        source="user",
    )


async def generate_domain_description(
    *,
    tool_list: list[dict],
    server_name: str,
    account_scoped: bool = False,
    user_id: UUID | None = None,
) -> str:
    """Generate an intelligent domain description using an LLM.

    Analyses MCP tool names and descriptions to produce a domain
    description optimized for LLM query routing: the description
    explains *what kind of user queries* this server can handle.

    Falls back to ``auto_generate_server_description()`` if the LLM
    call fails for any reason (network, provider outage, etc.).

    Args:
        tool_list: Discovered tools (list of dicts with "name" / "description").
        server_name: Human-readable server name.
        account_scoped: True when the server's credential is the user's
            own (``auth_type != none``). Fed only tool names, the
            generator once described an authenticated GitHub server as
            "public GitHub repositories" — and every routing surface
            repeated it (2026-09-02).
        user_id: Account the description is generated for, so the call is
            billed to the person whose server it is. None only where no
            owner is in scope, and then the spend is simply not accounted
            rather than charged to someone else.

    Returns:
        Generated domain description string.
    """
    # Bounded before it spends: the deployment's provider key pays for this
    # call, so both ceilings apply. Non-raising on purpose — a quota must not
    # stop someone registering a server, only deprive its description of a
    # model, which is exactly what the deterministic fallback below is for.
    from src.domains.usage_limits.enforcement import spend_blocked

    if await spend_blocked(user_id):
        return _algorithmic_description(server_name=server_name, tool_list=tool_list)

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.domains.agents.prompts import load_prompt
        from src.infrastructure.llm import get_llm

        llm = get_llm("mcp_description")

        # Build tool summary for the prompt
        tool_lines: list[str] = []
        for t in tool_list:
            name = t.get("name", "")
            desc = t.get("description", "")
            if name and desc:
                tool_lines.append(f"- {name}: {desc}")
            elif name:
                tool_lines.append(f"- {name}")
        tools_text = "\n".join(tool_lines)

        auth_line = (
            "Authentication: calls are authenticated with the user's own account "
            "credentials - capabilities operate on the user's own data, never "
            "describe this server as public-only."
            if account_scoped
            else "Authentication: none - the server serves public or anonymous data."
        )
        system_prompt = load_prompt("mcp_description_prompt")
        user_prompt = f"Server name: {server_name}\n{auth_line}\n\nAvailable tools:\n{tools_text}"

        from src.infrastructure.llm.invoke_helpers import (
            enrich_config_with_node_metadata,
        )

        invoke_config = enrich_config_with_node_metadata(None, "mcp_description_generation")
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ],
            config=invoke_config,
        )
        await _account_description_spend(user_id, server_name, llm, response)

        generated = response.text.strip()

        # Remove surrounding quotes if present
        if (generated.startswith('"') and generated.endswith('"')) or (
            generated.startswith("'") and generated.endswith("'")
        ):
            generated = generated[1:-1].strip()

        if generated:
            logger.debug(
                "user_mcp_description_llm_generated",
                server_name=server_name,
                description_length=len(generated),
            )
            return generated

    except Exception:
        logger.warning(
            "user_mcp_description_llm_failed",
            server_name=server_name,
            exc_info=True,
        )

    return _algorithmic_description(server_name=server_name, tool_list=tool_list)


def _algorithmic_description(*, server_name: str, tool_list: list[dict]) -> str:
    """The deterministic description, used whenever no model writes one.

    Extracted so the two paths that need it — a failed call and a refused one
    — cannot drift into two different fallbacks.

    Args:
        server_name: The MCP server's name.
        tool_list: Its advertised tools.

    Returns:
        A domain description built from the tool names and descriptions.
    """
    from src.domains.agents.registry.domain_taxonomy import (
        auto_generate_server_description,
    )

    return auto_generate_server_description(
        tool_descriptions=[t.get("description", "") for t in tool_list],
        server_name=server_name,
        tool_names=[t.get("name", "") for t in tool_list],
    )
