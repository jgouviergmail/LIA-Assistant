"""Whether a chat client retries a failed call by itself (ADR-100 amendment 2026-10-23).

The vendor SDKs under LangChain's chat classes retry a transient failure on their
own: connection errors, rate limits and 5xx, with backoff and the provider's
``Retry-After``, twice by default (Anthropic's errors page; measured on LIA's
factory-built Anthropic and OpenAI-wire clients on 2026-10-22, three requests for
one 503). LangChain exposes that budget as the class's public ``max_retries``: an
integer, or ``None`` on the OpenAI wire for « the SDK's default ». A class without
the field — the Ollama client — has no retry of its own, so a caller's own loop is
the only one it gets.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableBinding

_ABSENT = object()


def client_retries_by_itself(llm: object) -> bool:
    """Whether ``llm`` retries a failed call before raising it.

    Args:
        llm: A chat model, or a binding of one (``bind_tools``, ``with_config``).

    Returns:
        True when its own budget is positive or left to the vendor SDK's default;
        False when it has none, or when it was set to zero.
    """
    model = llm.bound if isinstance(llm, RunnableBinding) else llm
    budget = getattr(model, "max_retries", _ABSENT)
    if budget is _ABSENT:
        return False
    if budget is None:
        return True
    return isinstance(budget, int) and not isinstance(budget, bool) and budget > 0
