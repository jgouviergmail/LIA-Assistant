"""Safe card content shared by the domain renderers."""

from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    render_collapsible,
    safe_url,
)
from src.domains.agents.display.components.folded_synthesis import split_lead
from src.domains.agents.display.values import scalar_text


def render_linked_title(
    title: object, url: object, *, class_name: str = "lia-card-top__title"
) -> str:
    """A title is a link only when the provider supplied a safe destination."""
    text = escape_html(scalar_text(title))
    target = safe_url(scalar_text(url))
    css_class = escape_html(class_name)
    if target:
        return (
            f'<a class="{css_class}" href="{target}" '
            f'target="_blank" rel="noopener noreferrer">{text}</a>'
        )
    return f'<span class="{css_class}">{text}</span>'


def render_text_content(text: object) -> str:
    """Escaped complete text with its original paragraphs and line breaks."""
    value = scalar_text(text)
    return f'<div class="lia-card-text">{escape_html(value)}</div>' if value else ""


def render_details(content: str, ctx: RenderContext) -> str:
    """The shared native detail affordance; absence draws no empty control."""
    return (
        render_collapsible(
            trigger_text=V3Messages.get_see_more(ctx.language),
            content_html=content,
            with_separator=False,
        )
        if content
        else ""
    )


def render_folded_text(text: object, ctx: RenderContext, *, preview_chars: int) -> str:
    """Lossless plain text preview using the existing paragraph/sentence policy."""
    lead, rest = split_lead(scalar_text(text), preview_chars=preview_chars)
    return render_text_content(lead) + render_details(render_text_content(rest), ctx)


def render_availability_rows(values: list[tuple[str, bool]], language: str) -> str:
    """Known Yes/No with text and an icon; absence never becomes a negative fact."""
    rows: list[str] = []
    for label, available in values:
        state = "true" if available else "false"
        symbol = "check_circle" if available else "do_not_disturb_on"
        answer = escape_html(card_label("yes" if available else "no", language))
        rows.append(
            f'<div class="lia-availability-row"><dt>{escape_html(label)}</dt><dd><span data-availability="{state}" class="lia-availability"><span class="material-symbols-outlined" aria-hidden="true">{symbol}</span>{answer}</span></dd></div>'
        )
    return f'<dl class="lia-availability-list">{"".join(rows)}</dl>' if rows else ""
