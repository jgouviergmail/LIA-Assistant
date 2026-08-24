"""Current-core provider contract for the self-host installer (B10/B10-bis).

Owner arbitration (2026-08-06): the reference ``llm_config_seed.sql`` is the
proven production configuration and is applied VERBATIM — so the provider
baseline is derived from the POST-SEED effective configuration (seed
override when its provider is non-NULL, else the code default), never from
code defaults alone. The anti-drift test recomputes the derivation from the
live constants plus the parsed seed file: moving one core slot to a new
provider turns CI red until the questionnaire contract is updated.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from src.domains.llm_config.constants import LLM_DEFAULTS

#: The pipeline-core LLM slots a fresh install must be able to serve
#: (chat pipeline + the user-toggleable ReAct entry).
CURRENT_CORE_LLM_TYPES: tuple[str, ...] = (
    "planner",
    "query_analyzer",
    "query_agent",
    "semantic_validator",
    "response",
    "hitl_classifier",
    "react_agent",
)

#: Audited derivation result — the questionnaire collects one key for each.
#: Machine-derived 2026-08-06: the seed overrides EVERY qwen code default
#: (planner/query_analyzer/query_agent/response/semantic_validator/
#: react_agent → deepseek), and the 16 slots absent from the seed all
#: default to openai — so no effective slot resolves qwen at all. Qwen
#: stays an optional Admin-UI provider (its models remain in the pricing
#: seed), never a required install key.
CURRENT_CORE_PROVIDER_IDS: tuple[str, ...] = ("deepseek", "openai")

#: Seeded capabilities that stay degraded without their (optional) key.
OPTIONAL_SEEDED_CAPABILITIES: dict[str, str] = {
    "vision_analysis": "gemini",
    "voice_tts": "elevenlabs",
    "mcp_app_react_agent": "anthropic",
}


def _find_seed_file() -> Path:
    """Locate the reference seed in both layouts (host repo and container).

    Host: <repo>/apps/api/src/... with seeds at <repo>/infrastructure/...
    Container: /app/src/... with seeds bind-mounted at /app/infrastructure/...
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "infrastructure" / "database" / "seeds" / "llm_config_seed.sql"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "llm_config_seed.sql not found in any parent tree — the provider "
        "baseline cannot be derived without the reference seed"
    )


_OVERRIDE_ROW = re.compile(
    r"\(gen_random_uuid\(\),\s*'(?P<llm_type>[^']+)',\s*" r"(?:'(?P<provider>[^']+)'|NULL)\s*,"
)


@lru_cache(maxsize=1)
def seeded_provider_overrides() -> dict[str, str | None]:
    """Parse the reference seed: llm_type → seeded provider (None = NULL)."""
    body = _find_seed_file().read_text(encoding="utf-8")
    return {
        match.group("llm_type"): match.group("provider") for match in _OVERRIDE_ROW.finditer(body)
    }


def effective_core_provider(llm_type: str) -> str:
    """Resolve one core slot on the post-seed effective configuration.

    Args:
        llm_type: A ``CURRENT_CORE_LLM_TYPES`` member.

    Returns:
        The provider id that slot resolves to after seeding.
    """
    seeded = seeded_provider_overrides().get(llm_type)
    if seeded is not None:
        return seeded
    return LLM_DEFAULTS[llm_type].provider


def required_current_core_provider_ids() -> tuple[str, ...]:
    """Derive the required provider set from the effective configuration."""
    return tuple(sorted({effective_core_provider(t) for t in CURRENT_CORE_LLM_TYPES}))
