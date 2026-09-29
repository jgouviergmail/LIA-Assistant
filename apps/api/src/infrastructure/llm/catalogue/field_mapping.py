"""Merge offline capability evidence, with a declared precedence.

Only fields LIA may safely import appear here. Four families are excluded by
measurement, not by caution (see the design spec):

- **prices** — 85 of 87 models were price-stable over two months and the only
  two "changes" were tier-tracking artefacts; the registries also publish one
  tier among six and follow promotions, and neither can express ADR-223 time
  slots;
- **reasoning metadata** — a naive import invalidates ``effort: off`` on 21
  slots and silently switches the pipeline to thinking mode;
- **streaming and the sampling flags** — a false would break SSE on
  ``response``, and no registry covers them reliably;
- **kind** — LiteLLM's ``mode`` names the API surface while LIA's ``kind``
  classifies the product for UI filtering. Over the 103 matched rows,
  ``mode=chat`` maps to ``kind=audio`` six times and to ``kind=tts`` once. The
  divergence is legitimate, so no correct consumer exists.

A fifth candidate was tested and refuted: LiteLLM's ``max_tokens`` looked
like a third source for the output cap, but over the 512 entries it duplicates
``max_output_tokens`` (361) or ``max_input_tokens`` (the 22 where it is the
only one present) and never carries an output cap nothing else does. It is not
vendored.

Every fact records its source. A pinned native model absent from both public
registries may use explicitly dated vendor evidence declared below; no network
is consulted by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from src.infrastructure.llm.catalogue.registry_match import match_litellm, match_modelsdev
from src.infrastructure.llm.catalogue.vendor_announcements import announced_shutdown
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RegistryFacts:
    """Capability facts a registry may contribute for one model.

    Attributes:
        max_input_tokens: Input budget in tokens, or ``None`` when unknown.
        max_output_tokens: Output cap in tokens, or ``None`` when unknown.
        supports_tools: Whether the model accepts tool calls.
        supports_structured_output: Whether it accepts a response schema.
        supports_vision: Whether it accepts image attachments.
        deprecation_date: Provider retirement date — the one the vendor's own
            page announces (``vendor_announcements``), else LiteLLM's copy.
        registry_status: models.dev status verbatim (``deprecated`` /
            ``beta`` / ``None``). A second, independent retirement signal: it
            covers the preview models providers retire without a date. Dropped
            when the vendor lists the model with no shutdown announced.
        matched_registries: Which registries knew this model at all. It is
            what separates "models.dev lists it and says nothing" from
            "models.dev does not list it", a distinction :func:`is_retired`
            depends on.
        sources: Field name -> the registry that supplied it.
    """

    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_structured_output: bool | None = None
    supports_vision: bool | None = None
    deprecation_date: date | None = None
    registry_status: str | None = None
    matched_registries: frozenset[str] = frozenset()
    sources: dict[str, str] = field(default_factory=dict)


# Vendor-curated evidence for a native primitive absent from the two public
# catalogues. Checked 2026-09-28: https://docs.typesafe.ai/models and /api.
# Choice has a 32k state + single-question bound (conservatively 32,000 here).
# It accepts neither chat tools, response schemas nor vision. There is no
# generative output cap to import; prices, kind and sampling remain curated
# on the database row exactly like every other provider (ADR-244).
_VENDOR_CAPABILITIES: dict[tuple[str, str], RegistryFacts] = {
    ("typesafe", "jev-1.13.0"): RegistryFacts(
        max_input_tokens=32_000,
        supports_tools=False,
        supports_structured_output=False,
        supports_vision=False,
        matched_registries=frozenset({"vendor"}),
        sources=dict.fromkeys(
            ("max_input_tokens", "supports_tools", "supports_structured_output", "supports_vision"),
            "vendor:typesafe",
        ),
    ),
}


#: Kinds for which no registry publishes a token output cap.
#: models.dev fills ``limit.output`` with the EMBEDDING DIMENSION instead:
#: 3072 for ``text-embedding-3-large``, 1536 for ``-small`` and for
#: ``ada-002``, 1 for ``gemini-embedding-001``. Importing it would write a
#: vector width into a token column. LiteLLM publishes nothing there. The
#: caller supplies the kind because only LIA knows what its own row is — the
#: registries' ``mode`` answers a different question (see the module
#: docstring).
_NO_OUTPUT_CAP_KINDS = frozenset({"embedding"})


def _positive_int(value: Any) -> int | None:
    """Return ``value`` when it is a usable token count, else ``None``.

    Registries publish ``0`` to mean "not applicable": models.dev exposes
    ``limit: {input: 0, output: 0}`` on every image model and LiteLLM does the
    same on the moderation family (10 entries measured 2026-08-24). Importing
    a zero would collapse every downstream budget computation, so a
    non-positive count is absence, not a value.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _first(
    candidates: list[tuple[str, Any]],
    sources: dict[str, str],
    name: str,
) -> Any:
    """Return the first non-``None`` candidate and record where it came from."""
    for source, value in candidates:
        if value is not None:
            sources[name] = source
            return value
    return None


