"""The largest output budget a model accepts — one answer, for every provider.

Production 2026-10-18: three slots kept the ``max_tokens`` (200 000) chosen for
the model they ran on before, after an administrator switched them to a model
whose catalogue row VOUCHES for a 128 000 output cap. The provider refused every
call (« max_tokens: 200000 > 128000 »): two document requests, six refusals,
and two more slots in the same state that simply had not run yet. The catalogue
knew the cap all along; only two provider branches capped anything, each its
own way, and every other client sent the raw value.

The cap is trusted where the catalogue's provenance vouches for it — the same
rule as the context window (ADR-244): ``imported`` and ``verified`` rows carry
it (``max_output_tokens`` is a ``CORRECTABLE_FIELDS`` column), a ``declared``
row only carries column defaults, and what an Ollama server says at discovery
is a constant, not a limit. The oracle is what the request CARRIES: the
Article-12 reader normalises the four spellings of the output cap the real
clients publish (ADR-263 lot 7), so these tests read what would be sent and
recorded, never a mock's arguments.
"""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import structlog
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.config import settings
from src.core.constants import LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.document_generation.schemas import DocumentType
from src.domains.document_generation.service import prompt_values
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm import output_cap
from src.infrastructure.llm.catalogue.field_mapping import RegistryFacts
from src.infrastructure.llm.factory import clear_llm_instance_cache, get_llm
from src.infrastructure.llm.inference_params import capture_inference_params
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.llm.output_cap import cap_max_tokens, output_cap_for
from src.infrastructure.llm.providers.adapter import ProviderAdapter, ProviderType

pytestmark = pytest.mark.unit

_OVERRIDE = "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override"
_REGISTRY = "src.infrastructure.llm.output_cap.registry_facts"


@pytest.fixture(autouse=True)
def _isolated_catalogue() -> Generator[None]:
    """Each test describes the catalogue it needs; nothing leaks to the next."""
    saved = (
        dict(ModelCapabilitiesCache._cache),
        dict(ModelCapabilitiesCache._provider_by_model),
        dict(ModelCapabilitiesCache._discovered),
        dict(ModelCapabilitiesCache._discovered_provider),
    )
    clear_llm_instance_cache()
    output_cap.registry_states_output_cap.cache_clear()
    yield
    output_cap.registry_states_output_cap.cache_clear()
    (
        ModelCapabilitiesCache._cache,
        ModelCapabilitiesCache._provider_by_model,
        ModelCapabilitiesCache._discovered,
        ModelCapabilitiesCache._discovered_provider,
    ) = saved
    clear_llm_instance_cache()


def _install(
    model: str,
    *,
    max_output_tokens: int,
    provenance: str = "verified",
    kind: str = "chat",
    provider: str = "anthropic",
) -> None:
    """A catalogue row, as ``ModelCapabilitiesCache.load_from_db`` would build it."""
    ModelCapabilitiesCache._cache[model] = ModelProfile(
        model_id=model,
        max_output_tokens=max_output_tokens,
        capability_provenance=provenance,
        kind=kind,
    )
    ModelCapabilitiesCache._provider_by_model[model] = provider


def _sent_output_cap(llm: BaseChatModel) -> int | None:
    """What the request carries, through the reader that files it (ADR-263 lot 7)."""
    params = llm._get_invocation_params()
    return capture_inference_params(params).max_output_tokens


