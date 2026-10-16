"""Guard: every hand-maintained list of LLM providers names the same providers.

A provider id lives in seven hand-maintained lists: five in the API, which fail in
five different ways when one is forgotten — the database enum refuses the
catalogue row, ``LLM_PROVIDERS`` hides the key from the admin screen, the two
request ``Literal``\\ s answer 422, and ``LLMAgentConfig`` turns EVERY merge of a
configured slot into a 500 at read time (``merge_config`` validates the stored
provider) — and two in the web app. Adding a provider was a scavenger hunt; this
test makes it a checklist that fails until it is complete. (The speech-only lists
keyed by TTS family are pinned beside their families, in the voice tests.)

The frontend files are parsed rather than imported: the backend suite runs from a
full checkout (CI checks the whole repository out), the same reading
``test_frontend_contract_guard.py`` does.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, get_args

import pytest

from src.core.llm_agent_config import LLMAgentConfig
from src.domains.llm.models import LLMProviderEnum
from src.domains.llm.schemas import ProviderLiteral
from src.domains.llm_config.constants import LLM_PROVIDERS
from src.domains.llm_config.schemas import LLMTypeConfigUpdate
from src.infrastructure.provisioning.demo_llm import _SPEECH_PROVIDERS

pytestmark = pytest.mark.unit

_WEB_SRC = Path(__file__).resolve().parents[3] / "web" / "src"
_SETTINGS_ACTIONS = _WEB_SRC / "lib" / "actions" / "settings-actions.ts"
_PRICING_SECTION = _WEB_SRC / "components" / "settings" / "AdminLLMPricingSection.tsx"


def _literal_values(annotation: Any) -> set[str]:
    """The string members of a ``Literal`` — or of the ``Literal`` inside ``X | None``."""
    values: set[str] = set()
    for member in get_args(annotation):
        if isinstance(member, str):
            values.add(member)
        else:
            values |= _literal_values(member)
    return values


def _ts_union(text: str, type_name: str) -> set[str]:
    match = re.search(rf"export type {type_name} =([^;]+);", text)
    assert match is not None, f"{type_name} not found"
    return set(re.findall(r"'([a-z0-9_]+)'", match.group(1)))


def _ts_array(text: str, const_name: str) -> set[str]:
    match = re.search(rf"const {const_name}[^=]*=\s*\[([^\]]+)\]", text)
    assert match is not None, f"{const_name} not found"
    return set(re.findall(r"'([a-z0-9_]+)'", match.group(1)))


BACKEND = {member.value for member in LLMProviderEnum}


@pytest.mark.parametrize(
    ("where", "declared"),
    [
        ("LLM_PROVIDERS", set(LLM_PROVIDERS)),
        ("ProviderLiteral", set(get_args(ProviderLiteral))),
        (
            "LLMTypeConfigUpdate.provider",
            _literal_values(LLMTypeConfigUpdate.model_fields["provider"].annotation),
        ),
        (
            "LLMAgentConfig.provider",
            _literal_values(LLMAgentConfig.model_fields["provider"].annotation),
        ),
        (
            "web LLMProviderName",
            _ts_union(_SETTINGS_ACTIONS.read_text(encoding="utf-8"), "LLMProviderName"),
        ),
        (
            "web PROVIDER_OPTIONS",
            _ts_array(_PRICING_SECTION.read_text(encoding="utf-8"), "PROVIDER_OPTIONS"),
        ),
    ],
)
def test_every_list_names_the_database_enum_exactly(where: str, declared: set[str]) -> None:
    assert declared == BACKEND, (
        f"{where} drifted from LLMProviderEnum: missing {sorted(BACKEND - declared)}, "
        f"unknown {sorted(declared - BACKEND)}"
    )


def test_the_speech_only_providers_are_known_providers() -> None:
    assert _SPEECH_PROVIDERS <= BACKEND