#: Boolean capability facts, as ``(fact, models.dev key, LiteLLM key)``.
#: models.dev first everywhere: it is curated per provider, while LiteLLM is
#: bulk-maintained over 3 000+ entries.
_BOOLEAN_FACTS: tuple[tuple[str, str, str], ...] = (
    ("supports_tools", "tool_call", "supports_function_calling"),
    ("supports_structured_output", "structured_output", "supports_response_schema"),
    ("supports_vision", "attachment", "supports_vision"),
)


def _record(sources: dict[str, str], name: str, resolved: tuple[str | None, Any]) -> Any:
    """Unpack a ``(source, value)`` resolution and remember where it came from."""
    source, value = resolved
    if value is not None and source is not None:
        sources[name] = source
    return value


def _boolean_facts(
    ll: dict[str, Any] | None,
    md: dict[str, Any] | None,
    sources: dict[str, str],
) -> dict[str, bool]:
    """Resolve every boolean capability through the declared table."""
    resolved: dict[str, bool] = {}
    for name, md_key, ll_key in _BOOLEAN_FACTS:
        value = _first(
            [("modelsdev", (md or {}).get(md_key)), ("litellm", (ll or {}).get(ll_key))],
            sources,
            name,
        )
        if value is not None:
            resolved[name] = bool(value)
    return resolved


def _max_input(
    ll: dict[str, Any] | None, md: dict[str, Any] | None
) -> tuple[str | None, int | None]:
    """models.dev's explicit ``input`` first, because LiteLLM conflates.

    LiteLLM's ``max_input_tokens`` is documented as the input budget but is
    populated with the TOTAL window on some entries. Measured 2026-08-24 over
    the 19 models where both registries state an input budget: 13 agree and
    **all six** disagreements are exactly ``litellm.max_input_tokens ==
    modelsdev.limit.context`` -- ``gpt-5-pro`` (400 000 against a real
    272 000), ``gpt-5.4``, ``gpt-5.4-pro``, ``gpt-5.5``, ``gpt-5.5-pro``
    (1 050 000 against 922 000) and ``gpt-realtime-2.1`` (128 000 against
    96 000). Zero disagreements have any other shape.

    models.dev states ``input`` on a minority of entries, so LiteLLM remains
    the source for everything else, and ``context - output`` is the last
    resort: most models.dev entries publish only ``context``, and using it as
    the input budget over-estimates by the whole output cap.
    """
    limit = (md or {}).get("limit") or {}
    declared = _positive_int(limit.get("input"))
    if declared is not None:
        return "modelsdev", declared
    direct = _positive_int((ll or {}).get("max_input_tokens"))
    if direct is not None:
        return "litellm", direct
    context = _positive_int(limit.get("context"))
    output = _positive_int(limit.get("output"))
    if context is not None and output is not None and context > output:
        return "modelsdev", context - output
    return None, None


def _max_output(
    ll: dict[str, Any] | None, md: dict[str, Any] | None
) -> tuple[str | None, int | None]:
    """models.dev first, unless it claims the output cap IS the whole window.

    An output cap equal to the model's own context is not a cap; measured
    2026-08-24, models.dev does that on nine entries. Those fall through to
    LiteLLM, and are refused outright when LiteLLM knows nothing either.

    The two registries otherwise disagree on 25 of the 143 models where both
    state an output cap, with no structural pattern (16 times LiteLLM is
    smaller, 9 times larger). That residue is a stated limitation, not a
    solved problem: no third source exists, and the field feeds admin display
    and the reasoning-budget ratio rather than any hard limit.
    """
    limit = (md or {}).get("limit") or {}
    declared = _positive_int(limit.get("output"))
    context = _positive_int(limit.get("context"))
    if declared is not None and declared != context:
        return "modelsdev", declared
    fallback = _positive_int((ll or {}).get("max_output_tokens"))
    if fallback is not None:
        return "litellm", fallback
    # A window-wide "cap" is refused outright rather than adopted as a last
    # resort: the row then keeps its 4096 default, which under-states instead
    # of over-stating, and an inflated cap would inflate the reasoning budget
    # derived from it. Measured 2026-08-24: no LIA row reaches this branch.
    return None, None


def _deprecation_date(raw: Any) -> date | None:
    """Parse LiteLLM's ISO ``deprecation_date``, tolerating a malformed one.

    The registry is external and refreshed by a developer task, so a shape
    change must degrade to "no date" rather than break every caller. All 45
    values parsed on 2026-08-24; the branch exists for the next refresh.
    """
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.warning("registry_deprecation_date_unparseable", raw=raw)
        return None


