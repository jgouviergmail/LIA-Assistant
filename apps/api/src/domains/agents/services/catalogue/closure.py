"""Catalogue closure — a filtered catalogue must let a valid plan exist.

Semantic filtering ranks tools against an English paraphrase of the user's
request. That paraphrase is produced by an LLM at temperature 0.2, so the same
request scores differently from one turn to the next. On 2026-07-30 the same
"summarize this email and draft a reply" was paraphrased "Summarize the email
titled…" (``get_emails_tool`` scored 0.010, excluded) and, thirty minutes
later, "Find the email titled…" (kept). The first run handed the planner
``reply_email_tool`` — whose ``message_id`` parameter is REQUIRED — with no
tool able to produce a ``message_id``. No valid plan existed, so the model
invented ``search_emails_tool``, which has no manifest, and the request failed.

This module removes that coin toss with a structural rule that never looks at
the query:

    A catalogue is CLOSED when every REQUIRED semantic type declared by a tool
    it contains is PRODUCED by another tool it contains.

Think of it as a linker resolving undefined symbols rather than a search
guessing which library is relevant. It is permissive: it makes a correct plan
possible, it never forces a step.

Two rules make it correct rather than merely plausible:

1. A tool never satisfies its own requirement. ``reply_email_tool`` both
   consumes a ``message_id`` (the original) and produces one (the reply it
   sent) — self-satisfaction would have made this whole module a no-op on the
   very incident that motivated it.

2. A provider must be READ-ONLY. ``send_email_tool`` also outputs a
   ``message_id``, and in the failing run it was in the catalogue: a rule that
   accepted any producer would again have concluded "satisfied" and added
   nothing. One does not trigger a side effect to discover an identifier.

Stated limit: closure guarantees a declared source is PRESENT, not that an
execution order exists. Two tools each requiring what the other yields would
both be legitimate sources of each other and deadlock at plan time. No manifest
declares such a cycle today; detecting it would need a topological pass, and
``MAX_CLOSURE_ROUNDS`` keeps the resolution terminating meanwhile.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.domains.agents.registry.catalogue import is_read_only_tool

# A provider pulled in may itself require a handle. Two extra rounds cover every
# chain observed in the manifests (the deepest is one hop); the bound exists so
# a future cyclic declaration cannot spin here.
MAX_CLOSURE_ROUNDS = 3


@dataclass(frozen=True)
class ClosureResult:
    """Outcome of a closure computation over a filtered catalogue.

    Attributes:
        additions: Provider tool names to add, in the order they were resolved.
        consumers: Names of already-kept tools that had at least one unsatisfied
            required type when the closure started — including those for which
            no provider could be found. Callers must not evict them to make
            room: dropping a consumer strands the provider added for it, and
            the over-inclusion is harmless (the query selected them anyway).
    """

    additions: list[str] = field(default_factory=list)
    consumers: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        """True when the catalogue was not already closed."""
        return bool(self.additions)


def _required_semantic_types(manifest: Any) -> set[str]:
    """Semantic types this tool cannot run without.

    Args:
        manifest: Tool manifest to inspect.

    Returns:
        Semantic type names carried by its REQUIRED parameters. Optional
        parameters are excluded on purpose: the planner may simply omit them,
        so their absence never empties the plan space.
    """
    return {
        semantic_type
        for param in getattr(manifest, "parameters", None) or []
        if (semantic_type := getattr(param, "semantic_type", None))
        and getattr(param, "required", False)
    }


def _produced_semantic_types(manifest: Any) -> set[str]:
    """Semantic types this tool yields in its declared outputs.

    Args:
        manifest: Tool manifest to inspect.

    Returns:
        Semantic type names carried by its output fields.
    """
    return {
        semantic_type
        for output in getattr(manifest, "outputs", None) or []
        if (semantic_type := getattr(output, "semantic_type", None))
    }


def _domain_of(manifest: Any) -> str:
    """Functional domain owning a manifest (``email_agent`` -> ``email``)."""
    return (getattr(manifest, "agent", "") or "").removesuffix("_agent")


def _can_source(manifest: Any, semantic_type: str) -> bool:
    """Whether this tool can be RUN to obtain ``semantic_type``.

    The single definition of "source", shared by the satisfaction check and the
    provider selection so they cannot drift apart. Three conditions:

    - it declares the type as an output;
    - it is read-only — a mutation's output identifies the resource it just
      created, which never answers "where do I find the existing one?";
    - it does not itself REQUIRE that type — a tool needing a ``URL`` to yield a
      ``URL`` is exactly as stuck as the tool we are trying to unblock.

    Args:
        manifest: Tool manifest to test.
        semantic_type: The semantic type to obtain.

    Returns:
        True when running this tool can produce a value of that type.
    """
    return (
        semantic_type in _produced_semantic_types(manifest)
        and is_read_only_tool(manifest)
        and semantic_type not in _required_semantic_types(manifest)
    )


def _discoverable_sources(manifests: Iterable[Any]) -> dict[str, set[str]]:
    """Index the tools that can source each semantic type.

    Args:
        manifests: Manifests currently in the catalogue.

    Returns:
        Mapping of semantic type name -> names of tools that can source it.
    """
    sources: dict[str, set[str]] = {}
    for manifest in manifests:
        if not is_read_only_tool(manifest):
            continue
        for semantic_type in _produced_semantic_types(manifest):
            if _can_source(manifest, semantic_type):
                sources.setdefault(semantic_type, set()).add(manifest.name)
    return sources


def _unsatisfied_requirements(manifests: Sequence[Any]) -> dict[str, set[str]]:
    """Required semantic types that no OTHER kept read-only tool can source.

    Args:
        manifests: Manifests currently in the catalogue.

    Returns:
        Mapping of unsatisfied semantic type -> names of the tools requiring it.
    """
    sources = _discoverable_sources(manifests)
    unsatisfied: dict[str, set[str]] = {}
    for manifest in manifests:
        for semantic_type in _required_semantic_types(manifest):
            # "- {manifest.name}" is the rule that keeps a tool from satisfying
            # itself (reply_email_tool consumes AND produces message_id).
            if sources.get(semantic_type, set()) - {manifest.name}:
                continue
            unsatisfied.setdefault(semantic_type, set()).add(manifest.name)
    return unsatisfied


def _best_provider(
    semantic_type: str,
    candidates: Sequence[Any],
    kept_by_name: Mapping[str, Any],
    scores: Mapping[str, float],
    consumers: set[str],
) -> Any | None:
    """Pick the single tool to add as a source for ``semantic_type``.

    One provider is enough to make the plan space non-empty; pulling every
    producer would inflate the catalogue (measured: up to 9 for ``URL``).

    Ordering is fully deterministic — same domain as a consumer first, then
    best semantic score, then name — so an unlucky paraphrase can change WHICH
    provider is offered but never whether one is.

    Args:
        semantic_type: The unsatisfied semantic type.
        candidates: Manifests eligible for the active domains.
        kept_by_name: Manifests already in the catalogue, by name.
        scores: Semantic scores per tool name (may be empty).
        consumers: Names of the tools requiring ``semantic_type``.

    Returns:
        The chosen manifest, or None when no read-only producer exists.
    """
    consumer_domains = {
        _domain_of(kept_by_name[name]) for name in consumers if name in kept_by_name
    }
    eligible = [
        manifest
        for manifest in candidates
        if manifest.name not in kept_by_name and _can_source(manifest, semantic_type)
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda manifest: (
            0 if _domain_of(manifest) in consumer_domains else 1,
            -scores.get(manifest.name, 0.0),
            manifest.name,
        ),
    )


def resolve_closure_additions(
    kept_manifests: Sequence[Any],
    candidate_manifests: Sequence[Any],
    tool_scores: Mapping[str, float] | None = None,
) -> ClosureResult:
    """Compute the tools to add so the catalogue becomes closed.

    Args:
        kept_manifests: Manifests that survived filtering.
        candidate_manifests: Manifests eligible for the active domains.
        tool_scores: Semantic scores per tool name, used only to rank providers
            against one another — never to decide whether to add one.

    Returns:
        A ClosureResult. Empty when the catalogue is already closed, which is
        the overwhelmingly common case (a read-only request selects a read-only
        tool, which requires no handle).
    """
    scores = tool_scores or {}
    kept_by_name: dict[str, Any] = {manifest.name: manifest for manifest in kept_manifests}
    additions: list[str] = []

    unsatisfied = _unsatisfied_requirements(list(kept_by_name.values()))

    # Captured BEFORE any addition: one provider often satisfies several
    # consumers at once (get_emails_tool sources both the email_address that
    # send_email_tool needs and the message_id that reply_email_tool needs).
    # Deriving the list afterwards would silently omit the second consumer,
    # leaving it evictable and stranding the provider added for it.
    consumers: set[str] = {name for requiring in unsatisfied.values() for name in requiring}

    for round_index in range(MAX_CLOSURE_ROUNDS):
        if round_index:
            unsatisfied = _unsatisfied_requirements(list(kept_by_name.values()))
        if not unsatisfied:
            break
        newly_sourced: set[str] = set()
        progressed = False
        for semantic_type in sorted(unsatisfied):
            if semantic_type in newly_sourced:
                continue  # a provider added earlier this round already covers it
            provider = _best_provider(
                semantic_type,
                candidate_manifests,
                kept_by_name,
                scores,
                unsatisfied[semantic_type],
            )
            if provider is None:
                # No read-only producer in the active domains: the manifests
                # cannot express this dependency. Reported by the caller.
                continue
            kept_by_name[provider.name] = provider
            additions.append(provider.name)
            newly_sourced |= {
                produced
                for produced in _produced_semantic_types(provider)
                if _can_source(provider, produced)
            }
            progressed = True
        if not progressed:
            break

    return ClosureResult(additions=additions, consumers=consumers)


__all__ = [
    "MAX_CLOSURE_ROUNDS",
    "ClosureResult",
    "resolve_closure_additions",
]
