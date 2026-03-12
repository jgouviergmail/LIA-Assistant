"""
Drive Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Google Drive operations using the
generic agent builder template for consistency and maintainability.

LOT 9: Drive agent with Data Registry support.
"""

from typing import Any

from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def build_drive_agent() -> Any:
    """
    Build and compile the Drive agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Drive tools (search, list, get_content)
    - Context resolution tools for reference handling
    - LLM configuration from settings

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_drive_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.context_tools import (
        get_context_list,
        get_context_state,
        list_active_domains,
        resolve_reference,
        set_current_item,
    )
    from src.domains.agents.tools.drive_tools import (
        delete_file_tool,
        get_files_tool,  # Unified tool (v2.0 - replaces search + list + details)
    )

    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            # Drive tools (unified)
            get_files_tool,  # Unified: search + list + details
            delete_file_tool,
            # Context resolution tools
            resolve_reference,
            get_context_list,
            set_current_item,
            get_context_state,
            list_active_domains,
        ],
    )

    context_instructions = """
## Contexte Multi-Domaines (Drive)

Le domaine "files" est actif pour stocker les résultats de recherche et les métadonnées.
Les outils resolve_reference, get_context_state, set_current_item fonctionnent avec domain="files".

**Exemples de références contextuelles** :
- $context.files.0 → Premier fichier des résultats de recherche
- $context.files.current → Fichier actuellement sélectionné
    """.strip()

    # Load versioned prompt template (v1.1 optimized)
    drive_agent_prompt_template = load_prompt("drive_agent_prompt", version="v1")

    system_prompt_template = drive_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions=context_instructions,
    )

    config = create_agent_config_from_settings(
        agent_name="drive_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "drive_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_drive_agent"]
