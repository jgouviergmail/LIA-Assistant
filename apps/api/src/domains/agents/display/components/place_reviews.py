"""Complete reviews, with graceful handling of incomplete provider fields."""

from collections.abc import Mapping

from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_date,
    render_collapsible,
    render_review,
)
from src.domains.agents.display.components.card_content import render_linked_title
from src.domains.agents.display.components.place_dates import provider_date
from src.domains.agents.display.urls import safe_image_url
from src.domains.agents.display.values import rating_value


def review_rating(value: object) -> int:
    """A malformed/out-of-range rating must neither crash nor allocate unbounded stars."""
    number = rating_value(value)
    return int(number) if number is not None else 0


def render_place_reviews(value: object, ctx: RenderContext | None = None) -> list[str]:
    """Accept raw and normalized reviews without discarding valid unattributed text."""
    if not isinstance(value, list):
        return []
    context = ctx or RenderContext()
    return [
        markup
        for review in value
        if isinstance(review, dict)
        if (markup := _render_place_review(review, context))
    ]


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _render_place_review(review: Mapping[str, object], ctx: RenderContext) -> str:
    author_name, header = _review_author(review)
    text = review.get("text")
    body = _text(text.get("text")) if isinstance(text, dict) else _text(text)
    if not body and rating_value(review.get("rating")) is None:
        return ""
    relative_time = _text(review.get("relative_time")) or _text(
        review.get("relativePublishTimeDescription")
    )
    published = _text(review.get("publish_time")) or _text(review.get("publishTime"))
    date = format_date(published, ctx.language, ctx.timezone) if published else ""
    time = " · ".join(part for part in (relative_time, date) if part)
    return render_review(
        author_name,
        time,
        review_rating(review.get("rating")),
        body,
        author_html=header,
        footer_html=_review_context(review, body, ctx),
    )


def _review_author(review: Mapping[str, object]) -> tuple[str, str]:
    author = review.get("authorAttribution")
    author_name = _text(author.get("displayName")) if isinstance(author, dict) else ""
    author_name = author_name or _text(review.get("author_name")) or _text(review.get("author"))
    profile = _text(review.get("author_url")) or (
        _text(author.get("uri")) if isinstance(author, dict) else ""
    )
    avatar = _text(review.get("author_photo_url")) or (
        _text(author.get("photoUri")) if isinstance(author, dict) else ""
    )
    header = render_linked_title(
        author_name, profile if safe_image_url(profile) else "", class_name="lia-review__author"
    )
    portrait = safe_image_url(avatar)
    if portrait:
        header = f'<img class="lia-review__avatar" src="{portrait}" alt="" loading="lazy">{header}'
    return author_name, header


def _review_context(review: Mapping[str, object], body: str, ctx: RenderContext) -> str:
    links = _review_links(review, ctx)
    score = rating_value(review.get("rating"))
    numeric = f'<span class="lia-review__score">{score:g}/5</span>' if score is not None else ""
    visit = provider_date(review.get("visit_date", review.get("visitDate")), ctx)
    visit_text = (
        f'<span>{escape_html(card_label("visit", ctx.language))} · {escape_html(visit)}</span>'
        if visit
        else ""
    )
    footer = f'<div class="lia-review__source">{numeric}{visit_text}{links}</div>'
    original = review.get("originalText")
    text = _text(review.get("original_text")) or (
        _text(original.get("text")) if isinstance(original, dict) else ""
    )
    if text and text != body:
        footer += render_collapsible(
            card_label("original_text", ctx.language),
            f'<div class="lia-card-text">{escape_html(text)}</div>',
            with_separator=False,
        )
    return footer


def _review_links(review: Mapping[str, object], ctx: RenderContext) -> str:
    links: list[str] = []
    sources = (
        (
            _text(review.get("source_url")) or _text(review.get("googleMapsUri")),
            V3Messages.get_open_in_maps(ctx.language),
        ),
        (
            _text(review.get("report_url")) or _text(review.get("flagContentUri")),
            card_label("report_content", ctx.language),
        ),
    )
    for value, label in sources:
        target = safe_image_url(value)
        if target:
            links.append(
                f'<a href="{target}" target="_blank" rel="noopener noreferrer">{escape_html(label)}</a>'
            )
    return "".join(links)
