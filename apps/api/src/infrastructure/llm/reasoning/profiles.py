"""The SHAPE of a model's reasoning, derived -- never stored.

Two things the first draft of this design conflated, and the validation harness
separated:

- the **family** is the shape of the translation. It must never be wrong, so it
  is derived from ``(provider, model prefix)`` through ordered rules. Measured
  over 87 chat models: **0 gaps**.
- the **ladder** is the set of accepted levels. It is genuinely per-model --
  OpenAI documents that supported values are model-dependent, ``o1`` accepts
  ``low/medium/high`` but not ``minimal``, ``gpt-5.6`` adds ``max`` -- so the
  catalogue may supply one, and it may only **narrow** the family's. Deriving
  it from the family instead produced **29 divergences**.

The consequence is the point: the catalogue becomes an optimisation rather than
a prerequisite. An unknown model resolves to its family's ladder and coercion
handles the rest, instead of raising ``RuntimeError`` at instantiation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

FAMILIES: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic_adaptive",
        "anthropic_budget",
        "gemini_level",
        "gemini_budget",
        "deepseek_toggle",
        "qwen_toggle_budget",
        "perplexity",
        "none",
    }
)


@dataclass(frozen=True)
class ReasoningProfile:
    """What a model can express about reasoning.

    Attributes:
        family: Which translator branch applies.
        levels: The accepted ladder, in ascending order.
        supports_budget: Whether an explicit token budget is expressible.
        budget_range: ``(min, max)`` when it is, else ``None``.
        can_disable: Whether reasoning can be turned off at all. Neither
            OpenRouter nor Vercel models this; LIA needs it because
            ``gemini-3.5-flash`` is ``reasoning.mandatory=true``, and a policy
            that believed it had a cheap mode would be wrong about cost.
        default_enabled: What the provider does absent any instruction, when
            that is known.
        source: ``family`` when the ladder is the family's, ``model_refined``
            when the catalogue narrowed it.
    """

    family: str
    levels: tuple[str, ...]
    supports_budget: bool
    budget_range: tuple[int, int] | None
    can_disable: bool
    default_enabled: bool | None
    source: str = "family"


#: A rule matched and says this model does not reason. Positive knowledge.
_NO_REASONING = ReasoningProfile("none", (), False, None, True, False)

#: No rule matched at all. The family is unknown, which is NOT the same claim --
#: a dynamically discovered Ollama tag reasons or not, and these rules simply do
#: not know. Both produce no kwarg at translation time, so the runtime behaves
#: identically; the difference matters to the *validator*, which may reject an
#: operator's level on the first and must never reject it on the second.
_UNKNOWN_FAMILY = ReasoningProfile("none", (), False, None, True, None, source="unknown")

#: ORDERED rules. A negative entry (``family="none"``) placed before a broad one
#: wins -- that ordering is what keeps ``gpt-4.1`` and ``gpt-5-chat-latest`` out
#: of the OpenAI reasoning family.
_RULES: list[tuple[str, tuple[str, ...], ReasoningProfile]] = [
    (
        "openai",
        (
            "o1-mini",
            "gpt-5-chat-latest",
            "gpt-5.1-chat-latest",
            # gpt-5.2-chat-latest is DELIBERATELY absent: unlike its 5.1 and 5.3
            # siblings the catalogue declares it reasoning, with a single-level
            # ladder ["medium"]. The coverage guard caught the mistake of
            # grouping the aliases by name rather than by what they declare.
            "gpt-5.3-chat-latest",
            "gpt-5-search-api",
            "gpt-4o",
            "gpt-4.1",
            "computer-use-preview",
            "text-embedding",
            "tts-",
        ),
        _NO_REASONING,
    ),
    ("qwen", ("qwen2.5",), _NO_REASONING),
    (
        "gemini",
        (
            "gemini-3.1-flash-preview-tts",
            "gemini-2.0",
            "gemini-1.5",
            "embedding-",
            "text-embedding",
        ),
        _NO_REASONING,
    ),
    ("anthropic", ("claude-3-5",), _NO_REASONING),
    (
        "anthropic",
        ("claude-opus-4-6", "claude-sonnet-4-6"),
        ReasoningProfile(
            "anthropic_adaptive",
            ("none", "low", "medium", "high", "max"),
            False,
            None,
            True,
            True,
        ),
    ),
    (
        "anthropic",
        ("claude-opus-4-5", "claude-haiku-4-5", "claude-opus-4", "claude-sonnet-4"),
        ReasoningProfile(
            "anthropic_budget",
            ("none", "minimal", "low", "medium", "high", "xhigh"),
            True,
            (1024, 128000),
            True,
            True,
        ),
    ),
    (
        "openai",
        ("gpt-5.6",),
        ReasoningProfile(
            "openai", ("none", "low", "medium", "high", "xhigh", "max"), False, None, True, None
        ),
    ),
    (
        "openai",
        ("gpt-5", "o1", "o3", "o4"),
        ReasoningProfile(
            "openai",
            ("none", "minimal", "low", "medium", "high", "xhigh"),
            False,
            None,
            True,
            None,
        ),
    ),
    (
        "deepseek",
        ("deepseek-v4",),
        ReasoningProfile("deepseek_toggle", ("none", "high", "max"), False, None, True, True),
    ),
    (
        "gemini",
        ("gemini-3",),
        ReasoningProfile(
            "gemini_level", ("minimal", "low", "medium", "high"), False, None, False, True
        ),
    ),
    (
        "gemini",
        ("gemini-2.5",),
        ReasoningProfile(
            "gemini_budget",
            ("none", "minimal", "low", "medium", "high"),
            True,
            (0, 24576),
            True,
            True,
        ),
    ),
    (
        "qwen",
        ("qwen",),
        ReasoningProfile(
            "qwen_toggle_budget",
            ("none", "minimal", "low", "medium", "high"),
            True,
            (0, 32768),
            True,
            False,
        ),
    ),
    (
        "perplexity",
        ("sonar-deep-research", "sonar-reasoning"),
        # can_disable=False: the sonar reasoning tier has no off switch -- a
        # caller who wants no reasoning uses ``sonar`` instead. Declaring it
        # True while offering no ``none`` on the ladder made the profile
        # self-contradictory, and an explicit ``none`` produced
        # ``reasoning_effort: "none"``, a value the API does not accept.
        ReasoningProfile("perplexity", ("low", "medium", "high"), False, None, False, True),
    ),
]


def resolve_reasoning_profile(
    provider: str,
    model: str,
    *,
    model_levels: tuple[str, ...] | None = None,
) -> ReasoningProfile:
    """Derive the family, then apply the catalogue's optional narrowing.

    Args:
        provider: LIA provider id.
        model: LIA model name.
        model_levels: The ladder the catalogue declares, when it declares one.
            It may only narrow: a level the family cannot translate is dropped,
            and a narrowing that intersects to nothing is ignored entirely
            rather than disarming the model.

            There is deliberately NO per-model override of ``can_disable``: the
            catalogue narrows DEPTHS, and whether a model can stop reasoning is
            a property of the provider's API that a curated row must not be
            able to contradict (``gemini-3.5-flash`` is mandatory-reasoning).

    Returns:
        The profile. Never raises. A model no rule matches resolves to
        ``family="none"`` with ``source="unknown"`` -- it produces no reasoning
        kwarg, exactly like a model a negative rule matched, but it carries no
        claim that the model cannot reason.
    """
    base = _UNKNOWN_FAMILY
    for rule_provider, prefixes, profile in _RULES:
        if rule_provider == provider and model.startswith(prefixes):
            base = profile
            break
    if base.family == "none":
        return base

    if not model_levels:
        return base
    declared = set(model_levels)
    narrowed = tuple(level for level in base.levels if level in declared)
    if not narrowed:
        return base
    return replace(base, levels=narrowed, source="model_refined")
