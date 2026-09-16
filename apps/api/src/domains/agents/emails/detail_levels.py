"""What a message carries at each detail level, and how a long body is served (ADR-287).

The assistant REASONS over e-mails — « résume mes non lus », « synthèse des
newsletters de la semaine », a morning routine — so ``get_emails_tool`` serves
three levels chosen by the question:

- ``metadata``: sender, subject, date, snippet, labels, attachments; no body,
  no model call. For listings.
- ``full`` (default): the clean text body, paginated by PARAGRAPH under a token
  budget — never cut mid-sentence, the continuation stated (``body_part`` /
  ``body_parts``). For one or a few messages.
- ``summary``: one digest per message (``emails/digest.py``), computed once and
  cached; the body sheds where a digest landed and stays where none could.
  For syntheses over many messages.

Before: every search downloaded every body and cut it at 1 500 characters —
a bound published nowhere, which is how a professional assistant came to treat
e-mails superficially. The budget here is in TOKENS (the currency the model
pays in) and a cut is always stated (ADR-184).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import structlog

from src.core.field_names import FIELD_BODY, FIELD_BODY_PART, FIELD_BODY_PARTS

logger = structlog.get_logger(__name__)

# What the digest step stamps on a message it condensed; anything else keeps
# its body under ``summary`` so the model can still read the message.
DIGEST_STATUSES_WITH_A_DIGEST: frozenset[str] = frozenset({"cached", "computed"})

_PARAGRAPH_SEPARATOR = "\n\n"
_LINE_SEPARATOR = "\n"


class EmailDetail(StrEnum):
    """The detail levels ``get_emails_tool`` publishes (ADR-287)."""

    METADATA = "metadata"
    SUMMARY = "summary"
    FULL = "full"


DEFAULT_DETAIL: EmailDetail = EmailDetail.FULL


def coerce_detail(value: object) -> EmailDetail:
    """Read the level a caller asked for; anything unknown is the default.

    The semantic validator does not enforce ``enum`` constraints (ADR-184
    pointed the other way: a bound must be enforced where it is published), so
    the tool repairs an unknown value to the default rather than failing the
    step — and says so in the log.

    Args:
        value: What the caller passed (a string, an enum member, or nothing).

    Returns:
        The level.
    """
    if isinstance(value, EmailDetail):
        return value
    if isinstance(value, str):
        normalised = value.strip().lower()
        for member in EmailDetail:
            if member.value == normalised:
                return member
    if value is not None:
        # The value is what a model wrote: counted at INFO, quoted at DEBUG only.
        logger.info("email_detail_unknown_defaulted")
        logger.debug("email_detail_unknown_value", requested=str(value)[:32])
    return DEFAULT_DETAIL


def _chunks_under(pieces: list[str], separator: str, budget: int) -> list[str]:
    """Group consecutive ``pieces`` under ``budget`` tokens each, joined by ``separator``.

    A piece that alone exceeds the budget becomes its own chunk, whole.
    """
    from src.domains.agents.utils.token_utils import count_tokens

    chunks: list[str] = []
    current: list[str] = []
    used = 0
    for piece in pieces:
        cost = count_tokens(piece)
        if current and used + cost > budget:
            chunks.append(separator.join(current))
            current, used = [], 0
        current.append(piece)
        used += cost
    if current:
        chunks.append(separator.join(current))
    return chunks


def _split_body(body: str, part_tokens: int) -> list[str]:
    """Paragraphs first; a paragraph too large for a part breaks at its lines;
    a line too large travels whole — the budget yields, never the sentence."""
    from src.domains.agents.utils.token_utils import count_tokens

    pieces: list[str] = []
    for paragraph in body.split(_PARAGRAPH_SEPARATOR):
        if count_tokens(paragraph) <= part_tokens:
            pieces.append(paragraph)
            continue
        pieces.extend(_chunks_under(paragraph.split(_LINE_SEPARATOR), _LINE_SEPARATOR, part_tokens))
    return _chunks_under(pieces, _PARAGRAPH_SEPARATOR, part_tokens)


def paginate_body(body: str, *, part: int, part_tokens: int) -> tuple[str, int]:
    """Serve one part of a long body and say how many parts there are.

    Args:
        body: The clean text body.
        part: The 1-based part wanted; clamped into ``[1, total]``.
        part_tokens: Tokens one part may hold.

    Returns:
        ``(text, total_parts)``. When more parts follow, ``text`` ends with a
        continuation line naming the next ``part`` to pass.
    """
    if not body:
        return "", 1
    parts = _split_body(body, part_tokens)
    total = len(parts)
    index = min(max(part, 1), total)
    text = parts[index - 1]
    if index < total:
        text = f"{text}\n[continued: part {index}/{total}; pass part={index + 1} for the next one]"
    return text, total


def apply_detail_level(
    emails: list[dict[str, Any]], *, detail: EmailDetail, part: int, part_tokens: int
) -> None:
    """Shape each message IN PLACE for the requested level.

    Runs after the fetch and — for ``summary`` — after the digest step, which
    stamps ``digest_status`` on every message it handled.

    Args:
        emails: The messages, as the client normalised them.
        detail: The level asked for.
        part: The 1-based body part wanted under ``full``.
        part_tokens: Tokens one body part may hold.
    """
    for email in emails:
        if detail is EmailDetail.METADATA:
            email.pop(FIELD_BODY, None)
            continue
        if (
            detail is EmailDetail.SUMMARY
            and email.get("digest_status") in DIGEST_STATUSES_WITH_A_DIGEST
        ):
            email.pop(FIELD_BODY, None)
            continue
        body = email.get(FIELD_BODY)
        if not isinstance(body, str):
            continue
        text, total = paginate_body(body, part=part, part_tokens=part_tokens)
        email[FIELD_BODY] = text
        email[FIELD_BODY_PART] = min(max(part, 1), total)
        email[FIELD_BODY_PARTS] = total


__all__ = [
    "DEFAULT_DETAIL",
    "DIGEST_STATUSES_WITH_A_DIGEST",
    "EmailDetail",
    "apply_detail_level",
    "coerce_detail",
    "paginate_body",
]
