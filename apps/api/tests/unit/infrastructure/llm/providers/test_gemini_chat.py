"""Unit tests for the Gemini chat client: the SDK never runs a tool itself."""

from __future__ import annotations

import pytest
from google.genai import _extra_utils
from langchain_core.messages import HumanMessage

from src.infrastructure.llm.providers.gemini_chat import ChatGeminiNoAfc

pytestmark = pytest.mark.unit


def _llm() -> ChatGeminiNoAfc:
    return ChatGeminiNoAfc(model="gemini-3.7-flash", google_api_key="key-for-a-local-build")


def test_every_request_switches_the_sdks_automatic_function_calling_off() -> None:
    # Production 2026-10-03: with the SDK's default, every briefing synthesis
    # logged « AFC is enabled with max remote calls: 10. » — for a feature that
    # can never act here, since LangGraph runs every tool.
    request = _llm()._prepare_request([HumanMessage("hi")])

    assert request["config"].automatic_function_calling.disable is True
    assert _extra_utils.should_disable_afc(request["config"]) is True


def test_the_stock_client_leaves_it_on() -> None:
    # The premise of the subclass, pinned: should a langchain-google-genai
    # release switch AFC off by itself, this test says the subclass can go.
    from langchain_google_genai import ChatGoogleGenerativeAI

    stock = ChatGoogleGenerativeAI(model="gemini-3.7-flash", google_api_key="key-for-a-local-build")
    request = stock._prepare_request([HumanMessage("hi")])

    assert _extra_utils.should_disable_afc(request["config"]) is False


def test_a_caller_that_asks_for_it_explicitly_is_obeyed() -> None:
    request = _llm()._prepare_request(
        [HumanMessage("hi")], automatic_function_calling={"disable": False}
    )

    assert request["config"].automatic_function_calling.disable is False
