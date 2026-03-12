"""
Prompt generation helpers for tool context instructions.

Automatically generates context-aware instructions for agent prompts
based on registered context types.

Usage:
    # In agent prompt
    context_instructions = get_context_instructions("contacts_agent")
    system_prompt = f'''
    Tu es un assistant...

    {context_instructions}

    Important: ...
    '''
"""

from src.domains.agents.context.registry import ContextTypeRegistry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def get_context_instructions(agent_name: str) -> str:
    """
    Generate contextual reference instructions for an agent.

    Auto-discovers context types available for the agent via ContextTypeRegistry
    and generates appropriate LLM instructions.

    Args:
        agent_name: Name of the agent ("contacts_agent", "emails_agent").

    Returns:
        Formatted instructions string (empty if no contexts available).

    Example:
        >>> # For contacts_agent with "contacts" context registered
        >>> instructions = get_context_instructions("contacts_agent")
        >>> print(instructions)
        ## Références Contextuelles (Disponibles: contacts)

        Tu peux utiliser `resolve_reference` pour résoudre des références...

    Integration:
        # In prompts.py
        def format_contacts_agent_prompt(_state: dict) -> list[SystemMessage]:
            context_instructions = get_context_instructions("contacts_agent")

            system_prompt = f'''
            Tu es un assistant...

            {context_instructions}

            Important: ...
            '''
            return [SystemMessage(content=system_prompt)]

    Best Practices:
        - Always call this function in agent prompt formatters
        - Instructions auto-adapt when new context types are registered
        - Zero maintenance when adding new agents
    """
    # Get all context types for this agent
    definitions = ContextTypeRegistry.get_by_agent(agent_name)

    if not definitions:
        logger.debug(
            "no_context_types_for_agent",
            agent_name=agent_name,
            message="No contextual instructions to inject",
        )
        return ""

    # Extract context type names
    context_types = [d.context_type for d in definitions]
    types_str = ", ".join(context_types)
    first_context_type = context_types[0] if context_types else "contacts"

    # Load externalized prompt and replace placeholders
    from src.domains.agents.prompts import load_prompt

    instructions = (
        load_prompt("context_reference_instructions_prompt")
        .replace("{context_types}", types_str)
        .replace("{first_context_type}", first_context_type)
    )

    logger.debug(
        "context_instructions_generated",
        agent_name=agent_name,
        context_types=context_types,
        instructions_length=len(instructions),
    )

    return instructions.strip()


def get_available_context_types_for_agent(agent_name: str) -> list[str]:
    """
    Get list of context types available for an agent.

    Utility function for UI or debugging purposes.

    Args:
        agent_name: Name of the agent.

    Returns:
        List of context type identifiers.

    Example:
        >>> types = get_available_context_types_for_agent("contacts_agent")
        >>> print(types)  # ["contacts"]
    """
    definitions = ContextTypeRegistry.get_by_agent(agent_name)
    return [d.context_type for d in definitions]
