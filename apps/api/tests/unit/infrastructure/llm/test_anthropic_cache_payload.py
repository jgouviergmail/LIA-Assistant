"""Anthropic prompt-cache payload shaping (Lot F, 2026-09).

Verified against the provider documentation (2026-09-02): Anthropic caching is
NEVER automatic by default — it requires either block-level ``cache_control``
breakpoints or a ROOT-level ``cache_control`` field (the documented mode for
multi-turn/agentic conversations, where the breakpoint auto-moves to the last
cacheable block as the history grows). Before this lot, LIA marked only the
static system block: on Anthropic the growing ReAct message history was never
cached — measured 2026-09-02, 0 message blocks marked, no root field.

The tests drive the REAL ``factory.py`` patch through a fake provider client,
exactly like the proof harness that established the defect.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.llm_config.constants import LLM_DEFAULTS

pytestmark = [pytest.mark.unit]

STATIC_SYSTEM = (
    "You are LIA.\n"
    + ("Static instruction line.\n" * 400)
    + DYNAMIC_CONTEXT_MARKER
    + "\nCurrent datetime: 2026-09-02T00:00:00Z\n"
)


class FakeAnthropic:
    """Exposes ``_get_request_payload`` like ``langchain_anthropic`` does."""

    callbacks = None

    def __init__(self, system: Any = STATIC_SYSTEM) -> None:
        self._system = system

    def _get_request_payload(self, input_: Any, stop: Any = None, **kwargs: Any) -> dict:
        return {
            "system": self._system,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Prepare ma journee."}]},
                {"role": "assistant", "content": [{"type": "tool_use", "name": "t1"}]},
                {"role": "user", "content": [{"type": "tool_result", "content": "A" * 4000}]},
            ],
        }


@pytest.fixture
def patched_llm(monkeypatch: pytest.MonkeyPatch):
    """A ``get_llm('react_agent')`` retargeted to Anthropic over the fake client."""
    import src.infrastructure.llm.factory as factory

    fake = FakeAnthropic()

    class _Adapter:
        @staticmethod
        def create_llm(**_kwargs: Any) -> FakeAnthropic:
            return fake

    cfg = LLM_DEFAULTS["react_agent"].model_copy(
        update={"provider": "anthropic", "model": "claude-opus-5"}
    )
    monkeypatch.setattr(factory, "ProviderAdapter", _Adapter)
    monkeypatch.setattr(factory, "get_llm_config_for_agent", lambda *_a, **_k: cfg)
    monkeypatch.setattr(factory, "_llm_instance_cache", {})
    return factory.get_llm("react_agent")


class TestAnthropicCachePayload:
    def test_static_system_block_keeps_its_breakpoint(self, patched_llm) -> None:
        """The proven static-prefix split stays exactly as it was."""
        payload = patched_llm._get_request_payload(None)
        system = payload["system"]
        assert isinstance(system, list)
        assert "cache_control" in system[0]
        assert "cache_control" not in system[1]

    def test_root_cache_control_covers_the_growing_history(self, patched_llm) -> None:
        """The documented multi-turn mode: a root-level cache_control field."""
        payload = patched_llm._get_request_payload(None)
        assert payload.get("cache_control") == {"type": "ephemeral"}

    def test_caller_supplied_cache_control_still_stripped(self, patched_llm) -> None:
        """Invoke-time kwargs cannot double or corrupt the breakpoints."""
        payload = patched_llm._get_request_payload(None, cache_control={"type": "custom"})
        # The root field is OURS, never the caller's raw kwarg.
        assert payload.get("cache_control") == {"type": "ephemeral"}

    def test_root_field_withheld_at_four_explicit_breakpoints(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Automatic + 4 explicit breakpoints is a documented 400: never emit it."""
        import src.infrastructure.llm.factory as factory

        four_marked = [
            {"type": "text", "text": f"block {i}", "cache_control": {"type": "ephemeral"}}
            for i in range(4)
        ]
        fake = FakeAnthropic(system=four_marked)

        class _Adapter:
            @staticmethod
            def create_llm(**_kwargs: Any) -> FakeAnthropic:
                return fake

        cfg = LLM_DEFAULTS["react_agent"].model_copy(
            update={"provider": "anthropic", "model": "claude-opus-5"}
        )
        monkeypatch.setattr(factory, "ProviderAdapter", _Adapter)
        monkeypatch.setattr(factory, "get_llm_config_for_agent", lambda *_a, **_k: cfg)
        monkeypatch.setattr(factory, "_llm_instance_cache", {})

        payload = factory.get_llm("react_agent")._get_request_payload(None)
        assert "cache_control" not in payload
