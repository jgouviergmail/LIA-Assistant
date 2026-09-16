"""What a person reads once they confirmed: the execution result (ADR-276 lot 13).

A draft is shown twice — the card that asks (``preview_renderer``) and this,
the outcome of what they approved. Lot 13 gave the card ONE vocabulary,
Markdown, and left this one in HTML: it opened every field with ``<br/>`` AND
joined the fields with ``\\n``, so the chat — which renders Markdown with no
hard-break plugin and keeps newlines — showed a blank line between every field
(measured on production, 2026-09-09), and any surface rendering neither
vocabulary read the tag out as typed.

Both surfaces now build their rows with
:mod:`~src.domains.agents.drafts.markdown_grammar`, so the same email cannot
read as a clean list before confirmation and as a stack of blank lines after.

Two rules the shape obeys, each paid for:

- **The renderer owns its own edges.** It used to open on ``\\n\\n`` and rely on
  its caller's ``.strip()``; a second caller would have inherited the blank
  lines. Nothing here opens or closes on whitespace.
- **A message that formats itself is left alone.** ``DRAFT_SUCCESS_MESSAGES``
  is mostly plain text, which the header emphasises — but ``phone_call`` ships
  its own ``**name**``, and wrapping that in another pair renders as broken
  markup. One predicate decides, rather than a special case per type.

This module reads ``DRAFT_DISPLAY_REGISTRY`` (ADR-085) for the per-``DraftType``
display configuration: domain emoji, label fields, optional contextual
datetime, detailed-view fields, plus the noun/verb keys that compose a localized
header like ``"3 rappels supprimés"`` with proper gender/number agreement.

Extracted from ``nodes/response_node.py`` (2026-09-10): the node is a
frozen-size, maximum-complexity hotspot and this is a presentation concern
belonging beside the preview it must agree with.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, DRAFT_RESULT_EXCERPT_MAX_CHARS
from src.core.i18n import _, normalize_language
from src.core.i18n_drafts import (
    EXCERPT_QUOTES,
    compose_result_header,
    get_draft_preview_labels,
)
from src.domains.agents.drafts.card_html import CardSurface, to_html_result
from src.domains.agents.drafts.card_spec import (
    Block,
    Note,
    PreviewLine,
    ResultItem,
    ResultSpec,
    Row,
    to_markdown_lines,
)
from src.domains.agents.drafts.display import (
    get_draft_display_config,
    resolve_nested_value,
)
from src.domains.agents.drafts.markdown_grammar import (
    plain_row,
    readable,
)
from src.domains.agents.drafts.models import DraftAction
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.core.i18n import Language
    from src.domains.agents.drafts.display import DraftDisplayConfig

__all__ = ["describe_execution_result", "render_execution_result"]

logger = get_logger(__name__)

#: Body-like fields carry paragraphs; a confirmation states what was done, it
#: does not reproduce the whole message.
_TEXT_FIELDS = frozenset({"body", "description", "notes"})
_TEXT_FIELD_MAX_CHARS = 200
#: The fields a batch row quotes as its excerpt (ADR-289): the text the action
#: carried — a body, a note, a peer message, a document's appended text.
_EXCERPT_FIELDS = _TEXT_FIELDS | frozenset({"message", "text"})

#: A batch row names its item; a 300-character title would push the outcome
#: off the screen.
_ITEM_LABEL_MAX_CHARS = 60

#: What the reader is told, per status.
#: The ``draft_type`` of a batch whose entries do not share one (ADR-288).
MIXED_BATCH_TYPE = "batch"

_STATUS_MARKS = {
    "success": "✅",
    "cancelled": "🚫",
    "partial_error": "⚠️",
    "error": "❌",
}

_URL_PREFIXES = ("http://", "https://")


def _headline(domain_emoji: str, mark: str, message: str) -> str:
    """The first line: what happened, named once.

    The message is emphasised so it reads as the title of the rows under it —
    unless it already carries emphasis of its own, in which case a second pair
    would nest and render as literal asterisks (``phone_call``). An empty
    message emphasises nothing rather than emitting ``****``.

    Args:
        domain_emoji: The draft family's emoji, or ``""`` for an unknown type.
        mark: The outcome mark (✅ 🚫 ⚠️ ❌).
        message: The localized outcome sentence.

    Returns:
        The headline, with no leading or trailing whitespace.
    """
    text = message.strip()
    if text and "**" not in text:
        text = f"**{text}**"
    return " ".join(part for part in (domain_emoji, mark, text) if part)


def _detail_value(
    field: Any,
    draft: dict[str, Any],
    data: dict[str, Any],
    user_tz: str,
    user_lang: Language,
) -> str | None:
    """Resolve and format ONE detail field, or None when it has nothing to say.

    Args:
        field: The registry's :class:`DraftDisplayField`.
        draft: The stored draft content.
        data: The execution result's data dict (fallback source).
        user_tz: The person's IANA timezone.
        user_lang: Their language.

    Returns:
        The value as text, or None when the field is absent or blank — a label
        above emptiness states less than silence.
    """
    from src.core.time_utils import format_datetime_for_display

    value = (
        resolve_nested_value(draft, field.content_key)
        if "." in field.content_key
        else (draft.get(field.content_key) or data.get(field.content_key))
    )
    if value is None or not str(value).strip():
        return None

    # ``readable`` and not ``str``: a recipient list used to reach this
    # surface as ``['paul@example.org']`` while the confirmation CARD, which
    # shares this grammar, spelled it out. Same draft, two spellings.
    text = readable(value)
    if field.is_datetime and isinstance(value, str) and "T" in value:
        # Keep raw ISO if formatting fails.
        with suppress(ValueError, TypeError):
            text = format_datetime_for_display(value, user_tz, user_lang, include_time=True)

    last_key = field.content_key.rsplit(".", 1)[-1]
    if last_key in _TEXT_FIELDS and len(text) > _TEXT_FIELD_MAX_CHARS:
        text = text[:_TEXT_FIELD_MAX_CHARS] + "…"
    return text


def _detail_lines(
    config: DraftDisplayConfig | None,
    draft: dict[str, Any],
    data: dict[str, Any],
    user_lang: Language,
    user_tz: str,
) -> list[PreviewLine]:
    """One described line per detail field the registry declares.

    Args:
        config: The type's display configuration, or None for an unknown type.
        draft: The stored draft content.
        data: The execution result's data dict.
        user_lang: The person's language.
        user_tz: Their IANA timezone.

    Returns:
        The rows, in registry order, plus the permalink row when one exists,
        then the blocks — a row after a block would land inside its paragraph.
    """
    labels = get_draft_preview_labels(user_lang)
    rows: list[PreviewLine] = []
    blocks: list[PreviewLine] = []
    for field in config.detail_fields if config else ():
        text = _detail_value(field, draft, data, user_tz, user_lang)
        if text is None:
            continue
        label = labels.get(field.label_key, field.content_key)
        if text.startswith(_URL_PREFIXES):
            # A URL-valued field (a conference link) reads as a link, never as
            # a raw URL dump.
            rows.append(Note(f"{field.emoji} [{label}]({text})"))
        elif "\n" in text:
            # A value carrying its own paragraphs cannot live in a list item:
            # the second paragraph escapes the item and the list ends there.
            # The confirmation CARD already renders such a value as its own
            # block, so the outcome does too — otherwise the same mail reads
            # one way before confirmation and another after (measured on a
            # two-paragraph body, which is most of them).
            blocks.append(Block(f"{field.emoji} {label}", text))
        else:
            rows.append(Row(label, text, key=field.label_key, emoji=field.emoji))
    html_link = data.get("html_link")
    if html_link:
        link_label = _("Link", user_lang)
        rows.append(Note(f"🔗 [{link_label}]({html_link})"))
    return rows + blocks


def _batch_locale(batch_results: list[dict[str, Any]]) -> tuple[Language, str]:
    """The language and timezone any item of the batch carries.

    Args:
        batch_results: The per-item results.

    Returns:
        ``(language, timezone)``, falling back to the app defaults.
    """
    raw_lang = "fr"
    user_tz = DEFAULT_USER_DISPLAY_TIMEZONE
    for item in batch_results:
        item_data = item.get("data") if isinstance(item.get("data"), dict) else {}
        content = (item_data or {}).get("_draft_content") or {}
        raw_lang = content.get("user_language") or raw_lang
        user_tz = content.get("user_timezone") or user_tz
        if content.get("user_language") and content.get("user_timezone"):
            break
    return normalize_language(raw_lang), user_tz


def _item_label(config: DraftDisplayConfig | None, content: dict[str, Any]) -> str:
    """The human-readable name of ONE batch item.

    Args:
        config: The type's display configuration.
        content: That item's stored draft content.

    Returns:
        The label, whitespace-collapsed and bounded, or ``""`` when the
        registry's keys resolve to nothing.
    """
    for key in config.item_label_fields if config else ():
        value = resolve_nested_value(content, key) if "." in key else content.get(key)
        if value:
            label = " ".join(str(value).split())
            if len(label) > _ITEM_LABEL_MAX_CHARS:
                return label[: _ITEM_LABEL_MAX_CHARS - 3] + "..."
            return label
    return ""


def _item_secondary(
    config: DraftDisplayConfig | None,
    content: dict[str, Any],
    user_lang: Language,
    user_tz: str,
) -> str:
    """The contextual datetime of a batch item, when the type declares one.

    Args:
        config: The type's display configuration.
        content: That item's stored draft content.
        user_lang: The person's language.
        user_tz: Their IANA timezone.

    Returns:
        The formatted datetime, or ``""``.
    """
    from src.core.time_utils import format_value_if_datetime_string

    if config is None or not config.item_secondary_datetime_key:
        return ""
    key = config.item_secondary_datetime_key
    value = resolve_nested_value(content, key) if "." in key else content.get(key)
    if not value or not isinstance(value, str):
        return ""
    formatted = format_value_if_datetime_string(
        value,
        user_timezone=user_tz,
        locale=user_lang,
        include_time=True,
        include_day_name=False,
    )
    return formatted if formatted != value else ""


def _excerpt(text: str, user_lang: Language) -> str:
    """One bounded line of a text the action carried, quoted (ADR-289).

    Args:
        text: The body, the note — paragraphs and all.
        user_lang: The person's language, which owns its quotation marks.

    Returns:
        The text whitespace-collapsed, cut at the excerpt bound with an
        ellipsis, between the language's own quotation marks.
    """
    flat = " ".join(text.split())
    if len(flat) > DRAFT_RESULT_EXCERPT_MAX_CHARS:
        flat = flat[: DRAFT_RESULT_EXCERPT_MAX_CHARS - 1].rstrip() + "…"
    opening, closing = EXCERPT_QUOTES.get(user_lang, EXCERPT_QUOTES["en"])
    return f"{opening}{flat}{closing}"


def _item_fields(
    config: DraftDisplayConfig | None,
    content: dict[str, Any],
    user_lang: Language,
    user_tz: str,
) -> tuple[tuple[Row, ...], str | None]:
    """The key fields of ONE batch item, and the excerpt of its text.

    ADR-289: the person who approved two e-mails reads, in the answer, who
    received what. The fields are the ones the registry declares for the
    type, minus what the row already says (its label, its datetime), the
    first text field becoming a bounded excerpt.

    Args:
        config: The type's display configuration.
        content: That item's stored draft content.
        user_lang: The person's language.
        user_tz: Their IANA timezone.

    Returns:
        The rows and the excerpt (``None`` when the type carries no text).
    """
    if config is None:
        return (), None
    labels = get_draft_preview_labels(user_lang)
    shown = set(config.item_label_fields)
    if config.item_secondary_datetime_key:
        shown.add(config.item_secondary_datetime_key)
    rows: list[Row] = []
    excerpt: str | None = None
    for field in config.detail_fields:
        if field.content_key in shown:
            continue
        text = _detail_value(field, content, {}, user_tz, user_lang)
        if text is None:
            continue
        if field.content_key.rsplit(".", 1)[-1] in _EXCERPT_FIELDS:
            if excerpt is None:
                excerpt = _excerpt(text, user_lang)
            continue
        rows.append(Row(labels.get(field.label_key, field.content_key), text, key=field.label_key))
    return tuple(rows), excerpt


def _describe_items(
    draft_type: str,
    config: DraftDisplayConfig | None,
    batch_results: list[dict[str, Any]],
    user_lang: Language,
    user_tz: str,
) -> tuple[ResultItem, ...]:
    """One described entry per batch item, each marked with its own outcome.

    Args:
        draft_type: The draft type string (for the diagnostic log).
        config: The batch's display configuration.
        batch_results: The per-item results.
        user_lang: The person's language.
        user_tz: Their IANA timezone.

    Returns:
        The entries, in batch order.
    """
    items: list[ResultItem] = []
    for item in batch_results:
        item_data = item.get("data") if isinstance(item.get("data"), dict) else {}
        content = (item_data or {}).get("_draft_content") or {}
        # ADR-288: a sequence mixes types and decisions — an entry is named by
        # ITS type (the batch's only when it carries none) and a cancelled
        # entry keeps its row under the cancelled mark.
        own_type = item.get("draft_type")
        row_config = get_draft_display_config(str(own_type)) if own_type else None
        row_config = row_config or config
        status = item.get("status")
        mark = _STATUS_MARKS[
            "cancelled" if status == "cancelled" else "success" if status == "success" else "error"
        ]
        label = _item_label(row_config, content)
        if not label:
            logger.warning(
                "draft_result_format_empty_label",
                draft_type=own_type or draft_type,
                available_keys=sorted(content.keys()),
            )
            items.append(ResultItem(mark, str(item.get("message", "")), "", (), None))
            continue
        fields, excerpt = _item_fields(row_config, content, user_lang, user_tz)
        secondary = _item_secondary(row_config, content, user_lang, user_tz)
        items.append(ResultItem(mark, label, secondary, fields, excerpt))
    return tuple(items)


def _batch_headline(
    draft_type: str, config: DraftDisplayConfig | None, data: dict[str, Any], user_lang: Language
) -> str:
    """What a batch is headed with: the count, the noun and the verb agreed."""
    success_count = data.get("success_count", 0)
    total_count = data.get("total_count", 0)
    if config is not None:
        return compose_result_header(
            success_count=success_count,
            total_count=total_count,
            noun_key=config.noun_key,
            verb_past_key=config.verb_past_key,
            language=user_lang,
        )
    if draft_type == MIXED_BATCH_TYPE:
        # ADR-288: several types decided one at a time — counted as actions.
        return compose_result_header(
            success_count=success_count,
            total_count=total_count,
            noun_key="action",
            verb_past_key="executed",
            language=user_lang,
        )
    # Unknown draft type — the legacy bare "X/Y" header.
    return f"{success_count}/{total_count}"


def _describe_batch(
    status: str,
    draft_type: str,
    domain_emoji: str,
    config: DraftDisplayConfig | None,
    data: dict[str, Any],
) -> ResultSpec:
    """The description of a batch result: the count on top, one entry per item."""
    batch_results = data.get("batch_results", []) or []
    user_lang, user_tz = _batch_locale(batch_results)
    return ResultSpec(
        emoji=domain_emoji,
        mark=_STATUS_MARKS["success" if status == "success" else "partial_error"],
        headline=_batch_headline(draft_type, config, data, user_lang),
        separator=get_draft_preview_labels(user_lang)["separator"],
        lines=(),
        items=_describe_items(draft_type, config, batch_results, user_lang, user_tz),
    )


def _describe_single(
    domain_emoji: str,
    config: DraftDisplayConfig | None,
    message: str,
    data: dict[str, Any],
) -> ResultSpec:
    """The description of a single confirmed draft's success: its detail fields."""
    draft = data.get("_draft_content", {}) if isinstance(data, dict) else {}
    draft = draft if isinstance(draft, dict) else {}
    user_lang = normalize_language(draft.get("user_language") or "fr")
    user_tz = draft.get("user_timezone") or DEFAULT_USER_DISPLAY_TIMEZONE
    return ResultSpec(
        emoji=domain_emoji,
        mark=_STATUS_MARKS["success"],
        headline=message,
        separator=get_draft_preview_labels(user_lang)["separator"],
        lines=tuple(_detail_lines(config, draft, data, user_lang, user_tz)),
        items=(),
    )


