"""The largest output budget a model accepts — one answer, for every provider.

A slot's ``max_tokens`` is a figure an administrator chose for a MODEL, and it
outlives the model: production 2026-10-18, three slots kept the 200 000 chosen
for the model they ran on before, after a switch to a model whose catalogue row
vouches for a 128 000 output cap. The provider refused every call. The
catalogue knew the cap; only two provider branches of the adapter capped
anything, each its own way, and every other client sent the raw value.

ONE rule says whose cap is known, and three readers ask it:

- the slot resolution (``get_llm_config_for_agent``), so every reader of a
  slot's budget — the factory, the document prompt's length budget, a meeting
  transcript's part size — works with the capped budget;
- the client door (``ProviderAdapter.create_llm``), for a caller that passes a
  budget of its own;
- the admin metadata (``/llm-config/metadata``), so the screen warns about the
  very figure the request is held to (ADR-184).

A cap is known where a curated catalogue row VOUCHES for it — ``imported`` or
``verified``, the provenances ``max_output_tokens`` is corrected under
(``sync_diff.CORRECTABLE_FIELDS``, ADR-244) — on a model that chats, served by
a provider that enforces one. A ``declared`` row carries column defaults, the
discovered Ollama layer publishes a constant, and a self-hosted runtime
generates until its context is full. The column default itself needs evidence
of its own: provenance is row-level while its evidence is field-level, the sync
promotes a row on ONE corroborated field and the catalogue editor stamps
``verified`` on any save, so the default survives under both — it is a cap
only where the vendored registries state that very figure for the model, as
they do for older models that really stop there. Doubt adds no cap here.
Behind this rule two provider branches keep ceilings of their own for what the
catalogue does not vouch for (``deepseek_limits`` for the DeepSeek families, a
name heuristic on the legacy OpenAI Chat Completions path); they only ever
lower further.
"""

from __future__ import annotations

from functools import lru_cache

from src.core.constants import (
    CAPABILITY_PROVENANCE_IMPORTED,
    CAPABILITY_PROVENANCE_VERIFIED,
    LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS,
    PROVIDERS_WITHOUT_OUTPUT_CAP,
)
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_utils import normalize_model_name
from src.domains.llm.models import LLMModelKindEnum
from src.infrastructure.llm.catalogue.field_mapping import registry_facts
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: The provenances whose row is evidence for ``max_output_tokens``.
_VOUCHING_PROVENANCES: frozenset[str] = frozenset(
    {CAPABILITY_PROVENANCE_IMPORTED, CAPABILITY_PROVENANCE_VERIFIED}
)

#: ``(llm_type, provider, model, requested)`` already reported by this process:
#: the resolution runs on every LLM instantiation, the line once per pair.
_REPORTED: set[tuple[str, str, str, int]] = set()


@lru_cache(maxsize=256)
def registry_states_output_cap(provider: str, model: str, cap: int) -> bool:
    """Whether the vendored registries state ``cap`` as this model's output cap.

    The snapshot is vendored and static for the life of the process, so the
    answer is computed once per model (ADR-244: never the network on an
    execution path).

    Args:
        provider: The provider the model is served by.
        model: The catalogue model name.
        cap: The figure to look for.

    Returns:
        True when the merged registry facts carry exactly ``cap``.
    """
    facts = registry_facts(provider, model, kind=LLMModelKindEnum.chat.value)
    return facts is not None and facts.max_output_tokens == cap


def is_unproven_default(provider: str, model: str, cap: int) -> bool:
    """The column default with no registry stating it: a placeholder, not a cap.

    Args:
        provider: The provider the model is served by.
        model: The catalogue model name.
        cap: The row's ``max_output_tokens``.

    Returns:
        True when ``cap`` must not be read as the model's output cap.
    """
    return cap == LLM_MODEL_DEFAULT_MAX_OUTPUT_TOKENS and not registry_states_output_cap(
        provider, model, cap
    )


def vouched_output_cap(provider: str, profile: ModelProfile | None) -> int | None:
    """The output cap a curated catalogue row vouches for, or None.

    Args:
        provider: The provider the model is served by.
        profile: The model's catalogue profile, or None when it has none.

    Returns:
        The largest ``max_tokens`` the model accepts, or None when nobody
        vouched for one (this rule then adds no cap).
    """
    if profile is None or provider in PROVIDERS_WITHOUT_OUTPUT_CAP:
        return None
    # Read defensively, as the reasoning seam reads the same entry
    # (``reasoning/translate.kwargs_for``): this runs on every LLM
    # instantiation, and an entry shaped otherwise -- a stand-in, a future
    # rename -- must mean "no known cap", never an error inside the factory.
    if getattr(profile, "kind", None) != LLMModelKindEnum.chat.value:
        return None
    if getattr(profile, "capability_provenance", None) not in _VOUCHING_PROVENANCES:
        return None
    cap = getattr(profile, "max_output_tokens", None)
    if not isinstance(cap, int) or cap <= 0:
        return None
    if is_unproven_default(provider, str(getattr(profile, "model_id", "")), cap):
        return None
    return cap


def output_cap_for(provider: str, model: str) -> int | None:
    """The vouched output cap of a model, looked up by name.

    A date-suffixed id is retried under its base name, as the context window
    is (``get_effective_context_window``).

    Args:
        provider: The provider the model is served by.
        model: The model name as configured.

    Returns:
        The cap, or None when no curated row vouches for one.
    """
    profile = ModelCapabilitiesCache.get(model)
    if profile is None:
        normalized = normalize_model_name(model)
        if normalized != model:
            profile = ModelCapabilitiesCache.get(normalized)
    return vouched_output_cap(provider, profile)


def cap_max_tokens(provider: str, model: str, requested: int, *, llm_type: str) -> int:
    """``requested``, or the model's vouched cap when the request exceeds it.

    Reported once per slot, model and value per process: the stored figure is
    the administrator's to correct, and the admin screen flags it too.

    Args:
        provider: The provider the model is served by.
        model: The model name as configured.
        requested: The budget the slot or the caller asked for.
        llm_type: The slot, for the report.

    Returns:
        The budget the provider accepts.
    """
    cap = output_cap_for(provider, model)
    if cap is None or requested <= cap:
        return requested
    key = (llm_type, provider, model, requested)
    if key not in _REPORTED:
        _REPORTED.add(key)
        logger.warning(
            "llm_max_tokens_above_model_cap",
            llm_type=llm_type,
            provider=provider,
            model=model,
            requested=requested,
            cap=cap,
        )
    return cap


def capped_config(config: LLMAgentConfig, *, llm_type: str) -> LLMAgentConfig:
    """The slot's configuration with the output budget its model accepts.

    Args:
        config: The resolved configuration (defaults merged with the override).
        llm_type: The slot it belongs to.

    Returns:
        ``config`` itself when its budget fits, else a copy carrying the cap —
        never a mutation, since ``config`` may be the code default.
    """
    capped = cap_max_tokens(config.provider, config.model, config.max_tokens, llm_type=llm_type)
    if capped == config.max_tokens:
        return config
    return config.model_copy(update={"max_tokens": capped})
