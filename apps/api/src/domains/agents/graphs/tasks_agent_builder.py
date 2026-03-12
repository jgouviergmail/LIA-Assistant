"""
Tasks Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Google Tasks operations using the
generic agent builder template for consistency and maintainability.

LOT 9: Tasks agent with Data Registry support.
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


def build_tasks_agent() -> Any:
    """
    Build and compile the Tasks agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Tasks tools (list, create, complete, list_lists)
    - Context resolution tools for reference handling
    - HITL support for create operations
    - LLM configuration from settings

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_tasks_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.context_tools import (
        get_context_list,
        get_context_state,
        list_active_domains,
        resolve_reference,
        set_current_item,
    )
    from src.domains.agents.tools.tasks_tools import (
        complete_task_tool,
        create_task_tool,
        delete_task_tool,
        get_tasks_tool,  # Unified tool (v2.0 - replaces list + details)
        list_task_lists_tool,
        update_task_tool,
    )

    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            # Tasks tools (unified)
            get_tasks_tool,  # Unified: list + details
            create_task_tool,
            update_task_tool,
            delete_task_tool,
            complete_task_tool,
            list_task_lists_tool,
            # Context resolution tools
            resolve_reference,
            get_context_list,
            set_current_item,
            get_context_state,
            list_active_domains,
        ],
    )

    context_instructions = """
## Contexte Multi-Domaines (Tasks)

Le domaine "tasks" est actif pour stocker les tâches et leurs détails.
Les outils resolve_reference, get_context_state, set_current_item fonctionnent avec domain="tasks".

**Exemples de références contextuelles** :
- $context.tasks.0 → Première tâche des résultats
- $context.tasks.current → Tâche actuellement sélectionnée
    """.strip()

    # Load versioned prompt template (v1.2 optimized)
    tasks_agent_prompt_template = load_prompt("tasks_agent_prompt", version="v1")

    system_prompt_template = tasks_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions=context_instructions,
    )

    config = create_agent_config_from_settings(
        agent_name="tasks_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "tasks_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_tasks_agent"]