class TestWhoseCapIsKnown:
    @pytest.mark.parametrize("provenance", ["imported", "verified"])
    def test_a_curated_row_vouches_for_its_cap(self, provenance: str) -> None:
        _install("cap-curated", max_output_tokens=128_000, provenance=provenance)

        assert output_cap_for("anthropic", "cap-curated") == 128_000

    def test_a_declared_row_carries_column_defaults_and_vouches_for_nothing(self) -> None:
        # Nobody curated the row: trusting its figure would cut a real budget
        # for no provider reason.
        _install("cap-declared", max_output_tokens=16_384, provenance="declared")

        assert output_cap_for("openai", "cap-declared") is None

    @pytest.mark.parametrize("provenance", ["imported", "verified"])
    def test_the_column_default_no_registry_states_is_no_evidence(self, provenance: str) -> None:
        # Provenance is row-level, its evidence field-level, and two writers can
        # leave the default in place while stamping the row: the sync promotes
        # a row as soon as ONE field is corroborated, and the catalogue editor
        # stamps ``verified`` on any save, resending the untouched default.
        _install(
            "cap-placeholder",
            max_output_tokens=LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS,
            provenance=provenance,
        )

        with patch(_REGISTRY, return_value=None):
            assert output_cap_for("perplexity", "cap-placeholder") is None

    def test_the_column_default_is_no_evidence_where_the_registries_state_another_cap(
        self,
    ) -> None:
        # The registries know the model and give it a different figure: the
        # row still holds the default nobody replaced, never the model's cap.
        _install("cap-other-figure", max_output_tokens=LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS)

        with patch(_REGISTRY, return_value=RegistryFacts(max_output_tokens=16_384)):
            assert output_cap_for("openai", "cap-other-figure") is None

    def test_the_column_default_a_registry_states_is_a_real_cap(self) -> None:
        # Older models really do stop at that figure, and the vendored
        # registries say so: refusing it would send a budget the provider
        # refuses, the incident itself.
        _install("cap-real-default", max_output_tokens=LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS)
        stated = RegistryFacts(max_output_tokens=LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS)

        with patch(_REGISTRY, return_value=stated):
            assert output_cap_for("openai", "cap-real-default") == (
                LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS
            )
            assert cap_max_tokens("openai", "cap-real-default", 16_000, llm_type="router") == (
                LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS
            )

    def test_what_a_server_says_at_discovery_is_not_an_output_cap(self) -> None:
        # The discovered layer publishes OLLAMA_DISCOVERED_MAX_OUTPUT_TOKENS, a
        # constant no server declared. The provider below is deliberately one
        # that HAS a cap: the provenance alone must refuse the figure.
        ModelCapabilitiesCache._discovered["cap-discovered:7b"] = ModelProfile(
            model_id="cap-discovered:7b",
            max_output_tokens=8_192,
            capability_provenance="discovered",
        )
        ModelCapabilitiesCache._discovered_provider["cap-discovered:7b"] = "openai"

        assert output_cap_for("openai", "cap-discovered:7b") is None

    def test_a_self_hosted_runtime_enforces_no_output_cap(self) -> None:
        # A registry may list an output limit for an open model; the local
        # server generates until its context is full and refuses nothing.
        _install("cap-local", max_output_tokens=8_192, provenance="imported", provider="ollama")

        assert output_cap_for("ollama", "cap-local") is None

    def test_a_model_that_does_not_chat_has_no_output_cap(self) -> None:
        _install("cap-voice", max_output_tokens=16_384, kind="tts")

        assert output_cap_for("openai", "cap-voice") is None

    def test_a_non_positive_cap_is_no_cap(self) -> None:
        _install("cap-zero", max_output_tokens=0, provenance="imported")

        assert output_cap_for("openai", "cap-zero") is None

    def test_an_unknown_model_has_no_known_cap(self) -> None:
        assert output_cap_for("anthropic", "cap-nobody-knows") is None

    def test_an_entry_shaped_otherwise_means_no_known_cap_never_an_error(self) -> None:
        # The resolution runs on EVERY LLM instantiation: a cache entry shaped
        # differently (a stand-in, a future rename) must degrade, as the
        # reasoning seam's profile read does, never raise inside the factory.
        stand_in = {"cap-stand-in": SimpleNamespace(model_id="cap-stand-in")}
        with patch.dict(ModelCapabilitiesCache._cache, stand_in):
            assert output_cap_for("anthropic", "cap-stand-in") is None
            assert (
                cap_max_tokens("anthropic", "cap-stand-in", 200_000, llm_type="subagent") == 200_000
            )

    def test_a_dated_model_id_finds_its_curated_row(self) -> None:
        _install("cap-dated", max_output_tokens=32_768, provenance="imported")

        assert output_cap_for("openai", "cap-dated-2026-01-01") == 32_768


class TestTheRequestNeverAsksMoreThanTheModelAccepts:
    def test_a_request_above_the_cap_is_capped(self) -> None:
        _install("cap-above", max_output_tokens=128_000)

        assert cap_max_tokens("anthropic", "cap-above", 200_000, llm_type="subagent") == 128_000

    @pytest.mark.parametrize("requested", [128_000, 5_000])
    def test_a_request_within_the_cap_is_sent_as_configured(self, requested: int) -> None:
        _install("cap-within", max_output_tokens=128_000)

        assert cap_max_tokens("anthropic", "cap-within", requested, llm_type="subagent") == (
            requested
        )

    def test_without_a_known_cap_the_request_is_sent_as_configured(self) -> None:
        _install("cap-unvouched", max_output_tokens=8_192, provenance="declared")

        assert cap_max_tokens("anthropic", "cap-unvouched", 200_000, llm_type="subagent") == (
            200_000
        )

    def test_capping_is_said_once_per_slot_model_and_value(self) -> None:
        _install("cap-said", max_output_tokens=128_000)

        with structlog.testing.capture_logs() as captured:
            for _ in range(3):
                cap_max_tokens("anthropic", "cap-said", 200_000, llm_type="meeting_synthesis")
            cap_max_tokens("anthropic", "cap-said", 150_000, llm_type="meeting_synthesis")

        said = [e for e in captured if e["event"] == "llm_max_tokens_above_model_cap"]
        assert [(e["requested"], e["cap"]) for e in said] == [
            (200_000, 128_000),
            (150_000, 128_000),
        ]
        assert all(e["log_level"] == "warning" for e in said)
        assert said[0]["llm_type"] == "meeting_synthesis"
        assert said[0]["model"] == "cap-said"


