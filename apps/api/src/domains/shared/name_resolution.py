"""Which entry of a directory a spoken name designates — one rule, every directory.

A person says a name the way people do: « Marie », « Marie D », « Dupont »,
rarely the whole display name. The peer tools used to accept only the folded
FULL name while the router recognised a first name on its own
(``name_mentions``): routing and tool disagreed on who exists, and a question
about « Marie » reached a connected user's tool that then refused to find her.

The rule, decided at the FIRST tier that matches anything:

1. the folded full name is identical — the rule every caller applied before,
   kept as the first tier so an exact answer is never second-guessed;
2. every word said is a WHOLE word of the name (two letters and up, so a
   two-letter first name counts), an initial only completing one of them —
   never a fragment inside a word, never an edit distance: guessing who
   someone is would be an invention.

One identity at the deciding tier is the answer; several are an AMBIGUITY the
caller must ask about, never settle by order; none is UNKNOWN. A directory may
name one identity under several spellings (the relationship list's merges):
matches are counted by IDENTITY, so two spellings of one person never make an
ambiguity.

Pure by construction — no session, no setting: each caller owns its directory
(the accepted connections, the relationship list) and what an outcome means
for it.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.domains.shared.name_mentions import TOKEN_RE
from src.domains.shared.text_normalization import fold_name

#: Shortest word that designates someone on its own. A single letter is an
#: initial: it only ever completes a longer word (« Mei D »).
MIN_WORD_LEN: Final[int] = 2

#: Names a refusal lists at most: enough to ask « which one? », bounded so a
#: common first name never floods the model's context.
MAX_NAMED_CANDIDATES: Final[int] = 5


class ResolutionStatus(StrEnum):
    """What a spoken name designates in one directory."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class NameResolution[T: Hashable]:
    """The identities a name designates, at the tier that decided.

    Attributes:
        status: Resolved, ambiguous or unknown.
        matches: The identities at the deciding tier, in directory order — one
            when resolved, several when ambiguous, none when unknown.
        exact: Whether the folded full name decided (tier 1).
    """

    status: ResolutionStatus
    matches: tuple[T, ...]
    exact: bool

    @property
    def match(self) -> T | None:
        """The one identity designated, or None unless resolved."""
        return self.matches[0] if self.status is ResolutionStatus.RESOLVED else None


def _words(text: str) -> list[str]:
    """The folded words of a name, punctuation and symbols removed."""
    return TOKEN_RE.findall(fold_name(text))


def _carries_every_word(said: Sequence[str], name: Sequence[str]) -> bool:
    """Whether every word said is a whole word of the name, initials completing.

    Each word of the name answers ONE word said: « Marie Marie » does not
    designate « Marie Dupont ».
    """
    words = [word for word in said if len(word) >= MIN_WORD_LEN]
    initials = [word for word in said if len(word) < MIN_WORD_LEN]
    if not words:
        return False
    remaining = list(name)
    for word in words:
        if word not in remaining:
            return False
        remaining.remove(word)
    for initial in initials:
        completed = next((word for word in remaining if word.startswith(initial)), None)
        if completed is None:
            return False
        remaining.remove(completed)
    return True


def _identities[T: Hashable](matching: Iterable[T]) -> tuple[T, ...]:
    """Each identity once, in the order the directory gave them."""
    return tuple(dict.fromkeys(matching))


def _decided[T: Hashable](matches: tuple[T, ...], *, exact: bool) -> NameResolution[T]:
    if len(matches) == 1:
        return NameResolution(ResolutionStatus.RESOLVED, matches, exact)
    if matches:
        return NameResolution(ResolutionStatus.AMBIGUOUS, matches, exact)
    return NameResolution(ResolutionStatus.UNKNOWN, (), exact)


def resolve_name[T: Hashable](spoken: str, directory: Sequence[tuple[str, T]]) -> NameResolution[T]:
    """Decide which identity of ``directory`` the name ``spoken`` designates.

    Args:
        spoken: The name as the person said it.
        directory: ``(spelling, identity)`` pairs; an identity may appear under
            several spellings.

    Returns:
        The resolution at the first tier that matched anything.
    """
    folded = fold_name(spoken)
    said = TOKEN_RE.findall(folded)
    if not said:
        return NameResolution(ResolutionStatus.UNKNOWN, (), exact=False)
    exact = _identities(identity for name, identity in directory if fold_name(name) == folded)
    if exact:
        return _decided(exact, exact=True)
    partial = _identities(
        identity for name, identity in directory if _carries_every_word(said, _words(name))
    )
    return _decided(partial, exact=False)


__all__ = [
    "MAX_NAMED_CANDIDATES",
    "MIN_WORD_LEN",
    "NameResolution",
    "ResolutionStatus",
    "resolve_name",
]
