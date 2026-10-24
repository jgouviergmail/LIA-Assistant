"""A compiler may narrow source consent; it cannot grant access or change preferences.

Models marked MODEL-FACING below are read by a model as a JSON schema (a
structured-output contract or a tool parameter). They carry comments, never
docstrings or field descriptions: both become schema text, and changing what a
model reads is a measured decision, not documentation.
"""

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AwareDatetime, Field, StrictBool, StrictInt

from src.core.config import settings
from src.core.constants import DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS
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


class RuleCompilationRefused(ValueError):
    """A compilation cited a statement it was not shown, or words that statement lacks."""


class RuleCache(DiscussionValue):
    """A compiled read restriction, reused for the same inputs until it expires.

    A refused compilation is cached too (``refused``), so the compiler is not paid
    again for the same inputs before its wait ends; ``refusals`` counts the
    consecutive refusals of these inputs, which doubles each wait (owner decision,
    2026-10-22). A cache stored before refusals were kept reads as a compilation.
    """

    signature: NonEmpty
    expires_at: AwareDatetime
    denied: tuple[SourceKey, ...]
    abstain: StrictBool
    refused: StrictBool = False
    refusals: Annotated[StrictInt, Field(ge=0)] = 0

    def stored(self) -> dict[str, object]:
        """The JSON the account's cache column keeps.

        A compilation is stored in the shape it had before refusals were cached:
        discussion values forbid unknown fields, so writing ``refused: false`` on
        every cache would make a rolled-back release refuse every account's rules.
        """
        return self.model_dump(mode="json", exclude_defaults=True)


def refusal_wait(refusals: int, *, first: timedelta, ceiling: timedelta) -> timedelta:
    """How long the same inputs wait after their ``refusals``-th consecutive refusal.

    Args:
        refusals: The consecutive refusals of these inputs, this one included (>= 1).
        first: The wait after the first one.
        ceiling: The longest wait; reached, it stays.

    Returns:
        ``first`` doubled once per earlier refusal, held to ``ceiling``.
    """
    wait = first
    for _ in range(refusals - 1):
        if wait >= ceiling:
            break
        wait *= 2
    return min(wait, ceiling)


def refused_rule_cache(
    signature: str,
    previous: RuleCache | None,
    *,
    now: datetime,
    first: timedelta,
    ceiling: timedelta,
) -> RuleCache:
    """The cache of a refused compilation, counting on from the previous refusal.

    Args:
        signature: The inputs that were refused.
        previous: What the account's cache held, expired or not.
        now: The run's clock.
        first: The wait after a first refusal.
        ceiling: The longest wait.

    Returns:
        A refusal that leaves no source readable until it expires: other inputs, or
        inputs that last compiled, start again from one refusal.
    """
    refusals = (
        previous.refusals + 1
        if previous is not None and previous.refused and previous.signature == signature
        else 1
    )
    return RuleCache(
        signature=signature,
        expires_at=now + refusal_wait(refusals, first=first, ceiling=ceiling),
        denied=(),
        abstain=True,
        refused=True,
        refusals=refusals,
    )


def cache_compilation(
    compiled: RuleCompilation,
    supports: tuple[ControlSupport, ...],
    sources: tuple[SourceKey, ...],
    *,
    signature: str,
    previous: RuleCache | None,
    now: datetime,
) -> RuleCache:
    """What a fresh compilation leaves in the account's cache: its denials, or a refusal.

    A compilation is reused for ``DISCUSSION_RULE_CACHE_HOURS``. A refused one waits
    ``DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS`` tick intervals, then twice as long
    at each refusal of the same inputs, up to the same lifetime.

    Args:
        compiled: The compiler's answer.
        supports: The first-party statements it was shown.
        sources: The sources the person consented to, in order.
        signature: The inputs it was compiled from.
        previous: What the cache held, expired or not.
        now: The run's clock.

    Returns:
        The cache entry to store.
    """
    lifetime = timedelta(hours=settings.discussion_rule_cache_hours)
    try:
        allowed = restricted_sources(compiled, supports, sources)
    except RuleCompilationRefused:
        first = timedelta(
            minutes=DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS
            * settings.discussion_interval_minutes
        )
        return refused_rule_cache(signature, previous, now=now, first=first, ceiling=lifetime)
    return RuleCache(
        signature=signature,
        expires_at=now + lifetime,
        denied=tuple(key for key in sources if key not in allowed),
        abstain=compiled.abstain,
    )


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
        RuleCompilationRefused: A denial cites a support it was not shown, or a
            quote the support does not contain.
    """
    owned = {item.id: item.text for item in supports}
    for denial in result.denied:
        if denial.support_id not in owned or denial.quote not in owned[denial.support_id]:
            raise RuleCompilationRefused("read restrictions require owned exact rule evidence")
    if result.abstain:
        return ()
    blocked = {item.source for item in result.denied}
    return tuple(source for source in sources if source not in blocked)
