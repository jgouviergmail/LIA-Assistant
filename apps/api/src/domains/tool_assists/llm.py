"""One short structured call of an assist (ADR-372).

The slot's own budget and no reasoning where the model can do without (ADR-285): someone is waiting
on the page. The static rules travel as the system message, the data below the prompt's marker
(ADR-309). The call hands the client the run's config, whose callback bills the assist (ADR-272),
and the structured door answers to both ceilings. A cut output is a refusal there: nothing partial
ever reaches the page (ADR-275).
"""

from __future__ import annotations

import base64
from functools import lru_cache

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import TOOL_ASSIST_LLM_TYPE, TOOL_ASSIST_VISION_LLM_TYPE
from src.core.llm_config_helper import get_llm_config_for_agent, short_answer_config
from src.core.prompt_layout import single_call_messages
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.tool_assists.door import AssistRun
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.structured_output import get_structured_output


@lru_cache(maxsize=1)
def _lines() -> dict[str, str]:
    """The assists' one-line scaffolds, read once from the store."""
    return dict(parse_prompt_sections(read_prompt_file("tool_assist_lines"), 2))


def assist_line(key: str) -> str:
    """One scaffold of the assists' lines file."""
    return _lines()[key]


async def ask_slot[T: BaseModel](run: AssistRun, rendered_prompt: str, schema: type[T]) -> T:
    """Ask the assists' slot once.

    Args:
        run: The assist's run: its config bills the call.
        rendered_prompt: The versioned prompt, its placeholders filled by its caller.
        schema: What the answer must be.

    Returns:
        The validated answer.

    Raises:
        StructuredOutputError: No usable answer came; the door tells it.
        UsageLimitExceededError: A ceiling closed; the door tells it.
    """
    llm = get_llm(TOOL_ASSIST_LLM_TYPE, config_override=short_answer_config(TOOL_ASSIST_LLM_TYPE))
    provider = get_llm_config_for_agent(settings, TOOL_ASSIST_LLM_TYPE).provider
    return await get_structured_output(
        llm,
        single_call_messages(rendered_prompt),
        schema,
        provider,
        node_name=TOOL_ASSIST_LLM_TYPE,
        user_id=str(run.user_id),
        config=run.config,
    )


def _with_image(messages: list[BaseMessage], image: bytes) -> list[BaseMessage]:
    """The call's messages, the picture joining the words of its last one."""
    *before, last = messages
    encoded = base64.b64encode(image).decode("ascii")
    return [
        *before,
        HumanMessage(
            content=[
                {"type": "text", "text": str(last.content)},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
            ]
        ),
    ]


async def ask_slot_on_image[T: BaseModel](
    run: AssistRun, rendered_prompt: str, image: bytes, schema: type[T]
) -> T:
    """Ask the vision slot once about a JPEG.

    Args:
        run: The assist's run: its config bills the call.
        rendered_prompt: The versioned prompt, its placeholders filled by its caller.
        image: The picture, already redrawn.
        schema: What the answer must be.

    Returns:
        The validated answer.

    Raises:
        StructuredOutputError: No usable answer came; the door tells it.
        UsageLimitExceededError: A ceiling closed; the door tells it.
    """
    llm = get_llm(
        TOOL_ASSIST_VISION_LLM_TYPE,
        config_override=short_answer_config(TOOL_ASSIST_VISION_LLM_TYPE),
    )
    return await get_structured_output(
        llm,
        _with_image(single_call_messages(rendered_prompt), image),
        schema,
        get_llm_config_for_agent(settings, TOOL_ASSIST_VISION_LLM_TYPE).provider,
        node_name=TOOL_ASSIST_VISION_LLM_TYPE,
        user_id=str(run.user_id),
        config=run.config,
    )
