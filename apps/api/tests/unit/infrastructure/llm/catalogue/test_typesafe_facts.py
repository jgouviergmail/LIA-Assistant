"""Native vendor evidence curates capabilities without inventing a chat budget."""

import pytest

from src.infrastructure.llm.catalogue.field_mapping import registry_facts

pytestmark = pytest.mark.unit


def test_pinned_native_model_has_field_level_vendor_evidence() -> None:
    facts = registry_facts("typesafe", "jev-1.13.0", kind="decision")
    assert facts is not None
    assert facts.max_input_tokens == 32_000
    assert facts.max_output_tokens is None
    assert facts.supports_tools is False
    assert facts.supports_structured_output is False
    assert facts.supports_vision is False
    assert set(facts.sources.values()) == {"vendor:typesafe"}


@pytest.mark.parametrize(
    "provider,model",
    [("openai", "jev-1.13.0"), ("typesafe", "jev-latest"), ("typesafe", "jev-2.0")],
)
def test_native_evidence_never_transfers_to_another_provider_or_version(
    provider: str, model: str
) -> None:
    assert registry_facts(provider, model) is None
