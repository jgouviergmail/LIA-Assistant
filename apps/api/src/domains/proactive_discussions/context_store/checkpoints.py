"""Body-free checkpoints cannot turn unresolved understanding into a ready context."""

import json
from collections.abc import Iterable
from typing import Annotated

from pydantic import Field

from src.domains.proactive_discussions.policy import effective_sources
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    DiscussionValue,
    NonEmpty,
    SourceKey,
    semantic_version,
)


class ReadyCheckpoint(DiscussionValue):
    """A ready context's fingerprint: its inputs' signature and each reference's version."""

    signature: NonEmpty
    references: Annotated[dict[str, str], Field(max_length=100)]


def interpretation_signature(policy: DiscussionPolicy, language: str) -> str:
    """Sign what an interpretation's meaning depends on in the policy.

    The readable sources, the consented and the refused topics, the clock and the
    language the summaries are written in. The hours, the daily limit and a pause
    change when LIA may speak, never what a fact means: editing them no longer makes
    every fact interpreted, and paid, again.

    Args:
        policy: The policy the interpretation runs under (its sources narrowed by the
            person's rules).
        language: The language the interpretation writes in.

    Returns:
        The signature.
    """
    # The switch decides whether LIA runs, never what a fact means: the sources are
    # those the consent covers, read as if discussions were on.
    readable = effective_sources(policy.model_copy(update={"enabled": True}), frozenset(SourceKey))
    return semantic_version(
        (
            "interpretation-v1",
            _listed(key.value for key in readable),
            _listed(policy.sensitive_topics),
            _listed({topic.strip().casefold() for topic in policy.forbidden_topics}),
            policy.timezone,
            language,
        )
    )


def _listed(values: Iterable[str]) -> str:
    # A set as one unambiguous string: a refused topic may itself hold a comma.
    return json.dumps(sorted(values), ensure_ascii=False, separators=(",", ":"))


def readiness_signature(interpretation: str, epoch: int, directives: str) -> str:
    """Sign what a ready context depends on: its interpretation, the epoch, the directives.

    Args:
        interpretation: The interpretation signature.
        epoch: The context epoch.
        directives: The directives' revision.

    Returns:
        The signature.
    """
    return semantic_version((interpretation, str(epoch), directives))


def verified_ready(
    checkpoint: ReadyCheckpoint, signature: str, facts: tuple[DiscussionEvidence, ...]
) -> set[str]:
    """Return the references of a ready context that still holds now.

    Args:
        checkpoint: The stored ready checkpoint.
        signature: The current inputs' signature.
        facts: The evidence read now.

    Returns:
        The checkpoint's references when the signature matches and every reference
        is present at its recorded version; otherwise nothing, so an unresolved
        understanding never passes for a ready one.
    """
    current = {fact.reference: fact.version for fact in facts}
    if checkpoint.signature != signature or any(
        current.get(ref) != version for ref, version in checkpoint.references.items()
    ):
        return set()
    return set(checkpoint.references)
