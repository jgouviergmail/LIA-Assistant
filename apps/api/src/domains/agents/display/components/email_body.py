"""Safe complete email reading, retaining the configured initial preview."""

from src.core.config import settings
from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    format_email_body,
    markdown_links_to_html,
    render_collapsible,
    render_desc_block,
)


def _body_markup(text: str, ctx: RenderContext) -> str:
    label = V3Messages.get_link(ctx.language)
    threshold = settings.emails_url_shorten_threshold
    return "<br>".join(markdown_links_to_html(line, threshold, label) for line in text.split("\n"))


def render_email_body(body: str, ctx: RenderContext) -> str:
    """Long content expands locally; the provider is never fetched to reveal it."""
    preview, truncated = format_email_body(
        body,
        max_length=settings.emails_body_max_length,
        preserve_links=True,
    )
    content = render_desc_block(_body_markup(preview, ctx), with_border=False)
    if not truncated:
        return content
    full_text, _ = format_email_body(body, max_length=None, preserve_links=True)
    return content + render_collapsible(
        trigger_text=card_label("full_message", ctx.language),
        content_html=render_desc_block(_body_markup(full_text, ctx), with_border=False),
        with_separator=False,
    )
