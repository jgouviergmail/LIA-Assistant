"""Whether a chat client retries a failed call by itself (ADR-100 amendment 2026-10-23).

The retry wrapper of the structured-output door leaves a failed call to a client that
retries by itself: LangChain's public ``max_retries`` carries the vendor SDK's budget, the
OpenAI wire leaves it to its SDK (``None``), and the Ollama client has no retry at all.
"""

from __future__ import annotations

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from src.infrastructure.llm.client_retries import client_retries_by_itself

pytestmark = pytest.mark.unit


class _Verdict(BaseModel):
    answer: str = Field(description="The answer.")


def test_a_client_says_whether_it_retries_by_itself() -> None:
    """LangChain's public ``max_retries`` carries the vendor SDK's budget; Ollama has none."""
    claude = ChatAnthropic(model="claude-sonnet-5-5", anthropic_api_key=SecretStr("t"))
    assert client_retries_by_itself(claude) is True
    assert client_retries_by_itself(claude.bind_tools([_Verdict])) is True
    assert (
        client_retries_by_itself(
            ChatAnthropic(
                model="claude-sonnet-5-5", anthropic_api_key=SecretStr("t"), max_retries=0
            )
        )
        is False
    )
    # The OpenAI wire leaves the budget to its SDK (None): measured three requests for one 503.
    assert (
        client_retries_by_itself(ChatOpenAI(model="gpt-4.1-mini", api_key=SecretStr("t"))) is True
    )
    assert client_retries_by_itself(ChatOllama(model="llama3.1")) is False