def describe_execution_result(result: dict[str, Any] | None) -> ResultSpec | None:
    """Describe what a person reads once a confirmed draft has run (ADR-289).

    Args:
        result: Draft execution result dict with:
            - status: ``"success"`` | ``"cancelled"`` | ``"error"`` |
              ``"partial_error"``
            - message: Localized message
            - draft_type: Type of draft (contact, event, email, reminder_delete…)
            - action: Optional, e.g. ``"confirm_batch"``
            - data: Result data dict (may contain ``html_link``,
              ``_draft_content``, ``batch_results``, ``success_count``,
              ``total_count``)

    Returns:
        The description, or ``None`` when there is nothing to say — an empty
        payload, or a status nobody declared.
    """
    if not result:
        return None

    status = result.get("status", "unknown")
    message = result.get("message", "")
    draft_type = result.get("draft_type", "action")
    data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
    action = result.get("action", "")

    config = get_draft_display_config(draft_type)
    domain_emoji = config.emoji if config else ""

    if action == DraftAction.CONFIRM_BATCH.value and status in ("success", "partial_error"):
        return _describe_batch(status, draft_type, domain_emoji, config, data)

    if status == "success":
        return _describe_single(domain_emoji, config, message, data)

    if status == "partial_error":
        # Non-batch partial_error fallback (defensive — batch is handled above).
        counted = f"{data.get('success_count', 0)}/{data.get('total_count', 0)}"
        return ResultSpec(
            domain_emoji, _STATUS_MARKS["partial_error"], f"{message} ({counted})", " : ", (), ()
        )

    if status in ("cancelled", "error"):
        return ResultSpec(domain_emoji, _STATUS_MARKS[status], message, " : ", (), ())

    return None


