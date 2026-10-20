"""The final provider boundary for SMS copied into a domain-agent loop."""

from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AnyMessage, BaseMessage, ToolMessage

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.sms.message_policy import is_sms_source_message, normalize_sms_messages
from src.domains.agents.sms.state_policy import guard_sms_messages


def _copy(original: AnyMessage, clean: BaseMessage) -> AnyMessage:
    if isinstance(original, ToolMessage) and isinstance(clean, ToolMessage):
        return original.model_copy(
            update={
                "content": clean.content,
                "response_metadata": clean.response_metadata,
                "status": clean.status,
            }
        )
    return original.model_copy(
        update={"content": clean.content, "response_metadata": clean.response_metadata}
    )


async def guarded_agent_messages(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    normalized = normalize_sms_messages(messages)
    guarded = await guard_sms_messages(normalized)
    return [_copy(original, clean) for original, clean in zip(normalized, guarded, strict=True)]


class SmsModelBoundary(AgentMiddleware[AgentState[object], LiaRuntimeContext, object]):
    async def awrap_model_call(
        self,
        request: ModelRequest[LiaRuntimeContext],
        handler: Callable[[ModelRequest[LiaRuntimeContext]], Awaitable[ModelResponse[object]]],
    ) -> ModelResponse[object]:
        messages = await guarded_agent_messages(request.messages)
        return await handler(request.override(messages=messages))

    def wrap_model_call(
        self,
        request: ModelRequest[LiaRuntimeContext],
        handler: Callable[[ModelRequest[LiaRuntimeContext]], ModelResponse[object]],
    ) -> ModelResponse[object]:
        if any(
            isinstance(message, ToolMessage) and is_sms_source_message(message)
            for message in request.messages
        ):
            raise PermissionError("SMS sources require the asynchronous live-policy boundary")
        return handler(request)


class SmsSafeSummarization(SummarizationMiddleware):
    """Never turn live SMS evidence into a persistent, unrevocable summary."""

    async def _acreate_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        messages = [
            message
            for message in messages_to_summarize
            if not isinstance(message, ToolMessage) or not is_sms_source_message(message)
        ]
        # A current draft can already quote a tool result. Exclude the whole
        # source-bearing segment, including AI paraphrases, from compression.
        if len(messages) != len(messages_to_summarize):
            messages = [message for message in messages if message.type in {"human", "system"}]
        result = await super()._acreate_summary(messages)
        if not isinstance(result, str):
            raise TypeError("Invalid summary result")
        return result

    def _create_summary(self, messages_to_summarize: list[AnyMessage]) -> str:
        if any(
            isinstance(message, ToolMessage) and is_sms_source_message(message)
            for message in messages_to_summarize
        ):
            messages_to_summarize = [
                message for message in messages_to_summarize if message.type in {"human", "system"}
            ]
        result = super()._create_summary(messages_to_summarize)
        if not isinstance(result, str):
            raise TypeError("Invalid summary result")
        return result
