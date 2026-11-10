"""Bound the complete textual request, never confuse estimation with billed usage."""

import json

from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import TOOL_ASSIST_PROMPT_OVERHEAD_TOKENS
from src.core.llm_config_helper import (
    get_effective_context_window_for_slot,
    get_llm_config_for_agent,
)
from src.core.token_budget import count_external_tokens
from src.domains.workbench.errors import TOO_LARGE, refuse


def output_budget(slot: str) -> int:
    """Reserve the resolved slot's output, including reasoning where it shares that cap."""
    return get_llm_config_for_agent(settings, slot).max_tokens


def require_prompt_room(slot: str, prompt: str, schema: type[BaseModel]) -> None:
    """Refuse before constructing a paid client; no silent cut of a selection."""
    schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    needed = count_external_tokens(prompt) + count_external_tokens(schema_text)
    needed += output_budget(slot) + TOOL_ASSIST_PROMPT_OVERHEAD_TOKENS
    if needed > get_effective_context_window_for_slot(slot):
        refuse(TOO_LARGE)
