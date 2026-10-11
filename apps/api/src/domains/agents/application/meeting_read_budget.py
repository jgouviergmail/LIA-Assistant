"""Keep native pages usable under the existing result ceiling and slot window."""

import json
from contextlib import suppress

import tiktoken

from src.core.config import settings
from src.domains.agents.utils.react_budget import tool_result_token_budget
from src.infrastructure.meeting_reads import MeetingReadPage


def meeting_read_token_budget() -> int:
    window: int | None = None
    with suppress(Exception):
        from src.core.llm_config_helper import get_effective_context_window_for_slot

        window = get_effective_context_window_for_slot("react_agent")
    return max(
        1,
        tool_result_token_budget(
            window,
            ceiling=settings.react_tool_result_max_tokens,
            window_fraction=settings.react_tool_result_window_fraction,
        )
        - 64,
    )


def _tokens(page: MeetingReadPage) -> int:
    # This is the original ReAct serialization and house encoding. Special
    # token spellings in private content remain ordinary text; counting fails
    # closed rather than using the Latin-only character estimate.
    serialized = json.dumps(page.model_dump(mode="json"), ensure_ascii=False, default=str)
    return len(
        tiktoken.get_encoding(settings.token_encoding_name).encode(
            serialized, disallowed_special=()
        )
    )


def _text_page(page: MeetingReadPage, count: int) -> MeetingReadPage:
    assert page.text is not None
    end = page.offset + count
    return page.model_copy(
        update={"text": page.text[:count], "next_offset": end if end < page.total else None}
    )


def _bound_text(page: MeetingReadPage, budget: int) -> MeetingReadPage:
    assert page.text is not None
    low, high = 0, len(page.text)
    while low < high:
        candidate = (low + high + 1) // 2
        if _tokens(_text_page(page, candidate)) <= budget:
            low = candidate
        else:
            high = candidate - 1
    bounded = _text_page(page, low)
    if not low or _tokens(bounded) > budget:
        raise ValueError("Meeting content cannot fit the current context budget")
    return bounded


def bound_meeting_page(page: MeetingReadPage, budget: int) -> MeetingReadPage:
    if _tokens(page) <= budget:
        return page
    if page.text is not None:
        return _bound_text(page, budget)
    items = page.data.get("items")
    if not isinstance(items, list):
        raise ValueError("Meeting metadata cannot fit the current context budget")
    selected = list(items)
    while len(selected) > 1:
        selected.pop()
        bounded = page.model_copy(
            update={
                "data": {**page.data, "items": selected},
                "next_offset": page.offset + len(selected),
            }
        )
        if _tokens(bounded) <= budget:
            return bounded
    raise ValueError("One meeting item cannot fit the current context budget")
