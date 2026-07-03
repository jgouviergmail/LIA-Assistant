"""Per-invocation datetime rendering for agent system prompts (audit N-183a).

Domain agents are built once and cached for the process lifetime, so any
``{current_datetime}`` rendered at BUILD time freezes: after a few hours of
uptime every agent reasons with a stale "now" (wrong day for calendar
queries, wrong relative dates in drafts).

This middleware re-renders the placeholder on EVERY model call by rewriting
``ModelRequest.system_message`` — the prompt template keeps its placeholder
for the whole agent lifetime and each LLM call sees the real current time.

Usage:
    >>> agent = create_agent(
    ...     model=llm,
    ...     tools=tools,
    ...     system_prompt="You are X. Current datetime: {current_datetime}.",
    ...     middleware=[DynamicDatetimeMiddleware(get_prompt_datetime_formatted)],
    ... )
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import SystemMessage

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

CURRENT_DATETIME_PLACEHOLDER = "{current_datetime}"


class DynamicDatetimeMiddleware(AgentMiddleware):
    """Render ``{current_datetime}`` in the system prompt at each model call.

    Attributes:
        _generator: Zero-argument callable returning the formatted datetime
            string to inject (e.g. ``get_prompt_datetime_formatted``).
    """

    def __init__(self, datetime_generator: Callable[[], str]) -> None:
        """Initialize with the datetime source.

        Args:
            datetime_generator: Callable returning the CURRENT formatted
                datetime; invoked once per model call.
        """
        super().__init__()
        self._generator = datetime_generator

    def _render(self, request: ModelRequest) -> ModelRequest:
        """Return a request whose system message has a fresh datetime.

        No-op when there is no system message or no placeholder — the
        middleware is safe to install unconditionally.
        """
        system_message = request.system_message
        if system_message is None:
            return request

        content = str(system_message.content)
        if CURRENT_DATETIME_PLACEHOLDER not in content:
            return request

        rendered = content.replace(CURRENT_DATETIME_PLACEHOLDER, self._generator())
        return request.override(system_message=SystemMessage(content=rendered))

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """Sync hook: render the datetime then delegate."""
        return handler(self._render(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[Any]],
    ) -> Any:
        """Async hook: render the datetime then delegate."""
        return await handler(self._render(request))


__all__ = ["CURRENT_DATETIME_PLACEHOLDER", "DynamicDatetimeMiddleware"]