def _item_markdown(item: ResultItem, separator: str) -> str:
    """One Markdown row per batch item: its outcome, its name, its key fields."""
    if not item.label:
        return plain_row(f"{item.mark} {item.label}".rstrip())
    parts = [f"{item.mark} **{item.label}**"]
    if item.secondary:
        parts.append(item.secondary)
    fields = " · ".join(f"{row.label}{separator}{readable(row.value)}" for row in item.fields)
    if fields:
        parts.append(fields)
    if item.excerpt:
        parts.append(item.excerpt)
    return plain_row(" — ".join(parts))


def _joined(headline: str, rows: list[str]) -> str:
    """Assemble a headline and its rows.

    Args:
        headline: The first line.
        rows: The Markdown rows, possibly empty.

    Returns:
        The headline alone, or the headline, one blank line, and the rows —
        never opening or closing on whitespace, since a block carries its own
        trailing newline.
    """
    if not rows:
        return headline
    return (headline + "\n\n" + "\n".join(rows)).rstrip()


def _to_markdown(spec: ResultSpec) -> str:
    """The lot-13 Markdown form of a described result."""
    headline = _headline(spec.emoji, spec.mark, spec.headline)
    rows = to_markdown_lines(spec.lines, spec.separator)
    rows.extend(_item_markdown(item, spec.separator) for item in spec.items)
    return _joined(headline, rows)


def render_execution_result(
    result: dict[str, Any] | None, surface: CardSurface = CardSurface.PLAIN
) -> str:
    """What a person reads once a confirmed draft has run.

    ADR-289: described once (:func:`describe_execution_result`), drawn per
    surface — Markdown for a surface that renders no markup, the chat's
    ``lia-card`` otherwise.

    Args:
        result: The draft execution result (see :func:`describe_execution_result`).
        surface: Where the result is drawn.

    Returns:
        Markdown or one line of HTML, with no leading or trailing whitespace.
        ``""`` when there is nothing to say.
    """
    spec = describe_execution_result(result)
    if spec is None:
        return ""
    if surface is CardSurface.CHAT:
        return to_html_result(spec)
    return _to_markdown(spec)
