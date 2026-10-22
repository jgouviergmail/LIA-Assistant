"""A compiler may narrow source consent; it cannot grant access or change preferences.

Models marked MODEL-FACING below are read by a model as a JSON schema (a
structured-output contract or a tool parameter). They carry comments, never
docstrings or field descriptions: both become schema text, and changing what a
model reads is a measured decision, not documentation.
"""

from typing import Annotated

from pydantic import AwareDatetime, Field, StrictBool

from src.domains.shared.discussion_sources import DiscussionValue, NonEmpty, SourceKey

#: A support is a whole first-party statement: a procedural memory with its nuance
#: and topic, or a reply (up to a chat message). The token budgets bound the set;
#: this bound only keeps the field finite and is wider than anything they admit.
CONTROL_SUPPORT_MAX_CHARS = 100_000


class ControlSupport(DiscussionValue):
    """One first-party statement a read restriction may rest on: a memory or a reply."""

    id: NonEmpty
    text: Annotated[str, Field(min_length=1, max_length=CONTROL_SUPPORT_MAX_CHARS)]


# MODEL-FACING (rule compiler): one source a first-party statement forbids, quoted.
class DeniedSource(DiscussionValue):
    source: SourceKey
    support_id: NonEmpty
    quote: Annotated[str, Field(min_length=1, max_length=400)]


# MODEL-FACING (rule compiler): the denied sources, or an abstention from reading.
class RuleCompilation(DiscussionValue):
    abstain: StrictBool
    denied: Annotated[tuple[DeniedSource, ...], Field(max_length=len(SourceKey))]


class RuleCache(DiscussionValue):
    """A compiled read restriction, reused for the same inputs until it expires."""

    signature: NonEmpty
    expires_at: AwareDatetime
    denied: tuple[SourceKey, ...]
    abstain: StrictBool


def restricted_sources(
    result: RuleCompilation,
    supports: tuple[ControlSupport, ...],
    sources: tuple[SourceKey, ...],
) -> tuple[SourceKey, ...]:
    """Apply a compiled read restriction to the consented sources.

    Every denial must quote its own support verbatim, or the whole compilation is
    refused; an abstention leaves no source readable.

    Args:
        result: The compiled restriction.
        supports: The first-party statements the compiler was shown.
        sources: The sources the person consented to, in order.

    Returns:
        The consented sources the restriction leaves readable, in their order.

    Raises:
        ValueError: A denial cites a support it was not shown, or a quote the
            support does not contain.
    """
    owned = {item.id: item.text for item in supports}
    for denial in result.denied:
        if denial.support_id not in owned or denial.quote not in owned[denial.support_id]:
            raise ValueError("read restrictions require owned exact rule evidence")
    if result.abstain:
        return ()
    blocked = {item.source for item in result.denied}
    return tuple(source for source in sources if source not in blocked)
