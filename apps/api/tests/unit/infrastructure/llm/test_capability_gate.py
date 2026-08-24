"""One decision about model fit, two behaviours depending on where it came from."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from src.infrastructure.llm.capability_gate import (
    GateVerdict,
    evaluate_slot_fit,
    report_configured_model,
)
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile


@pytest.fixture(autouse=True)
def _restore_cache() -> Generator[None]:
    saved = dict(ModelCapabilitiesCache._cache)
    yield
    ModelCapabilitiesCache._cache = saved


def _install(model: str, **caps: object) -> None:
    ModelCapabilitiesCache._cache[model] = ModelProfile(model_id=model, **caps)  # type: ignore[arg-type]


def test_a_fitting_model_satisfies_the_slot() -> None:
    _install("fits", supports_structured_output=True, kind="chat")
    assert evaluate_slot_fit("query_analyzer", "fits") == GateVerdict(
        satisfied=True, missing=(), wrong_kind=False
    )


def test_a_missing_capability_is_named() -> None:
    _install("blind", supports_vision=False, kind="chat")
    verdict = evaluate_slot_fit("vision_analysis", "blind")
    assert verdict is not None
    assert verdict.satisfied is False
    assert verdict.missing == ("vision",)
    assert verdict.wrong_kind is False


def test_a_wrong_kind_is_reported_separately() -> None:
    """``required_kind`` and ``required_capabilities`` are different failures."""
    _install("a-chat-model", supports_vision=True, kind="chat")
    verdict = evaluate_slot_fit("image_generation", "a-chat-model")
    assert verdict is not None
    assert verdict.wrong_kind is True
    assert verdict.satisfied is False


def test_an_unknown_model_yields_no_verdict() -> None:
    """No profile means no evidence — never a rejection.

    A live Ollama pull is outside the catalogue and must stay usable.
    """
    ModelCapabilitiesCache._cache.pop("ghost", None)
    assert evaluate_slot_fit("query_analyzer", "ghost") is None


def test_an_unknown_slot_yields_no_verdict() -> None:
    _install("fits", supports_structured_output=True, kind="chat")
    assert evaluate_slot_fit("not-a-slot", "fits") is None


def test_reporting_a_configured_model_never_raises() -> None:
    """A human decision is counted and logged, never overridden."""
    _install("blind", supports_vision=False, kind="chat")
    report_configured_model("vision_analysis", "blind")


def test_reporting_a_fitting_model_is_silent() -> None:
    _install("sees", supports_vision=True, kind="chat")
    report_configured_model("vision_analysis", "sees")


def test_every_declared_capability_has_a_profile_attribute() -> None:
    """The gate and the API filter must know the same vocabulary."""
    from src.domains.llm_config.service import KNOWN_MODEL_CAPABILITIES
    from src.infrastructure.llm.capability_gate import _CAPABILITY_ATTRS

    assert set(_CAPABILITY_ATTRS) == set(KNOWN_MODEL_CAPABILITIES)
    for attribute in _CAPABILITY_ATTRS.values():
        assert hasattr(ModelProfile(), attribute), attribute


def test_a_profile_silent_about_a_capability_is_not_rejected() -> None:
    """Absence of evidence is never a rejection, and never an exception.

    This runs on the resolution chokepoint, once per LLM instantiation. A
    profile shaped differently — a stand-in, a future field rename — must
    produce "no evidence", not an ``AttributeError`` that turns a reporting
    helper into a failed request.
    """
    from types import SimpleNamespace

    ModelCapabilitiesCache._cache["partial"] = SimpleNamespace(  # type: ignore[assignment]
        model_id="partial", reasoning_widget="none"
    )
    verdict = evaluate_slot_fit("query_agent", "partial")
    assert verdict is not None
    assert verdict.missing == ()
    assert verdict.satisfied is True
    report_configured_model("query_agent", "partial")
