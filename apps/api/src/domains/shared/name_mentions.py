"""Which names from a directory are mentioned in a turn's texts.

One implementation, because two would eventually disagree — and disagreeing
here means one surface believes a person was named while another does not, over
the same sentence. It grew inside ``agents/services/analysis/peer_directory``
while connected peers were the only directory anyone matched against; the
relationship debrief matches against a second one, and lives in ``relations``,
which the agents layer imports. Reaching back would close a runtime cycle
(F009), and a local import would only hide that edge.

So the matcher sits in ``shared``, beside ``fold_name`` — the folding it is
built on — and both callers keep their own vocabulary above it.

Matching is accent- and case-insensitive, on whole words, over the full name
AND each of its tokens long enough to be distinctive: users drop the surname as
soon as the conversation is under way.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import Final

from src.domains.shared.text_normalization import fold_name

#: Shortest token that may stand for a person on its own. Below this, a name
#: fragment matches half the language.
MIN_TOKEN_LEN: Final[int] = 3

#: Alphanumeric runs, Unicode-aware, underscore excluded — used both to split a
#: name into tokens and to define the word boundaries a match must respect.
TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[^\W_]+")


@lru_cache(maxsize=512)
def word_bounded(needle: str) -> re.Pattern[str]:
    """Compile a whole-word matcher for one folded needle.

    ``\\b`` is not usable here: it treats ``_`` as a word character and would
    also fire inside ``snake_case`` blobs. The lookarounds below use the same
    alphanumeric class as :data:`TOKEN_RE`, so "Jean" matches "jean," and
    "(jean)" but never "jeans".

    Args:
        needle: Already folded search term.

    Returns:
        Compiled pattern matching ``needle`` on alphanumeric boundaries.
    """
    return re.compile(rf"(?<![^\W_]){re.escape(needle)}(?![^\W_])")


def search_needles(folded_name: str) -> set[str]:
    """Every folded form whose presence means this name was used.

    Args:
        folded_name: A display name, already folded.

    Returns:
        Folded needles to search for.
    """
    needles = {folded_name}
    needles.update(token for token in TOKEN_RE.findall(folded_name) if len(token) >= MIN_TOKEN_LEN)
    return needles


def folded_haystack(texts: Iterable[str | None]) -> str:
    """Fold and join every usable text into one searchable blob."""
    return "\n".join(fold_name(text) for text in texts if isinstance(text, str) and text.strip())


def usable_names(names: Sequence[str | None]) -> list[str]:
    """Strip blanks and non-strings from a directory, preserving order."""
    return [name.strip() for name in names if isinstance(name, str) and name.strip()]


def detect_mentioned_names(
    texts: Iterable[str | None],
    names: Sequence[str | None],
) -> list[str]:
    """Find which of ``names`` are named in the turn's texts.

    Args:
        texts: Every text that may carry a name — the original query, the
            English pivot, and the values of resolved references (``"mon
            frère"`` → ``"Jérôme G"``, where the name is in the mapping and
            never in what the user typed).
        names: The directory to match against, as displayed.

    Returns:
        The matching names, in directory order, without duplicates.
    """
    directory = usable_names(names)
    haystack = folded_haystack(texts)
    if not directory or not haystack:
        return []

    mentioned: list[str] = []
    for name in directory:
        folded = fold_name(name)
        if not folded or name in mentioned:
            continue
        if any(word_bounded(needle).search(haystack) for needle in search_needles(folded)):
            mentioned.append(name)
    return mentioned
