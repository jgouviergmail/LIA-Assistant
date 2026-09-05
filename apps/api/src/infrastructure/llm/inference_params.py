"""What was actually SENT to a model, in one vocabulary (ADR-263, lot 7).

Article 12 asks for the parameters of the inference. LIA holds three different
answers to that, and only one of them is true:

1. ``llm_config_overrides`` — the CONFIGURATION. Mutable and unversioned:
   reading it tomorrow does not say what ran yesterday.
2. the ``LLMAgentConfig`` resolved in ``get_llm()`` — what LIA DECIDED. But
   ADR-245 coerces a reasoning level a model refuses, so the decided value is
   not always the sent one.
3. ``invocation_params``, which LangChain hands every callback — what was
   actually SENT.

This module reads the third. It needs no new plumbing: the tracking callback
already receives it beside the metadata it reads for ``llm_type`` (ADR-244).

Two rules, both established by probing the real adapters rather than the docs:

- **The output cap has three spellings** — ``max_completion_tokens`` (OpenAI),
  ``max_tokens`` (Anthropic), ``max_output_tokens`` (Google) — and reasoning
  has three shapes. Storing the provider's spelling would produce a register
  where one concept wears three names and compares with nothing.
- **An allowlist, never a dump.** No adapter leaks a credential in its
  invocation parameters today; nothing guarantees the next one will not, and a
  register is the last place a key should end up. The same rule the technical
  export already lives by.

Nothing here raises. It runs inside a LangChain callback, where an exception
would turn an observability concern into a broken turn.
"""

from __future__ import annotations

from typing import Any, Final, NamedTuple

from src.domains.agents.effects.chain_digest import row_digest

#: Every parameter worth keeping, and nothing else. A key absent from this set
#: never reaches a column, a digest or a log — which is what makes a future
#: adapter publishing ``api_key`` a non-event.
#:
#: ``_type`` is in: it is how the client names its own family, and losing it
#: would leave a row that cannot say which client answered.
INFERENCE_PARAM_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "_type",
        "model",
        "model_name",
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "max_completion_tokens",
        "max_output_tokens",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "streaming",
        "stream",
        "n",
        # The three reasoning shapes, kept so the digest covers them even when
        # the readable columns cannot express a provider's oddity.
        "reasoning_effort",
        "reasoning",
        "thinking",
        "thinking_level",
        "thinking_budget",
        "include_thoughts",
        "verbosity",
    }
)

#: The three spellings of one concept, in the order a reader would look.
_OUTPUT_CAP_KEYS: Final[tuple[str, ...]] = (
    "max_output_tokens",
    "max_completion_tokens",
    "max_tokens",
)

#: What a client calls itself -> what LIA calls it. An unknown family is kept
#: AS DECLARED rather than mapped to None: a register that silently forgets
#: which client answered is worse than one carrying an un-normalised name.
_FAMILY_NAMES: Final[dict[str, str]] = {
    "openai-chat": "openai",
    "azure-openai-chat": "openai",
    "anthropic-chat": "anthropic",
    "chat-google-generative-ai": "google",
    "chat-vertexai": "google",
    "ollama-chat": "ollama",
    "chat-ollama": "ollama",
}


class InferenceParams(NamedTuple):
    """The parameters of one call, normalised.

    Attributes:
        provider: The client family that answered.
        temperature: As sent; None when the call did not set one.
        top_p: As sent.
        max_output_tokens: The output cap, whatever the provider calls it.
        reasoning_level: ADR-245's ladder vocabulary, never a provider spelling.
        reasoning_budget_tokens: The thinking budget, when one was set.
        params_digest: Over EVERY allowlisted parameter, so « was anything else
            set? » stays answerable when the readable columns cannot say.
    """

    provider: str | None
    temperature: float | None
    top_p: float | None
    max_output_tokens: int | None
    reasoning_level: str | None
    reasoning_budget_tokens: int | None
    params_digest: str


