"""What was actually SENT to the model, in one vocabulary (ADR-263, lot 7).

Every property below comes from a probe run against the real adapters rather
than from the documentation, and two of them changed the design:

- **The output cap has three spellings.** ``max_completion_tokens`` (OpenAI),
  ``max_tokens`` (Anthropic), ``max_output_tokens`` (Google). Recording the
  provider's own spelling would produce a register where one concept wears
  three names and compares with nothing.
- **A blind capture is a secret risk.** None of the four adapters leaks a key
  today; nothing guarantees the next one will not. So the rule is the export's
  rule: an ALLOWLIST, never a dump.

The third property is a consequence of ADR-245: reasoning has ONE stored shape
across providers, so the register reads that vocabulary and never
``thinking_level`` or ``reasoning_effort``.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.inference_params import (
    INFERENCE_PARAM_ALLOWLIST,
    InferenceParams,
    capture_inference_params,
)

pytestmark = [pytest.mark.unit]


class TestTheOutputCapHasOneName:
    @pytest.mark.parametrize(
        "spelling",
        ["max_completion_tokens", "max_tokens", "max_output_tokens"],
        ids=["openai", "anthropic", "google"],
    )
    def test_every_provider_s_spelling_lands_in_ONE_column(self, spelling: str) -> None:
        captured = capture_inference_params({"_type": "x", spelling: 1200})

        assert captured.max_output_tokens == 1200

    def test_two_spellings_at_once_do_not_multiply(self) -> None:
        """A provider that publishes both must not make the value ambiguous."""
        captured = capture_inference_params(
            {"_type": "x", "max_tokens": 900, "max_completion_tokens": 900}
        )

        assert captured.max_output_tokens == 900


class TestAnAbsentParameterStaysABSENT:
    def test_nothing_is_invented_for_what_was_not_sent(self) -> None:
        """Measured on the DeepSeek adapter: an unset temperature is simply not
        in ``invocation_params``. Storing 0.0 there would be a fabrication, and
        0.0 is a meaningful temperature."""
        captured = capture_inference_params({"_type": "openai-chat", "model": "x"})

        assert captured.temperature is None
        assert captured.top_p is None
        assert captured.max_output_tokens is None

    def test_a_zero_is_kept_because_zero_is_a_VALUE(self) -> None:
        captured = capture_inference_params({"_type": "x", "temperature": 0.0})

        assert captured.temperature == 0.0

    @pytest.mark.parametrize("params", [None, {}])
    def test_no_parameters_at_all_never_raises(self, params: object) -> None:
        """This runs inside a LangChain callback: raising there would turn an
        observability concern into a broken turn."""
        captured = capture_inference_params(params)  # type: ignore[arg-type]

        assert captured.provider is None
        assert captured.params_digest is not None, "a digest of nothing is still a digest"


class TestNothingSecretIsEverKept:
    @pytest.mark.parametrize(
        "secret",
        [
            "api_key",
            "openai_api_key",
            "anthropic_api_key",
            "google_api_key",
            "authorization",
            "access_token",
            "client_secret",
            "password",
            "credentials",
        ],
    )
    def test_a_credential_is_refused_whatever_a_future_adapter_publishes(self, secret: str) -> None:
        captured = capture_inference_params({"_type": "x", secret: "sk-live-do-not-store"})

        assert "sk-live-do-not-store" not in captured.params_digest
        assert secret not in INFERENCE_PARAM_ALLOWLIST

    def test_the_allowlist_is_the_only_thing_that_can_be_kept(self) -> None:
        """An allowlist that grew a denylist beside it would be two rules."""
        captured = capture_inference_params(
            {"_type": "x", "temperature": 0.5, "some_new_field": "whatever"}
        )

        assert captured.temperature == 0.5
        assert "whatever" not in captured.params_digest


class TestTheDigestAnswersWhatTheColumnsCannot:
    def test_the_same_call_twice_digests_the_same(self) -> None:
        params = {"_type": "openai-chat", "model": "gpt-4.1-mini", "temperature": 0.3}

        assert (
            capture_inference_params(params).params_digest
            == capture_inference_params(dict(params)).params_digest
        )

    def test_a_parameter_with_no_column_of_its_own_still_moves_the_digest(self) -> None:
        """Otherwise « was anything else set? » would be unanswerable, and the
        readable columns would quietly stand for the whole configuration."""
        base = {"_type": "x", "temperature": 0.3}

        assert (
            capture_inference_params({**base, "frequency_penalty": 0.5}).params_digest
            != capture_inference_params(base).params_digest
        )

    def test_the_declaration_order_does_not_matter(self) -> None:
        first = capture_inference_params({"_type": "x", "temperature": 0.3, "top_p": 0.9})
        second = capture_inference_params({"top_p": 0.9, "_type": "x", "temperature": 0.3})

        assert first.params_digest == second.params_digest


class TestTheProviderIsReadFromWhatTheClientDECLARES:
    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            ("openai-chat", "openai"),
            ("anthropic-chat", "anthropic"),
            ("chat-google-generative-ai", "google"),
            ("fake-list-chat-model", "fake-list-chat-model"),
        ],
    )
    def test_the_family_is_named_the_way_LIA_names_it(self, declared: str, expected: str) -> None:
        """An unknown family is kept AS DECLARED rather than mapped to None: a
        register that silently forgets which client answered is worse than one
        carrying a name nobody has normalised yet."""
        assert capture_inference_params({"_type": declared}).provider == expected


class TestReasoningSpeaksADR245sVocabulary:
    def test_the_openai_spelling_is_translated_to_the_ladder(self) -> None:
        captured = capture_inference_params({"_type": "openai-chat", "reasoning_effort": "high"})

        assert captured.reasoning_level == "high"

    def test_the_google_spelling_is_translated_too(self) -> None:
        captured = capture_inference_params(
            {"_type": "chat-google-generative-ai", "thinking_level": "low", "thinking_budget": 2048}
        )

        assert captured.reasoning_level == "low"
        assert captured.reasoning_budget_tokens == 2048

    def test_the_anthropic_shape_yields_its_budget(self) -> None:
        captured = capture_inference_params(
            {
                "_type": "anthropic-chat",
                "thinking": {"type": "enabled", "budget_tokens": 4096},
            }
        )

        assert captured.reasoning_budget_tokens == 4096

    def test_a_model_that_was_not_asked_to_think_says_nothing(self) -> None:
        captured = capture_inference_params({"_type": "anthropic-chat", "thinking": None})

        assert captured.reasoning_level is None
        assert captured.reasoning_budget_tokens is None

    def test_an_unreadable_reasoning_shape_never_raises(self) -> None:
        """A provider changing its shape must degrade to « unknown », never to
        a failed turn."""
        captured = capture_inference_params({"_type": "anthropic-chat", "thinking": "surprise"})

        assert captured.reasoning_budget_tokens is None


class TestTheRecordIsAPlainValue:
    def test_it_carries_exactly_the_columns_the_log_stores(self) -> None:
        assert set(InferenceParams._fields) == {
            "provider",
            "temperature",
            "top_p",
            "max_output_tokens",
            "reasoning_level",
            "reasoning_budget_tokens",
            "params_digest",
        }