class TestEveryReaderSeesTheBudgetThatIsSent:
    """The resolved slot carries the budget the provider will accept."""

    def test_the_resolved_slot_is_capped_and_the_code_default_untouched(self) -> None:
        _install("cap-slot", max_output_tokens=128_000)
        default_budget = LLM_DEFAULTS["subagent"].max_tokens
        override = {"provider": "anthropic", "model": "cap-slot", "max_tokens": 200_000}

        with patch(_OVERRIDE, return_value=override):
            config = get_llm_config_for_agent(settings, "subagent")

        assert config.max_tokens == 128_000
        assert LLM_DEFAULTS["subagent"].max_tokens == default_budget

    def test_a_slot_within_its_cap_is_returned_unchanged(self) -> None:
        _install("cap-slot-ok", max_output_tokens=128_000)
        override = {"provider": "anthropic", "model": "cap-slot-ok", "max_tokens": 100_000}

        with patch(_OVERRIDE, return_value=override):
            config = get_llm_config_for_agent(settings, "subagent")

        assert config.max_tokens == 100_000

    def test_the_document_prompt_publishes_a_length_the_model_can_write(self) -> None:
        # The prompt derives its length budget from the slot (ADR-184): with
        # the raw 200 000 it promised the model 110 000 words it could not
        # write, and a cut document is refused (ADR-275).
        _install("cap-document", max_output_tokens=128_000)
        override = {"provider": "anthropic", "model": "cap-document", "max_tokens": 200_000}

        with patch(_OVERRIDE, return_value=override):
            capped = prompt_values(
                doc_type=DocumentType.TXT, language="en", instructions="i", source_data=""
            )
        with patch(_OVERRIDE, return_value={**override, "max_tokens": 128_000}):
            at_the_cap = prompt_values(
                doc_type=DocumentType.TXT, language="en", instructions="i", source_data=""
            )

        assert capped["length_budget_words"] == at_the_cap["length_budget_words"]


class TestTheClientCarriesTheCappedBudget:
    def test_the_incident_slot_now_sends_what_the_model_accepts(self) -> None:
        """2026-10-18: the configured 200 000 reached the provider unchanged."""
        _install("cap-incident", max_output_tokens=128_000)
        override = {"provider": "anthropic", "model": "cap-incident", "max_tokens": 200_000}

        with patch(_OVERRIDE, return_value=override):
            llm = get_llm("document_generation")

        assert _sent_output_cap(llm) == 128_000

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("anthropic", "cap-branch-claude"),
            ("openai", "gpt-5-cap-branch"),  # Responses API client
            ("openai", "gpt-4-turbo-cap-branch"),  # init_chat_model client
            ("deepseek", "deepseek-chat-cap-branch"),
            ("gemini", "gemini-3-cap-branch"),
            ("qwen", "qwen-cap-branch"),
            ("perplexity", "sonar-cap-branch"),
        ],
    )
    def test_every_provider_branch_receives_the_capped_budget(
        self, provider: ProviderType, model: str
    ) -> None:
        _install(model, max_output_tokens=1_000, provider=provider)

        llm = ProviderAdapter.create_llm(
            provider=provider,
            model=model,
            temperature=0.5,
            max_tokens=5_000,
            streaming=False,
            llm_type="response",
        )

        assert _sent_output_cap(llm) == 1_000

    def test_a_self_hosted_runtime_receives_the_configured_budget(self) -> None:
        _install("cap-branch:7b", max_output_tokens=1_000, provenance="imported", provider="ollama")

        llm = ProviderAdapter.create_llm(
            provider="ollama",
            model="cap-branch:7b",
            temperature=0.5,
            max_tokens=5_000,
            streaming=False,
            llm_type="response",
        )

        assert _sent_output_cap(llm) == 5_000