def capture_inference_params(params: dict[str, Any] | None) -> InferenceParams:
    """Read one call's parameters into the register's vocabulary.

    Args:
        params: ``invocation_params`` as LangChain hands them to a callback,
            or None when a path does not provide them.

    Returns:
        The normalised record. Never raises.
    """
    kept = {key: value for key, value in (params or {}).items() if key in INFERENCE_PARAM_ALLOWLIST}
    level, budget = _reasoning(kept)
    return InferenceParams(
        provider=_provider(kept),
        temperature=_number(kept.get("temperature")),
        top_p=_number(kept.get("top_p")),
        max_output_tokens=_integer(_first_present(kept, _OUTPUT_CAP_KEYS)),
        reasoning_level=level,
        reasoning_budget_tokens=budget,
        params_digest=row_digest({key: _digestible(value) for key, value in kept.items()}),
    )


def _first_present(kept: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """The first of several spellings that carries a value.

    Args:
        kept: The allowlisted parameters.
        keys: The spellings, in reading order.

    Returns:
        The value, or None.
    """
    for key in keys:
        if kept.get(key) is not None:
            return kept[key]
    return None


def _provider(kept: dict[str, Any]) -> str | None:
    """Name the client family the way LIA names it.

    Args:
        kept: The allowlisted parameters.

    Returns:
        The family, or None when the client declared none.
    """
    declared = kept.get("_type")
    if not isinstance(declared, str) or not declared:
        return None
    return _FAMILY_NAMES.get(declared, declared)


def _reasoning(kept: dict[str, Any]) -> tuple[str | None, int | None]:
    """Read the reasoning ask in ADR-245's vocabulary, whatever the provider.

    Args:
        kept: The allowlisted parameters.

    Returns:
        ``(level, budget_tokens)``. A shape this does not recognise yields
        ``(None, None)`` rather than an exception: a provider changing its
        payload must degrade to « unknown », never to a failed turn.
    """
    level = kept.get("reasoning_effort") or kept.get("thinking_level")
    budget = _integer(kept.get("thinking_budget"))

    thinking = kept.get("thinking")
    if isinstance(thinking, dict):
        budget = budget if budget is not None else _integer(thinking.get("budget_tokens"))
        level = level or thinking.get("effort")

    reasoning = kept.get("reasoning")
    if isinstance(reasoning, dict):
        level = level or reasoning.get("effort")
        budget = budget if budget is not None else _integer(reasoning.get("max_tokens"))

    return (str(level) if isinstance(level, str) and level else None), budget


def _number(value: Any) -> float | None:
    """A float, or None — never a coerced zero.

    Args:
        value: The raw parameter.

    Returns:
        The value. ``0.0`` is kept: it is a meaningful temperature, and
        confusing it with « unset » would misreport a deterministic call.
    """
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _integer(value: Any) -> int | None:
    """An int, or None.

    Args:
        value: The raw parameter.

    Returns:
        The value.
    """
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _digestible(value: Any) -> Any:
    """Render a value the canonical encoding can take.

    The encoding deliberately refuses any type nobody pinned — a rule this
    module respects rather than relaxes, because the same encoding seals the
    tamper-evident chain and its vectors are frozen. So the rendering happens
    HERE, on the caller's side, and only for the two shapes the encoding has no
    opinion about:

    - a **float** becomes ``repr()``: the shortest text that round-trips to the
      same IEEE-754 double, so ``0.3`` digests identically on every machine;
    - a **nested payload** (a provider's reasoning block, a stop list) becomes a
      sorted, bracketed text. It must MOVE the digest — that is the whole point
      of digesting more than the readable columns — and refusing it would leave
      a parameter nobody can detect a change in.

    Args:
        value: The raw parameter.

    Returns:
        A scalar the canonical encoding accepts.
    """
    if isinstance(value, float):
        return repr(value)
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}={_digestible(value[k])}" for k in sorted(map(str, value))) + "}"
    if isinstance(value, list | tuple):
        return "[" + ",".join(str(_digestible(item)) for item in value) + "]"
    return repr(value)


__all__ = ["INFERENCE_PARAM_ALLOWLIST", "InferenceParams", "capture_inference_params"]
