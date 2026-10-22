"""One admission predicate, applied before aggregation, retrieval or paid interpretation."""

from collections.abc import Mapping
from datetime import datetime

from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SensitiveTopic,
    SourceKey,
    evidence_identity,
    semantic_version,
)


def observation_key(item: DiscussionEvidence) -> str:
    """Return the identity key of one piece of evidence, whatever its version.

    Args:
        item: The evidence.

    Returns:
        The key under which its observations, exclusions and markers are stored.
    """
    return evidence_identity(item)


def reference_key(reference: str) -> str:
    """Return the key under which an evidence reference is excluded or forgotten.

    Args:
        reference: The evidence reference.

    Returns:
        The reference's hashed key.
    """
    return semantic_version(("reference", reference))


def support_key(support: str) -> str:
    """Return the key of a support: a hashed key as is, a reference through reference_key.

    Args:
        support: A support, either a 64-character hexadecimal key or a reference.

    Returns:
        The support's key.
    """
    if len(support) == 64 and all(character in "0123456789abcdef" for character in support):
        return support
    return reference_key(support)


def _forgotten(
    item: DiscussionEvidence, versions: Mapping[str, str], forgotten_at: datetime | None
) -> bool:
    previous = versions.get(observation_key(item))
    if previous is not None:
        return previous == item.version
    if forgotten_at is None:
        return False
    # A source with no semantic date cannot prove that an unknown old fact is new.
    dated = item.recorded_at or item.occurred_at
    return dated is None or dated <= forgotten_at


def admissible_evidence(
    item: DiscussionEvidence,
    *,
    allowed_sources: frozenset[SourceKey],
    allowed_topics: frozenset[SensitiveTopic],
    excluded_roots: frozenset[str],
    forgotten_versions: Mapping[str, str],
    forgotten_at: datetime | None,
    now: datetime,
) -> bool:
    """The one admission predicate: may this evidence enter the context?

    It must come from an allowed source with all its required sources allowed,
    carry only consented topics, touch no root the person excluded, rest on no
    forgotten support, be unexpired, and not be a fact a purge forgot (the same
    version as forgotten, or undated, or dated before the purge).

    Args:
        item: The evidence.
        allowed_sources: The sources the run may read.
        allowed_topics: The sensitive topics the person allowed.
        excluded_roots: The keys the person marked not usable.
        forgotten_versions: The versions a purge forgot, by key.
        forgotten_at: When the whole context was last purged, if ever.
        now: The current instant.

    Returns:
        True when the evidence may enter the context.
    """
    supports = {support_key(support) for support in item.supports}
    roots = {observation_key(item), *supports}
    return (
        item.source in allowed_sources
        and set(item.required_sources) <= allowed_sources
        and set(item.sensitive_topics) <= allowed_topics
        and not roots.intersection(excluded_roots)
        and not supports.intersection(forgotten_versions)
        and (item.expires_at is None or item.expires_at > now)
        and not _forgotten(item, forgotten_versions, forgotten_at)
    )
