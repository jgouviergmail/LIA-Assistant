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
from src.domains.shared.answer_lexicon import answer_tokens, consumed_by, lexicon


class Answer(str, Enum):
    """What the person's comment means for the pending action."""

    APPROVE = "approve"
    REFUSE = "refuse"
    AMEND = "amend"


_APPROVALS = lexicon(ANSWER_APPROVAL_PHRASES)
_REFUSALS = lexicon(ANSWER_REFUSAL_PHRASES)
#: Words an answer may carry without changing its meaning: politeness and
#: the small words a phrase leans on (« annule tout », « cancel it »).
_SOFT = frozenset(
    token for phrase in ANSWER_POLITE_WORDS | ANSWER_FILLER_WORDS for token in answer_tokens(phrase)
)


def classify_answer(text: str) -> Answer:
    """Read what the person's comment means for the pending action.

    Args:
        text: The comment body, in any of the six languages.

    Returns:
        :attr:`Answer.APPROVE` for a bare approval, :attr:`Answer.REFUSE` for a
        bare refusal, :attr:`Answer.AMEND` for everything else — an empty
        comment included.
    """
    tokens = answer_tokens(text)
    if not tokens:
        return Answer.AMEND
    if consumed_by(tokens, _APPROVALS, _SOFT):
        return Answer.APPROVE
    if consumed_by(tokens, _REFUSALS, _SOFT):
        return Answer.REFUSE
    return Answer.AMEND


__all__ = ["Answer", "classify_answer"]
