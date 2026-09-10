"""What the person answered on a ticket LIA is waiting on (ADR-276, lot 7).

A run that met an action it may not perform alone put the draft on the ticket
and handed the ticket back. The person answers with a COMMENT, then hands the
ticket to LIA again — and that handover is where the answer is read. Three
verdicts, and the third is the safe one:

- **approve** — the comment is nothing but an approval (« oui », « ok, vas-y »,
  « yes please », « ja », « sí », « sì », « 好的 »): the sweep replays the
  approved action, identical to the one shown, and nothing else;
- **refuse** — nothing but a refusal (« non », « annule », « no thanks »,
  « nein », « 取消 »): the ticket is cancelled and stays with the person;
- **amend** — anything else. « Oui mais change le sujet » is not an approval:
  the words enter the next brief as the owner's own notes and LIA re-reads,
  rebuilds, and asks again if it must.

No model call: a lexicon in six languages, matched on the WHOLE answer once it
is folded (accents, case, punctuation) and tokenised. A phrase that is not
exactly an approval or a refusal is an amendment — the direction in which a
misreading costs a second question rather than an action nobody wanted.
"""

from __future__ import annotations

from enum import Enum

from src.core.i18n_workboard import (
    ANSWER_APPROVAL_PHRASES,
    ANSWER_FILLER_WORDS,
    ANSWER_POLITE_WORDS,
    ANSWER_REFUSAL_PHRASES,
)
from src.domains.shared.text_normalization import fold_name


class Answer(str, Enum):
    """What the person's comment means for the pending action."""

    APPROVE = "approve"
    REFUSE = "refuse"
    AMEND = "amend"


def _tokens(text: str) -> tuple[str, ...]:
    """Fold and tokenise an answer.

    Accents and case go through :func:`fold_name` — the one folding this
    repository has — and every character that is neither a letter, a digit nor
    whitespace becomes a separator, so « Oui, vas-y ! » and « oui vas y » are
    the same answer. CJK characters are letters to Python, so a Chinese answer
    with no spaces stays one token, matched whole.

    Args:
        text: The comment body.

    Returns:
        The tokens, in order.
    """
    folded = fold_name(text)
    separated = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in folded)
    return tuple(separated.split())


def _phrases(raw: frozenset[str]) -> frozenset[tuple[str, ...]]:
    """Fold a lexicon the way the answer is folded, so both sides agree."""
    return frozenset(_tokens(phrase) for phrase in raw if _tokens(phrase))


_APPROVALS = _phrases(ANSWER_APPROVAL_PHRASES)
_REFUSALS = _phrases(ANSWER_REFUSAL_PHRASES)
#: Words an answer may carry without changing its meaning: politeness and
#: the small words a phrase leans on (« annule tout », « cancel it »).
_SOFT = frozenset(
    token for phrase in ANSWER_POLITE_WORDS | ANSWER_FILLER_WORDS for token in _tokens(phrase)
)


def _consumed_by(tokens: tuple[str, ...], phrases: frozenset[tuple[str, ...]]) -> bool:
    """Whether the answer is nothing but phrases of one family, plus soft words.

    Greedy, longest phrase first, so « oui vas-y » reads as one approval and
    « no thanks » as one refusal. At least one phrase must match: an answer
    made of soft words alone (« merci ») means nothing here.

    Args:
        tokens: The folded answer.
        phrases: One family's lexicon, folded.

    Returns:
        True when every token was consumed and a phrase was met.
    """
    longest = max((len(phrase) for phrase in phrases), default=0)
    index = 0
    matched = False
    while index < len(tokens):
        for length in range(min(longest, len(tokens) - index), 0, -1):
            if tokens[index : index + length] in phrases:
                index += length
                matched = True
                break
        else:
            if tokens[index] in _SOFT:
                index += 1
                continue
            return False
    return matched


def classify_answer(text: str) -> Answer:
    """Read what the person's comment means for the pending action.

    Args:
        text: The comment body, in any of the six languages.

    Returns:
        :attr:`Answer.APPROVE` for a bare approval, :attr:`Answer.REFUSE` for a
        bare refusal, :attr:`Answer.AMEND` for everything else — an empty
        comment included.
    """
    tokens = _tokens(text)
    if not tokens:
        return Answer.AMEND
    if _consumed_by(tokens, _APPROVALS):
        return Answer.APPROVE
    if _consumed_by(tokens, _REFUSALS):
        return Answer.REFUSE
    return Answer.AMEND


__all__ = ["Answer", "classify_answer"]
