"""The actual tool invocation checks graph authority before activity and provider work."""

from collections.abc import Awaitable, Callable

from src.domains.agents.expressivity.activity import observe_activity
from src.infrastructure.streaming.run_admission import authorize_external_work


async def invoke_authorized[T](
    tool_name: str, policy: str | None, act: Callable[[], Awaitable[T]]
) -> T:
    """Preserve result/exception identity and the caller's existing effect claim."""
    await authorize_external_work()
    return await observe_activity(tool_name, policy, act)