def registry_facts(provider: str, model: str, *, kind: str | None = None) -> RegistryFacts | None:
    """Merge public registries, then pinned vendor facts if neither knows the model.

    Args:
        provider: LIA provider id.
        model: LIA model name.
        kind: The catalogue row's ``kind`` when the caller knows it. It gates
            the one fact whose meaning depends on what the model is — see
            :data:`_NO_OUTPUT_CAP_KINDS`.

    Returns:
        The merged facts, with a ``sources`` map naming the registry that
        supplied each populated field.
    """
    ll = match_litellm(provider, model)
    md = match_modelsdev(provider, model)
    if ll is None and md is None:
        return _VENDOR_CAPABILITIES.get((provider, model))

    sources: dict[str, str] = {}
    booleans = _boolean_facts(ll, md, sources)
    deprecation: tuple[str | None, date | None] = (
        "litellm",
        _deprecation_date((ll or {}).get("deprecation_date")),
    )
    status: tuple[str | None, Any] = ("modelsdev", (md or {}).get("status"))
    announced, shutdown = announced_shutdown(provider, model)
    if announced:
        # The vendor's own page outranks the copies (see vendor_announcements):
        # its date replaces the registry's, and a model it lists with no
        # shutdown announced is not « deprecated » whatever a registry flags.
        deprecation = ("vendor", shutdown)
        if shutdown is None:
            status = ("vendor", None)

    return RegistryFacts(
        max_input_tokens=_record(sources, "max_input_tokens", _max_input(ll, md)),
        max_output_tokens=_record(
            sources,
            "max_output_tokens",
            (None, None) if kind in _NO_OUTPUT_CAP_KINDS else _max_output(ll, md),
        ),
        supports_tools=booleans.get("supports_tools"),
        supports_structured_output=booleans.get("supports_structured_output"),
        supports_vision=booleans.get("supports_vision"),
        deprecation_date=_record(sources, "deprecation_date", deprecation),
        registry_status=_record(sources, "registry_status", status),
        matched_registries=frozenset(
            name for name, entry in (("litellm", ll), ("modelsdev", md)) if entry is not None
        ),
        sources=sources,
    )


#: How much warning a build gives before a model retires. One value, so the
#: guard, the sync report and the migration cannot disagree about the horizon.
RETIREMENT_NOTICE = timedelta(days=30)


def is_retiring(
    facts: RegistryFacts,
    *,
    today: date,
    notice: timedelta = RETIREMENT_NOTICE,
) -> bool:
    """Return whether a model is retiring, reading BOTH registry signals.

    The two signals are complementary, not redundant. LiteLLM publishes a
    ``deprecation_date`` for models whose retirement the provider announced;
    models.dev flags ``status="deprecated"`` for the preview families that are
    retired without a published date. Measured 2026-08-24 over LIA's
    catalogue: 45 rows carry a date, 8 carry the flag, seven of them overlap,
    and ``gemini-3.1-flash-lite-preview`` is visible only through the flag.

    This is the single implementation of the policy. The sync report, the
    initial-correction migration and the CI guard all call it, with different
    notice windows: the guard warns 30 days ahead, the migration deactivates
    only what is already past (``notice=timedelta(0)``).

    Args:
        facts: The merged registry facts for the model.
        today: The reference date (timezone-aware UTC date at the call site).
        notice: How far ahead of the published date to start reporting.

    Returns:
        ``True`` when either signal says the model is going away.
    """
    if facts.registry_status == "deprecated":
        return True
    return facts.deprecation_date is not None and facts.deprecation_date <= today + notice


def is_retired(facts: RegistryFacts, *, today: date) -> bool:
    """Return whether a model is demonstrably gone, not merely announced.

    :func:`is_retiring` answers "should a build warn?"; this answers "may the
    catalogue stop offering it?". The two questions deserve different
    evidence, because the costs are not symmetric: deactivating a live model
    drops it out of ``ModelCapabilitiesCache`` and falls back to
    ``CONSERVATIVE_DEFAULT``, whose ``is_reasoning_model=False`` makes the
    adapter send sampling parameters to a reasoning model and the provider
    answer 400. Leaving a dead model listed only leaves a stale dropdown entry,
    which the CI guard surfaces anyway.

    So retirement requires a published date already in the past AND no
    contradiction. Measured 2026-08-24 over the snapshot: 71 LiteLLM entries
    are past their date; models.dev corroborates 1, does not list 66 (it drops
    retired models, so silence is weak corroboration) and **contradicts 4** by
    still listing them healthy -- ``gpt-5.2-chat-latest`` and
    ``gpt-5.3-chat-latest`` (rolling aliases OpenAI repoints, where the date
    expires the snapshot rather than the alias) and two Gemini image previews.
    Those four are exactly the false positives this predicate refuses.

    A ``registry_status="deprecated"`` alone never retires a model either: the
    seven LIA rows carrying it also carry a date two months in the FUTURE
    (2026-10-23), so they are announced, not gone.

    Args:
        facts: The merged registry facts for the model.
        today: The reference date (timezone-aware UTC date at the call site).

    Returns:
        ``True`` only when the evidence is uncontradicted.
    """
    if facts.deprecation_date is None or facts.deprecation_date >= today:
        return False
    contradicted = "modelsdev" in facts.matched_registries and facts.registry_status != "deprecated"
    return not contradicted
