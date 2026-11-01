"""Which listed option an answer to « which one? » designates — read without a model (ADR-367).

Several shown items fit a description, so the person was asked which one, the
options numbered. A click carries its index (:meth:`ChoiceAnswer.from_resume`);
a typed or spoken answer is read here, in the person's language:

- a refusal (« non », « annule », « cancel », « 取消 ») cancels — the lexicon
  the workboard reads its tickets with;
- « none of them » (« aucun », « neither », « 都不是 ») asks for a new lookup;
- an answer that is ONLY a position — « 2 », « le deuxième », « numéro 3 »,
  « the last one », « 第二个 » — names that option;
- otherwise the words that tell ONE option apart from the others (« celui de
  la facture », « the garage one », « celui de dimanche ») name it, read on the
  labels the person was shown; an ordinal beside them must agree with them. A
  Chinese answer writes no spaces (« 关于发票的那个 »): its run is read for the
  longest stretch of it only some options carry (« 发票 »).

Anything else is UNCLEAR: the question is asked again, never guessed. A number
word is read in the person's own language only (« due » is two in Italian and
a date in English), and « one » is no number (« the garage one »).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any, Final

from src.core.i18n import resolve_language
from src.core.i18n_patterns import (
    CHOICE_FILLER_WORDS,
    CHOICE_LAST_WORDS,
    CHOICE_NONE_PHRASES,
    CHOICE_NUMBER_WORDS,
    FUNCTION_WORDS,
    get_ordinal_map,
    get_ordinal_suffix_patterns,
)
from src.core.i18n_workboard import ANSWER_POLITE_WORDS
from src.domains.agents.context.descriptor_match import (
    carries,
    folded_words,
    is_cjk,
    word_runs,
)
from src.domains.shared.answer_lexicon import answer_tokens, consumed_by, lexicon
from src.domains.shared.text_normalization import fold_name
from src.domains.workboard.answers import Answer, classify_answer

__all__ = [
    "CHOICE_CANCEL",
    "CHOICE_NONE",
    "CHOICE_SELECT",
    "CHOICE_UNCLEAR",
    "FIELD_SELECTED_INDEX",
    "ChoiceAnswer",
    "read_choice_answer",
]

#: The person chose an option — :data:`FIELD_SELECTED_INDEX` names it.
CHOICE_SELECT: Final = "select"
#: The item is none of the options: it is looked up anew.
CHOICE_NONE: Final = "none"
#: The person declined: nothing is done.
CHOICE_CANCEL: Final = "cancel"
#: The answer names no single option: the question is asked again.
CHOICE_UNCLEAR: Final = "unclear"
#: The chosen option's 1-based position, in the resume payload.
FIELD_SELECTED_INDEX: Final = "selected_index"

_LAST: Final = -1
#: A Chinese classifier closing a position (« 第二个 », « 最后一个 »).
_ZH_CLASSIFIER = re.compile(r"[个号项条封位]$")
#: How much of one Chinese run is compared, stretch by stretch (bounded work).
_CJK_RUN_MAX: Final = 32
#: The shortest stretch of a Chinese run that can tell an option apart.
_CJK_STRETCH_MIN: Final = 2


@dataclass(frozen=True)
class ChoiceAnswer:
    """What an answer to « which one? » came to."""

    action: str
    index: int | None = None

    def resume(self) -> dict[str, Any]:
        """The payload the waiting question is resumed with."""
        payload: dict[str, Any] = {"action": self.action}
        if self.index is not None:
            payload[FIELD_SELECTED_INDEX] = self.index
        return payload

    @classmethod
    def from_resume(cls, payload: object, options: int) -> ChoiceAnswer:
        """Read a resume payload back — strictly: anything malformed is UNCLEAR.

        Args:
            payload: What the question was resumed with.
            options: How many options were offered.

        Returns:
            The answer it carries.
        """
        if not isinstance(payload, dict):
            return cls(CHOICE_UNCLEAR)
        action = payload.get("action")
        if action in (CHOICE_NONE, CHOICE_CANCEL):
            return cls(str(action))
        index = payload.get(FIELD_SELECTED_INDEX)
        valid = isinstance(index, int) and not isinstance(index, bool) and 1 <= index <= options
        if action == CHOICE_SELECT and valid:
            return cls(CHOICE_SELECT, index)
        return cls(CHOICE_UNCLEAR)


@dataclass(frozen=True)
class _Vocabulary:
    """The words of one language an answer is read with."""

    positions: dict[str, int]
    suffixes: tuple[re.Pattern[str], ...]
    soft: frozenset[str]
    none: frozenset[tuple[str, ...]]


@cache
def _vocabulary(language: str) -> _Vocabulary:
    positions = {fold_name(word): index for word, index in get_ordinal_map(language).items()}
    positions.update(CHOICE_NUMBER_WORDS[language])
    positions.update(dict.fromkeys(CHOICE_LAST_WORDS[language], _LAST))
    polite = frozenset(token for word in ANSWER_POLITE_WORDS for token in answer_tokens(word))
    return _Vocabulary(
        positions=positions,
        suffixes=tuple(re.compile(pattern) for pattern in get_ordinal_suffix_patterns(language)),
        soft=FUNCTION_WORDS[language] | CHOICE_FILLER_WORDS[language] | polite,
        none=lexicon(CHOICE_NONE_PHRASES[language]),
    )


def _forms(token: str) -> tuple[str, ...]:
    """A token, then without the Chinese classifier and « 一 » closing a position."""
    bare = _ZH_CLASSIFIER.sub("", token)
    return (token, bare, bare.removesuffix("一"))


def _numeral(token: str, vocabulary: _Vocabulary) -> int | None:
    """A position written with digits (« 2 », « 2ème », « 第3个 »)."""
    for form in _forms(token):
        for pattern in vocabulary.suffixes:
            if match := pattern.fullmatch(form):
                return int(match.group(1))
    return None


def _word_position(token: str, vocabulary: _Vocabulary) -> int | None:
    """A position written as a word (« deuxième », « two », « 第二个 », « 最后一个 »)."""
    return next((vocabulary.positions[f] for f in _forms(token) if f in vocabulary.positions), None)


def _in_range(position: int, options: int) -> int | None:
    resolved = options if position == _LAST else position
    return resolved if 1 <= resolved <= options else None


def _named_positions(
    tokens: Sequence[str], vocabulary: _Vocabulary, options: int
) -> set[int] | None:
    """The options a position-only answer names — 0 for one that does not exist.

    Digits count here: « 2 » answers a numbered question. None when a token is
    not a position: the answer then describes its option.
    """
    named: set[int] = set()
    for token in tokens:
        position = _word_position(token, vocabulary)
        if position is None:
            position = _numeral(token, vocabulary)
        if position is None:
            return None
        named.add(_in_range(position, options) or 0)
    return named


def _cjk_carried(run: str, texts: Sequence[str]) -> list[bool]:
    """The options carrying the longest stretch of a Chinese run that tells them apart."""
    run = run[:_CJK_RUN_MAX]
    for size in range(len(run), _CJK_STRETCH_MIN - 1, -1):
        found = [False] * len(texts)
        for start in range(len(run) - size + 1):
            carried = [run[start : start + size] in text for text in texts]
            if 0 < sum(carried) < len(texts):
                found = [had or hit for had, hit in zip(found, carried, strict=True)]
        if any(found):
            return found
    return [False] * len(texts)


def _carrier(tokens: Sequence[str], labels: Sequence[str]) -> int | None:
    """The one option carrying the most words that tell the options apart, if any."""
    texts = [folded_words(label) for label in labels]
    scores = [0] * len(labels)
    for run in (run for token in tokens for run in word_runs(token)):
        if is_cjk(run):
            carried = _cjk_carried(run, [text for _, text in texts])
        else:
            carried = [carries(run, words, text) for words, text in texts]
        if 0 < sum(carried) < len(labels):
            scores = [score + hit for score, hit in zip(scores, carried, strict=True)]
    best = max(scores, default=0)
    if best == 0 or scores.count(best) > 1:
        return None
    return scores.index(best) + 1


def _described(tokens: Sequence[str], vocabulary: _Vocabulary, labels: Sequence[str]) -> int | None:
    """An option named by its words, an ordinal WORD beside them having to agree."""
    words = [_in_range(p, len(labels)) for t in tokens if (p := _word_position(t, vocabulary))]
    positions = {position for position in words if position is not None}
    rest = [token for token in tokens if _word_position(token, vocabulary) is None]
    carrier = _carrier(rest, labels)
    if len(positions) > 1 or (positions and carrier is not None and carrier not in positions):
        return None
    return carrier if carrier is not None else next(iter(positions), None)


def read_choice_answer(answer: str, labels: Sequence[str], language: str) -> ChoiceAnswer:
    """Which option a typed or spoken answer designates.

    Args:
        answer: What the person wrote or said.
        labels: The options as they were shown, in order.
        language: The person's language: number words are read in it.

    Returns:
        A choice, « none of them », a cancellation, or UNCLEAR.
    """
    tokens = answer_tokens(answer)
    if not tokens:
        return ChoiceAnswer(CHOICE_UNCLEAR)
    if classify_answer(answer) is Answer.REFUSE:
        return ChoiceAnswer(CHOICE_CANCEL)
    vocabulary = _vocabulary(resolve_language(language))
    if consumed_by(tokens, vocabulary.none, vocabulary.soft):
        return ChoiceAnswer(CHOICE_NONE)
    informative = [token for token in tokens if token not in vocabulary.soft]
    named = _named_positions(informative, vocabulary, len(labels)) if informative else None
    if named is not None:
        index = named.pop() if len(named) == 1 else 0
    else:
        index = _described(informative, vocabulary, labels) or 0
    return ChoiceAnswer(CHOICE_SELECT, index) if index else ChoiceAnswer(CHOICE_UNCLEAR)
