"""Which listed items a description designates — by the words that name them (ADR-367).

« Reply to Jérôme's email », « cancel the dentist », « call Jean from Lyon »:
the person designates an item the assistant already showed by WHAT it is. The
words of that description are matched against the item's identity, folded the
way the codebase folds a name (:func:`fold_name`: accents and case away), word
by word:

- **every word must be carried** by the item. A word no item carries is never
  dropped — dropping it is how « Marc Dupont » would come to designate
  « Marc Dubois », and a description that designates nothing must say so;
- a word of six letters or more also matches the END of a longer word, the
  head of a compound (« Rechnung » in « Werkstattrechnung »); a shorter word,
  or a prefix, never does (« Marc » is not in « Marcel », « Martin » not in
  « Martinez »);
- a Chinese run is matched as a substring: the language writes no spaces;
- the identity fields are read first; an item's CONTENT (a body, notes) only
  when no item matches on its identity — a word of a body is a weaker sign
  than the same word in a subject.

Pure functions, no I/O: the resolver, the answer to a disambiguation question
and the context tools read ONE matcher.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from functools import cache
from typing import Any, TypeVar

from src.core.i18n_patterns import get_all_function_words
from src.domains.agents.context.registry import ContextTypeDefinition
from src.domains.shared.text_normalization import fold_name

__all__ = [
    "carries",
    "descriptor_tokens",
    "folded_words",
    "is_cjk",
    "items_matching",
    "strings_at",
    "strings_of",
    "word_runs",
]

#: A word of the description long enough to be the head of a compound.
COMPOUND_SUFFIX_MIN_CHARS = 6

_CJK_CHARS = "㐀-䶿一-鿿豈-﫿"
_TOKEN = re.compile(rf"[{_CJK_CHARS}]+|[^\W_{_CJK_CHARS}]+", re.UNICODE)
_CJK = re.compile(rf"[{_CJK_CHARS}]")

ItemT = TypeVar("ItemT", bound=Mapping[str, Any])


@cache
def _function_words() -> frozenset[str]:
    return get_all_function_words()


def is_cjk(token: str) -> bool:
    """Whether a token is (or holds) Chinese characters."""
    return _CJK.search(token) is not None


def word_runs(token: str) -> tuple[str, ...]:
    """A token cut where Chinese meets another script (« marc的那个 » → marc, 的那个)."""
    return tuple(_TOKEN.findall(token))


def descriptor_tokens(descriptor: str) -> tuple[str, ...]:
    """The words of a description that can identify an item, folded, in order.

    Function words of the six languages and lone letters (the « s » an English
    possessive leaves) carry no identity and are left out.

    Args:
        descriptor: The description as the analyzer extracted it.

    Returns:
        The identifying words; empty when none is left.
    """
    return tuple(
        token
        for token in _TOKEN.findall(fold_name(descriptor or ""))
        if is_cjk(token) or (len(token) > 1 and token not in _function_words())
    )


def strings_of(value: Any) -> Iterator[str]:
    """Every string a field holds, nested people and places included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from strings_of(nested)
    elif isinstance(value, list | tuple):
        for nested in value:
            yield from strings_of(nested)


def strings_at(value: Any, path: str) -> Iterator[str]:
    """Every string at a dotted path (« start.formatted », « emailAddresses.value »).

    A list on the way is walked item by item, so « emailAddresses.value » reads
    every address of a contact.

    Args:
        value: The payload.
        path: Field names joined by dots.

    Returns:
        The strings found there, nested values included.
    """
    head, _, rest = path.partition(".")
    if isinstance(value, list | tuple):
        for nested in value:
            yield from strings_at(nested, path)
    elif isinstance(value, Mapping):
        nested = value.get(head)
        yield from strings_at(nested, rest) if rest else strings_of(nested)


def folded_words(text: str) -> tuple[frozenset[str], str]:
    """A text's folded words and its folded whole, as :func:`carries` reads them.

    Args:
        text: An item's text — its fields joined, or a label.

    Returns:
        The set of its folded words, and the folded text itself.
    """
    folded = fold_name(text)
    return frozenset(_TOKEN.findall(folded)), folded


def carries(token: str, words: frozenset[str], text: str) -> bool:
    """Whether a folded word of a description is carried by a text.

    Args:
        token: One word of the description, folded.
        words: The text's folded words (:func:`folded_words`).
        text: The folded text, where a Chinese run is looked for.

    Returns:
        True for the word itself, a compound it heads, or a Chinese substring.
    """
    if is_cjk(token):
        return token in text
    if token in words:
        return True
    return len(token) >= COMPOUND_SUFFIX_MIN_CHARS and any(
        len(word) > len(token) and word.endswith(token) for word in words
    )


def _matching(
    tokens: tuple[str, ...], items: Sequence[ItemT], fields: Sequence[str]
) -> list[ItemT]:
    matched: list[ItemT] = []
    for item in items:
        words, text = folded_words(
            " ".join(s for field in fields for s in strings_of(item.get(field)))
        )
        if all(carries(token, words, text) for token in tokens):
            matched.append(item)
    return matched


def _named_exactly(descriptor: str, matched: list[ItemT], fields: Sequence[str]) -> list[ItemT]:
    """The matched items one of whose fields IS the description, else all of them.

    « Jean » designates the contact named « Jean » rather than « Jean Dupond »;
    two items named alike stay two.
    """
    whole = " ".join(fold_name(descriptor).split())
    named = [
        item
        for item in matched
        if any(
            " ".join(fold_name(text).split()) == whole
            for field in fields
            for text in strings_of(item.get(field))
        )
    ]
    return named or matched


def items_matching(
    descriptor: str, items: Sequence[ItemT], definition: ContextTypeDefinition
) -> list[ItemT]:
    """The items a description designates, in the order they were listed.

    Args:
        descriptor: The words the person designated the item with.
        items: The listed items (registry payloads).
        definition: The context type, which declares the identity fields and
            the content fields of its items.

    Returns:
        Every item carrying all the description's words on its identity, else
        on its content — narrowed to those a field names EXACTLY when there are
        some; empty when the description designates none of them.
    """
    tokens = descriptor_tokens(descriptor)
    if not tokens:
        return []
    for fields in (definition.reference_fields, definition.content_reference_fields):
        if fields and (matched := _matching(tokens, items, fields)):
            return _named_exactly(descriptor, matched, fields) if len(matched) > 1 else matched
    return []
