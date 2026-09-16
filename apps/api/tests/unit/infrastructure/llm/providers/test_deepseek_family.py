"""DeepSeek's thinking family is recognised by ONE declaration, current names included.

DeepSeek renamed its flagship: the API's model is ``deepseek-flash``
(DeepSeek-V4.1-Flash) and ``deepseek-v4-flash`` is a retired alias still
accepted. Three places in LIA recognised the family by their own private
``startswith("deepseek-v4-")`` -- the profile rule, the adapter's V4 branch
and the structured-output ``tool_choice`` detour -- so a row an operator
created for ``deepseek-flash`` (``is_reasoning_model=true``, provenance
``verified``) resolved to NO family: the UI offered no ladder, an explicit
``none`` sent no ``thinking: disabled``, the V3 ``deepseek-chat`` output cap of
8 192 applied to a model that emits 384 K, and every short-budget call spent
its whole ``max_tokens`` on the hidden chain of thought (measured 2026-09-12 on
production: the reminder job asked for 150 tokens and received 150 tokens of
reasoning and an empty answer -- every reminder read « 🔔 » and nothing else).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.llm.providers.adapter import ProviderAdapter
from src.infrastructure.llm.reasoning.profiles import (
    is_deepseek_thinking_model,
    resolve_reasoning_profile,
)
from src.infrastructure.llm.structured_output import _is_v4_thinking_enabled

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[5] / "src"
_PROFILES = _SRC / "core" / "reasoning_profiles.py"


# ---------------------------------------------------------------------------
# The family rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    ["deepseek-flash", "deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"],
)
def test_every_current_and_legacy_v4_name_resolves_to_the_toggle_family(model: str) -> None:
    assert resolve_reasoning_profile("deepseek", model).family == "deepseek_toggle"
    assert is_deepseek_thinking_model(model)


@pytest.mark.parametrize("model", ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"])
def test_the_v3_names_stay_outside_the_toggle_family(model: str) -> None:
    assert resolve_reasoning_profile("deepseek", model).family == "none"
    assert not is_deepseek_thinking_model(model)


def test_the_ladder_is_the_one_the_vendor_documents() -> None:
    """``low/high/max`` per api-docs.deepseek.com/guides/thinking_mode, plus the off switch."""
    assert resolve_reasoning_profile("deepseek", "deepseek-flash").levels == (
        "none",
        "low",
        "high",
        "max",
    )


# ---------------------------------------------------------------------------
# The adapter reads the same declaration
# ---------------------------------------------------------------------------


def _deepseek_constructor_kwargs(
    model: str, max_tokens: int = 10_000, **passed: Any
) -> dict[str, Any]:
    mock_llm = MagicMock(spec=BaseChatModel)
    with (
        patch(
            "src.infrastructure.llm.providers._deepseek_patched.ChatDeepSeekPatched",
            return_value=mock_llm,
        ) as deepseek,
        patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_api_key",
            return_value="sk-test",
        ),
    ):
        ProviderAdapter.create_llm(
            provider="deepseek",
            model=model,
            temperature=0.3,
            max_tokens=max_tokens,
            streaming=True,
            llm_type="response",
            **passed,
        )
    assert deepseek.called
    return dict(deepseek.call_args.kwargs)


def test_an_explicit_none_switches_thinking_off_on_the_current_name() -> None:
    kwargs = _deepseek_constructor_kwargs(
        "deepseek-flash", reasoning_effort=ReasoningIntent(level="none")
    )
    assert kwargs["extra_body"]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in kwargs


def test_a_depth_switches_thinking_on_with_the_vendor_effort() -> None:
    kwargs = _deepseek_constructor_kwargs(
        "deepseek-flash", reasoning_effort=ReasoningIntent(level="low")
    )
    assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}
    assert kwargs["reasoning_effort"] == "low"


def test_the_v3_output_cap_does_not_apply_to_the_current_name() -> None:
    """8 192 is ``deepseek-chat``'s ceiling; the V4 family emits up to 384 K."""
    kwargs = _deepseek_constructor_kwargs("deepseek-flash")
    assert kwargs["max_tokens"] == 10_000


