"""The Gemini chat client LIA builds: tools are declared, never run by the SDK.

google-genai turns on Automatic Function Calling (AFC) unless a request says
otherwise: handed Python callables, the SDK would run them itself, up to ten
remote calls per request. LIA never hands it one — LangChain sends function
DECLARATIONS and LangGraph runs every tool, through the gate that records it
(ADR-263) — so AFC can do nothing here but speak: one INFO line on every call
(« AFC is enabled with max remote calls: 10. »), and a WARNING per process that
direct use of AFC in ``generate_content`` is not recommended (production
2026-10-03, every briefing synthesis). Saying so on every request is what
silences both: the SDK then calls the model directly.

This module exists because ``adapter.py`` sits at its size cap.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

__all__ = ["ChatGeminiNoAfc"]


class ChatGeminiNoAfc(ChatGoogleGenerativeAI):
    """``ChatGoogleGenerativeAI`` whose requests switch the SDK's AFC off."""

    def _prepare_request(self, messages: list[BaseMessage], **kwargs: Any) -> dict[str, Any]:
        # The one funnel of _generate, _agenerate, _stream and _astream: the
        # setting lands in the request's GenerateContentConfig.
        kwargs.setdefault("automatic_function_calling", {"disable": True})
        return super()._prepare_request(messages, **kwargs)
