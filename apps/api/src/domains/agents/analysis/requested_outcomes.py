"""Explicit, source-anchored result requirements; never anticipated needs."""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.date_quotes import date_from_quote


class GoalFieldExpectation(BaseModel):
    """A literal field constraint, quoted from the current user's request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1)
    expected_value: str
    operator: Literal["equals", "on_date"] = "equals"
    source_quote: str = Field(min_length=1)
    reference_date: str | None = None
    reference_timezone: str | None = None


class GoalRequirement(BaseModel):
    """A requested result whose existence can be checked against canonical outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    kind: Literal["read", "action"] = "read"
    operation: Literal["create", "update", "delete", "send"] | None = None
    collection_key: str | None = None
    min_count: int | None = Field(default=None, ge=0)
    requires_complete: bool = False
    expected_fields: tuple[GoalFieldExpectation, ...] = ()


def _quoted(quote: str, query: str) -> bool:
    """Whitespace/case tolerance preserves a literal anchor without inferring intent."""
    normalized = " ".join(quote.split()).casefold()
    return bool(normalized) and normalized in " ".join(query.split()).casefold()


def anchored_requirements(
    requirements: Iterable[GoalRequirement],
    query: str,
    domains: Collection[str],
    *,
    reference_date: date | None = None,
    reference_timezone: str | None = None,
    trusted_checkpoint: bool = False,
) -> tuple[GoalRequirement, ...]:
    """Reject invented goals and constraints, including references to older turns."""
    stamped = (
        _stamp_reference_context(goal, reference_date, reference_timezone, trusted_checkpoint)
        for goal in requirements
    )
    return tuple(
        requirement
        for requirement in stamped
        if requirement.domain in domains
        and _quoted(requirement.source_quote, query)
        and _constraints_anchored(requirement, query)
    )


def _constraints_anchored(requirement: GoalRequirement, query: str) -> bool:
    """Literal values/counts must be present, not merely a neighboring quote."""
    if requirement.min_count is not None:
        count = str(requirement.min_count)
        if not (
            _literal_present(count, requirement.source_quote) and _literal_present(count, query)
        ):
            return False
    if requirement.requires_complete and not _exhaustive_quote(requirement.source_quote):
        return False
    return all(
        _quoted(expectation.source_quote, query)
        and _literal_expectation(expectation)
        and (
            _literal_present(expectation.expected_value, query)
            if expectation.operator == "equals"
            else _calendar_quote_present(expectation.source_quote, query)
        )
        for expectation in requirement.expected_fields
    )


def _literal_expectation(expectation: GoalFieldExpectation) -> bool:
    if expectation.operator == "equals":
        return _literal_present(expectation.expected_value, expectation.source_quote)
    try:
        if date.fromisoformat(expectation.expected_value).isoformat() != expectation.expected_value:
            return False
    except ValueError:
        return False
    reference = None
    if expectation.reference_date:
        try:
            reference = date.fromisoformat(expectation.reference_date)
        except ValueError:
            return False
    quoted_date = date_from_quote(
        expectation.source_quote, reference, reference_timezone=expectation.reference_timezone
    )
    return quoted_date is not None and quoted_date.isoformat() == expectation.expected_value


def _literal_present(value: str, quote: str) -> bool:
    """A mailbox, name or number prefix is not a quoted literal value."""
    if not value:
        return False
    before, after = _literal_boundaries(value)
    pattern = f"{before}{re.escape(value)}{after}"
    return re.search(pattern, quote) is not None


def _calendar_quote_present(quote: str, query: str) -> bool:
    """Calendar words retain case tolerance, but cannot be shortened within a token."""
    before, after = _literal_boundaries(quote)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", quote):
        after += r"(?![Tt ][0-9]{2}:[0-9]{2})"
    return re.search(f"{before}{re.escape(quote)}{after}", query, re.IGNORECASE) is not None


def _literal_boundaries(value: str) -> tuple[str, str]:
    """Match complete literal tokens, preserving unambiguous sentence punctuation."""
    if "://" in value:
        # URI query/fragment/path suffixes denote a different resource. Terminal
        # URI punctuation is ambiguous; quotes/angle brackets/space are safe delimiters.
        uri = r"[\w@.%:/?&#=+\-~!$'()*;,]"
        return rf"(?<!{uri})", rf"(?!{uri})"
    if "@" in value:
        mailbox = r"[\w@.!#$%&'*+/?=^`{|}~\-]"
        suffix = r"[\w@+%/'’\-]|[.!#$&*=?^`{|}~][\w@.!#$%&'*+/?=^`{|}~\-]"
        return rf"(?<!{mailbox})", rf"(?!{suffix})"
    if re.fullmatch(r"[+-]?[0-9]+(?:[.,][0-9]+)?", value):
        return r"(?<![\w.\-+−])(?<![0-9][,/:])", r"(?!\w|[.,/:\-'’‐‑+][0-9])"
    return r"(?<!\w)(?<!\w[.'’\-‐‑])", r"(?!\w|[.'’\-‐‑]\w)"


def _stamp_reference_context(
    goal: GoalRequirement,
    reference_date: date | None,
    reference_timezone: str | None,
    trusted_checkpoint: bool,
) -> GoalRequirement:
    if trusted_checkpoint:
        return goal
    updated: GoalRequirement = goal.model_copy(
        update={
            "expected_fields": tuple(
                expectation.model_copy(
                    update={
                        "reference_date": reference_date.isoformat() if reference_date else None,
                        "reference_timezone": reference_timezone,
                    }
                )
                for expectation in goal.expected_fields
            )
        }
    )
    return updated


def _exhaustive_quote(quote: str) -> bool:
    """Conservative literal corroboration, never a natural-language intent parser."""
    words = set(re.findall(r"\w+", quote.casefold()))
    return bool(
        words.intersection(
            {
                "all",
                "every",
                "entire",
                "tous",
                "toutes",
                "tout",
                "toute",
                "alle",
                "sämtliche",
                "todos",
                "todas",
                "tutti",
                "tutte",
            }
        )
    ) or any(word in quote for word in ("所有", "全部", "每个"))


def parse_requirements(value: object) -> tuple[GoalRequirement, ...]:
    """Tolerantly read old checkpoints, without losing valid neighboring goals."""
    if not isinstance(value, (list, tuple)):
        return ()
    requirements: list[GoalRequirement] = []
    for item in value:
        try:
            requirements.append(GoalRequirement.model_validate(item))
        except ValidationError:
            continue
    return tuple(requirements)
