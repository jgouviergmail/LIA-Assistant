"""Unit tests for the native Responses-API adapter (post-ResponsesLLM migration).

Covers the surface that survived the migration to native ``ChatOpenAI``:
- ``is_responses_api_eligible`` model gating;
- ``_extract_static_prefix`` (dynamic-marker cutoff);
- ``compute_prompt_cache_key`` (stable, prefix-driven, system-only);
- ``create_responses_llm`` builds a ``ChatOpenAICached`` configured for the
  Responses API (+ reasoning summary when an effort is set).
No network / no LLM call.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.infrastructure.llm.providers.responses_adapter import (
    ChatOpenAICached,
    _extract_static_prefix,
    compute_prompt_cache_key,
    create_responses_llm,
    is_responses_api_eligible,
)


class TestEligibility:
    def test_eligible_models(self) -> None:
        assert is_responses_api_eligible("gpt-5-mini")
        assert is_responses_api_eligible("gpt-4.1")
        assert is_responses_api_eligible("o3-mini")

    def test_ineligible_legacy_models(self) -> None:
        assert not is_responses_api_eligible("gpt-4o")
        assert not is_responses_api_eligible("gpt-4-turbo")
        assert not is_responses_api_eligible("gpt-3.5-turbo")


class TestStaticPrefix:
    def test_cuts_at_dynamic_marker(self) -> None:
        from src.core.constants import DYNAMIC_CONTEXT_MARKER

        content = f"STATIC INSTRUCTIONS HERE{DYNAMIC_CONTEXT_MARKER}volatile user stuff"
        assert _extract_static_prefix(content) == "STATIC INSTRUCTIONS HERE"

    def test_no_marker_returns_full_trimmed(self) -> None:
        assert _extract_static_prefix("  just static  ") == "just static"

    def test_literal_tag_mentions_do_not_cut_the_prefix(self) -> None:
        """A static instruction MENTIONING a tag must not truncate the prefix.

        Regression guard: legacy marker list included "<TemporalContext>", so
        response_system_prompt_base (which references that tag in a static rule
        at ~12% of the file) had its cache prefix cut there instead of at the
        canonical marker at ~74%.
        """
        from src.core.constants import DYNAMIC_CONTEXT_MARKER

        content = (
            "Static rule: verify facts against <TemporalContext> below.\n"
            "More static rules referencing <UserRequest> and ## DYNAMIC CONTEXT.\n"
            f"{DYNAMIC_CONTEXT_MARKER}\nvolatile"
        )
        prefix = _extract_static_prefix(content)
        assert "<TemporalContext>" in prefix
        assert "<UserRequest>" in prefix
        assert "volatile" not in prefix

    def test_capped_length(self) -> None:
        big = "x" * 20000
        assert len(_extract_static_prefix(big)) == 8192


class TestComputeCacheKey:
    def test_stable_for_same_static_prefix(self) -> None:
        from src.core.constants import DYNAMIC_CONTEXT_MARKER

        msgs_a = [
            SystemMessage(content=f"ROUTER PROMPT{DYNAMIC_CONTEXT_MARKER}ctx A"),
            HumanMessage(content="question A"),
        ]
        msgs_b = [
            SystemMessage(content=f"ROUTER PROMPT{DYNAMIC_CONTEXT_MARKER}ctx B totally different"),
            HumanMessage(content="question B"),
        ]
        # Same static prefix + different dynamic/user content → SAME cache key.
        assert compute_prompt_cache_key(msgs_a, "gpt-5-mini") == compute_prompt_cache_key(
            msgs_b, "gpt-5-mini"
        )

    def test_differs_for_different_static_prefix(self) -> None:
        a = [SystemMessage(content="PROMPT TYPE A")]
        b = [SystemMessage(content="PROMPT TYPE B")]
        assert compute_prompt_cache_key(a, "gpt-5-mini") != compute_prompt_cache_key(
            b, "gpt-5-mini"
        )

    def test_no_system_message_falls_back_to_model(self) -> None:
        key1 = compute_prompt_cache_key([HumanMessage(content="hi")], "gpt-5-mini")
        key2 = compute_prompt_cache_key([HumanMessage(content="different")], "gpt-5-mini")
        # Falls back to model-based grouping → stable regardless of user text.
        assert key1 == key2
        assert len(key1) == 32


class TestCreateResponsesLLM:
    def test_standard_model_config(self) -> None:
        llm = create_responses_llm("gpt-4.1", api_key="sk-test", temperature=0.5, top_p=0.9)
        assert isinstance(llm, ChatOpenAICached)
        assert llm.model_name == "gpt-4.1"
        assert llm.use_responses_api is True
        # Sampling params applied for non-reasoning use.
        assert llm.temperature == 0.5

    def test_reasoning_model_enables_summary(self) -> None:
        llm = create_responses_llm("gpt-5-mini", api_key="sk-test", reasoning_effort="low")
        assert isinstance(llm, ChatOpenAICached)
        # Reasoning config carries summary=auto so thinking can be streamed.
        assert llm.reasoning == {"effort": "low", "summary": "auto"}


class TestSamplingParametersOnAReasoningModel:
    """A reasoning model gets no sampling parameter, effort asked for or not.

    This is the branch that actually runs. `_prepare_provider_config` carries a
    named "reasoning model parameter filter", and it is unreachable for every
    real OpenAI model: `_create_with_dedicated_client` is consulted FIRST, and
    every `gpt-4.1*`, `gpt-5*` and `o[1-9]*` leaves through the Responses API
    before that filter is ever evaluated (measured 2026-09-06 — only `o0`,
    which does not exist, still reaches it).

    So the protection lives HERE, and it had a hole: it keyed on the effort
    being rendered, not on the model. With no intent configured the translator
    renders nothing, the "standard model" branch was taken, and `top_p` and
    `temperature` went out to a model whose API refuses them the moment they
    are not neutral (`top_p=0.9` -> 400 *Unsupported parameter*, measured
    against the real API on `gpt-5.6-luna`; `top_p=1.0` is tolerated, which is
    the only reason nothing broke).
    """

    def test_no_effort_asked_still_sends_no_sampling_parameter(self) -> None:
        llm = create_responses_llm(
            model="gpt-5.6-luna", api_key="k", temperature=0.3, top_p=0.9, max_tokens=64
        )
        assert llm.top_p is None
        assert llm.temperature is None

    def test_an_effort_asked_sends_none_either(self) -> None:
        llm = create_responses_llm(
            model="gpt-5.6-luna",
            api_key="k",
            temperature=0.3,
            top_p=0.9,
            max_tokens=64,
            reasoning_effort="low",
        )
        assert llm.top_p is None
        assert llm.temperature is None

    def test_a_standard_model_keeps_both(self) -> None:
        """The 18 slots on `gpt-4.1*` must be untouched: that model accepts
        `top_p=0.9` (measured against the real API)."""
        llm = create_responses_llm(
            model="gpt-4.1-mini", api_key="k", temperature=0.3, top_p=0.9, max_tokens=64
        )
        assert llm.top_p == 0.9
        assert llm.temperature == 0.3

    def test_an_unknown_model_is_treated_as_standard(self) -> None:
        """The fallback stays permissive: only a model KNOWN to reason loses
        its sampling parameters."""
        llm = create_responses_llm(
            model="gpt-4.1-turbo-2026", api_key="k", temperature=0.5, top_p=0.8, max_tokens=64
        )
        assert llm.top_p == 0.8


class TestOnePredicateForReasoningModels:
    """ "Is this a reasoning model" is asked in two places. It must be ANSWERED
    in one.

    Both the Responses adapter and the `init_chat_model` fallback need the
    answer, and they used to compute it separately — cache, then name pattern,
    written twice. Only ONE of the two branches runs for any real model, so a
    fix applied to the other passes its tests and changes nothing in
    production. That is not a hypothetical: it is exactly the mistake this
    change was about to ship (2026-09-06).
    """

    def test_the_name_pattern_is_read_from_a_single_module(self) -> None:
        import subprocess

        out = subprocess.run(
            ["git", "grep", "-l", "REASONING_MODELS_PATTERN", "--", "src"],
            capture_output=True,
            text=True,
            cwd=_repo_root(),
        ).stdout.split()
        readers = {f for f in out if not f.endswith("core/constants.py")}
        assert readers == {"src/infrastructure/llm/model_capabilities_cache.py"}, (
            "the reasoning-model pattern gained a second reader: route it through "
            "`model_capabilities_cache.is_reasoning_model` instead, or the two "
            f"copies will drift. Readers: {sorted(readers)}"
        )

    def test_the_catalogue_wins_over_the_name(self) -> None:
        """An administrator turning `is_reasoning_model` off means it."""
        from unittest.mock import patch

        from src.infrastructure.llm.model_capabilities_cache import is_reasoning_model
        from src.infrastructure.llm.model_profiles import ModelProfile

        with patch(
            "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache.get",
            return_value=ModelProfile(is_reasoning_model=False),
        ):
            assert is_reasoning_model("gpt-5.6-luna") is False

    def test_an_unseeded_model_falls_back_to_the_name(self) -> None:
        from unittest.mock import patch

        from src.infrastructure.llm.model_capabilities_cache import is_reasoning_model

        with patch(
            "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache.get",
            return_value=None,
        ):
            assert is_reasoning_model("gpt-5.9-unseeded") is True
            assert is_reasoning_model("gpt-4.1-mini") is False


def _repo_root() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parents[5])