def test_the_family_output_cap_is_the_catalogue_row_when_it_is_known() -> None:
    """The catalogue is the authority on what a model can do (ADR-244).

    The adapter's 64 000 literal dates from the V4 launch; the vendor now
    documents 384 K for ``deepseek-flash`` and the catalogue row says so. A
    document generation asking for 200 000 must not be cut to 64 000 by a
    number the catalogue contradicts.
    """
    mock_llm = MagicMock(spec=BaseChatModel)
    profile = ModelProfile(
        model_id="deepseek-flash",
        max_input_tokens=1_000_000,
        max_output_tokens=384_000,
        is_reasoning_model=True,
    )
    with (
        patch(
            "src.infrastructure.llm.providers._deepseek_patched.ChatDeepSeekPatched",
            return_value=mock_llm,
        ) as deepseek,
        patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_api_key",
            return_value="sk-test",
        ),
        patch.object(ModelCapabilitiesCache, "get", return_value=profile),
    ):
        ProviderAdapter.create_llm(
            provider="deepseek",
            model="deepseek-flash",
            temperature=0.3,
            max_tokens=200_000,
            streaming=True,
            llm_type="document_generation",
        )
    assert deepseek.call_args.kwargs["max_tokens"] == 200_000


def test_the_family_output_cap_falls_back_when_the_catalogue_is_silent() -> None:
    with patch.object(ModelCapabilitiesCache, "get", return_value=None):
        kwargs = _deepseek_constructor_kwargs("deepseek-flash", max_tokens=200_000)
    assert kwargs["max_tokens"] == 64_000


# ---------------------------------------------------------------------------
# The structured-output detour reads the same declaration
# ---------------------------------------------------------------------------


def _llm_named(model: str, extra_body: dict[str, Any] | None = None) -> MagicMock:
    llm = MagicMock(spec=BaseChatModel)
    llm.model_name = model
    llm.extra_body = extra_body
    return llm


def test_the_current_name_thinks_by_default_for_the_tool_choice_detour() -> None:
    assert _is_v4_thinking_enabled(_llm_named("deepseek-flash")) is True
    assert (
        _is_v4_thinking_enabled(_llm_named("deepseek-flash", {"thinking": {"type": "disabled"}}))
        is False
    )


def test_a_v3_name_never_takes_the_detour() -> None:
    assert _is_v4_thinking_enabled(_llm_named("deepseek-chat")) is False


# ---------------------------------------------------------------------------
# The shipped catalogue carries the vendor's current name
# ---------------------------------------------------------------------------


def test_the_seed_carries_the_current_name_with_the_documented_ladder() -> None:
    """A fresh install must be able to pick ``deepseek-flash`` and see its ladder.

    Reads the seed through the family-coverage test's own parser, so the
    columns are the ones the INSERT declares, not positions.
    """
    from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

    rows = {row["model_name"]: row for row in _catalogue_rows() if row["provider"] == "deepseek"}
    flash = rows["deepseek-flash"]
    assert flash["is_reasoning_model"] == "true"
    assert flash["is_active"] == "true"
    assert flash["reasoning_doc_i18n_key"] == "deepseek_v4"
    assert flash["max_output_tokens"] == "384000"
    for name in ("deepseek-flash", "deepseek-v4-flash", "deepseek-v4-pro"):
        # the parser strips the outer quotes and leaves the ``::jsonb`` cast
        assert rows[name]["reasoning_enum_values"].startswith(
            '["none", "low", "high", "max"]'
        ), name


# ---------------------------------------------------------------------------
# One declaration: no reader may keep a private copy of the prefix test
# ---------------------------------------------------------------------------


def test_no_module_recognises_the_family_by_its_own_prefix_test() -> None:
    """The prefix list lives in ``profiles.py`` and nowhere else.

    Three private copies is how ``deepseek-flash`` fell through every one of
    them at once; a fourth would be written the same way.
    """
    pattern = re.compile(r"""startswith\(\s*['"]deepseek-v4""")
    offenders = [
        str(path.relative_to(_SRC))
        for path in _SRC.rglob("*.py")
        if path != _PROFILES and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], offenders
