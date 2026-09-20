"""The SHAPE of a model's reasoning, derived -- never stored.

Lives in ``core`` because ``core.llm_config_helper`` reads it: as an
``infrastructure`` module it closed a cycle (``infrastructure.llm.__init__``
imports the evaluation pipeline, which imports the helper back) and a fresh
interpreter importing the helper first died on a partially initialised module.
The rules are pure — dataclasses and prefixes, no configuration — so ``core``
is their natural home; ``infrastructure.llm.reasoning.profiles`` re-exports
them for its readers.

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
        "gemini_live_level",
        "deepseek_toggle",
        "qwen_toggle_budget",
        "perplexity",
        "ollama",
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
        ladder_from_catalogue: The family's own ladder is only a VOCABULARY;
            whether a given model reasons at all is known to the catalogue
            alone (for Ollama, to the model's own server, read at discovery).
            Without a declared ladder such a model resolves to the unknown
            family -- no kwarg, no claim -- instead of inheriting depths the
            rule table cannot vouch for.
    """

    family: str
    levels: tuple[str, ...]
    supports_budget: bool
    budget_range: tuple[int, int] | None
    can_disable: bool
    default_enabled: bool | None
    source: str = "family"
    ladder_from_catalogue: bool = False


#: A rule matched and says this model does not reason. Positive knowledge.
_NO_REASONING = ReasoningProfile("none", (), False, None, True, False)

#: No rule matched at all. The family is unknown, which is NOT the same claim --
#: a dynamically discovered Ollama tag reasons or not, and these rules simply do
#: not know. Both produce no kwarg at translation time, so the runtime behaves
#: identically; the difference matters to the *validator*, which may reject an
#: operator's level on the first and must never reject it on the second.
_UNKNOWN_FAMILY = ReasoningProfile("none", (), False, None, True, None, source="unknown")

#: Ollama (ADR-267). The server's ``think`` field accepts a boolean or a level
#: (``low``/``medium``/``high``/``max``); ``false`` is accepted by every model
#: while a positive level is refused (400) by a model without the ``thinking``
#: capability. A tag's name says nothing about that capability -- the server
#: does, at discovery -- so the ladder is DECLARED per model (full for a
#: thinking model, ``("none",)`` for the others) and an undeclared tag stays
#: unknown. ``can_disable`` is True: ``think=false`` is accepted everywhere
#: (gpt-oss ignores it rather than refusing it).
_OLLAMA_PROFILE = ReasoningProfile(
    "ollama",
    ("none", "low", "medium", "high", "max"),
    False,
    None,
    True,
    None,
    ladder_from_catalogue=True,
)

#: DeepSeek's thinking-toggle family, declared ONCE. The vendor renamed its
#: flagship: the API model is ``deepseek-flash`` (DeepSeek-V4.1-Flash) and the
#: ``deepseek-v4-*`` names are retired aliases it still accepts; the V3 names
#: (``deepseek-chat``, ``deepseek-reasoner``) are NOT in the family. The adapter
#: and the structured-output detour read this through
#: :func:`is_deepseek_thinking_model` -- each kept a private
#: ``startswith("deepseek-v4-")`` until 2026-09-12, so a row created for
#: ``deepseek-flash`` fell through all three at once: no ladder offered, no
#: off switch sent, the V3 output cap applied, and a 150-token call came back
#: as 150 tokens of reasoning and no answer.
DEEPSEEK_THINKING_PREFIXES: tuple[str, ...] = ("deepseek-flash", "deepseek-v4")

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
    # The live extended-thinking model (ADR-299): a ladder of three, no
    # ``minimal``, and NO off switch — reasoning is what the model is. The plain
    # live model matches no rule and resolves unknown: it reasons on its own
    # terms and nothing about it is configurable. Rendered into a Live API
    # ``setup`` by ``domains/live/providers/gemini.py``, never into a kwarg.
    (
        "gemini_live",
        ("gemini-3.8-live-extended-thinking",),
        ReasoningProfile("gemini_live_level", ("low", "medium", "high"), False, None, False, True),
    ),
    (
        "gemini",
        (
            "gemini-3.1-flash-tts-preview",
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
        DEEPSEEK_THINKING_PREFIXES,
        # ``low/high/max`` per api-docs.deepseek.com/guides/thinking_mode; the
        # API also answers 200 to ``medium`` and ``minimal`` (probed 2026-09-12)
        # but its silence is not a declaration, so the ladder stays the
        # documented one.
        ReasoningProfile(
            "deepseek_toggle", ("none", "low", "high", "max"), False, None, True, True
        ),
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
    # Every Ollama tag: the empty prefix matches any name. The ladder comes
    # from the server (see ``_OLLAMA_PROFILE``), never from the name.
    ("ollama", ("",), _OLLAMA_PROFILE),
]


def is_deepseek_thinking_model(model: str) -> bool:
    """Whether ``model`` belongs to DeepSeek's thinking-toggle family.

    The ONE predicate the adapter's V4 branch and the structured-output
    ``tool_choice`` detour consult; it reads the same prefixes as the rule
    table, so the family cannot be recognised in one place and missed in
    another.

    Args:
        model: The DeepSeek model name as configured.

    Returns:
        True for the current name and the retired ``deepseek-v4-*`` aliases,
        False for the V3 names and anything unknown.
    """
    return model.startswith(DEEPSEEK_THINKING_PREFIXES)


def ollama_declared_ladder(thinking: bool) -> tuple[str, ...]:
    """The ladder the discovery declares for an Ollama tag.

    Args:
        thinking: Whether the server lists the ``thinking`` capability.

    Returns:
        The full Ollama ladder for a thinking model; ``("none",)`` otherwise,
        which keeps the tag KNOWN (so the write path can refuse a depth it has
        no way to honour) while letting ``none`` reach the server, where
        ``think=false`` is accepted by every model.
    """
    return _OLLAMA_PROFILE.levels if thinking else ("none",)


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
        # A family whose ladder only the catalogue can vouch for resolves to
        # UNKNOWN without a declaration: the validator must not reject, the
        # translator must not send, the UI must not offer.
        return _UNKNOWN_FAMILY if base.ladder_from_catalogue else base
    declared = set(model_levels)
    narrowed = tuple(level for level in base.levels if level in declared)
    if not narrowed:
        return base
    return replace(base, levels=narrowed, source="model_refined")
