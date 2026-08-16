"""Local subclass of ChatDeepSeek that round-trips reasoning_content.

The DeepSeek API requires the ``reasoning_content`` field of every prior
assistant message to be echoed back in subsequent requests when the
model is in thinking mode (V4 family by default; V3 ``deepseek-reasoner``
in tool-call flows). The pinned ``langchain-deepseek==1.1.0`` (verified
against the tag source on 2026-08-16, during the ecosystem upgrade) still
does NOT do this round-trip — its ``_get_request_payload`` only reformats
tool/assistant content and ultimately delegates to the parent
``BaseChatOpenAI._get_request_payload`` which serialises messages via
``_convert_message_to_dict`` and drops ``additional_kwargs``.

Concrete failure mode (without this patch):

    openai.BadRequestError: 400 - {
        'error': {
            'message': 'The reasoning_content in the thinking mode must
                        be passed back to the API.',
            'type': 'invalid_request_error',
        }
    }

… raised on the **second** internal LLM call inside any agent loop that
uses tools with a thinking-mode DeepSeek model.

Six upstream PRs over six months have attempted to fix this; none has
been merged. This patch ports the fix from PR #37179 (auto-closed by
a bot for missing issue assignment, not for technical reasons), with
issue #37178 tracking community demand. When upstream lands a release
that round-trips ``reasoning_content``, this module can be deleted and
``ChatDeepSeek`` can be used directly again.

References:
    - https://github.com/langchain-ai/langchain/issues/37178
    - https://github.com/langchain-ai/langchain/pull/37179
    - https://api-docs.deepseek.com/guides/thinking_mode
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek  # type: ignore[import-not-found]


class ChatDeepSeekPatched(ChatDeepSeek):
    """``ChatDeepSeek`` with reasoning_content round-trip in tool flows.

    Drop-in replacement: the override only adds the round-trip logic
    after the parent has built the payload. Models that never produce
    ``reasoning_content`` (e.g. ``deepseek-chat`` V3 with thinking
    disabled) are unaffected — the additional_kwargs dict is empty so
    nothing is injected.
    """

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        # Re-resolve the original messages so we still have access to
        # additional_kwargs (the parent's _convert_message_to_dict drops them).
        original_messages = self._convert_input(input_).to_messages()
        reasoning_contents = [
            msg.additional_kwargs.get("reasoning_content")
            for msg in original_messages
            if isinstance(msg, AIMessage)
        ]

        # Walk the payload's assistant messages in the same order and inject
        # the matching reasoning_content if it exists. Indexing is by occurrence
        # because the payload may also contain system/user/tool messages.
        ai_idx = 0
        for message in payload["messages"]:
            if message["role"] == "assistant":
                if ai_idx < len(reasoning_contents) and reasoning_contents[ai_idx] is not None:
                    message["reasoning_content"] = reasoning_contents[ai_idx]
                ai_idx += 1

        return payload
