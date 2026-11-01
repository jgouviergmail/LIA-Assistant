"""Reading a short answer against lexicons, without a model (ADR-276, ADR-367).

A person answering LIA's question — the comment on a ticket waiting for them,
the reply to « which of these? » — is read here, never by a model: a lexicon
in six languages, matched on the WHOLE answer once it is folded.

Accents and case go through :func:`fold_name` — the one folding this
repository has — and every character that is neither a letter, a digit nor
whitespace becomes a separator, so « Oui, vas-y ! » and « oui vas y » are the
same answer. CJK characters are letters to Python, so a Chinese answer with no
spaces stays one token, matched whole.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.domains.shared.text_normalization import fold_name

__all__ = ["answer_tokens", "consumed_by", "lexicon"]


def answer_tokens(text: str) -> tuple[str, ...]:
    """Fold and tokenise an answer.

    Args:
        text: What the person wrote or said.

    Returns:
        The tokens, in order.
    """
    folded = fold_name(text)
    separated = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in folded)
    return tuple(separated.split())


def lexicon(raw: Iterable[str]) -> frozenset[tuple[str, ...]]:
    """Fold a lexicon the way an answer is folded, so both sides agree.

    Args:
        raw: The phrases, as written in the lexicon.

    Returns:
        Each non-empty phrase as its tuple of tokens.
    """
    return frozenset(tokens for phrase in raw if (tokens := answer_tokens(phrase)))


def consumed_by(
    tokens: tuple[str, ...], phrases: frozenset[tuple[str, ...]], soft: frozenset[str]
) -> bool:
    """Whether the answer is nothing but phrases of one family, plus soft words.

    Greedy, longest phrase first, so « oui vas-y » reads as one approval and
    « no thanks » as one refusal. At least one phrase must match: an answer
    made of soft words alone (« merci ») means nothing here.

    Args:
        tokens: The folded answer.
        phrases: One family's lexicon, folded.
        soft: Words the answer may carry without changing what it says.

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
            if tokens[index] in soft:
                index += 1
                continue
            return False
    return matched
