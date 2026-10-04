"""Pure collection presentation: disclosure preserves selection, failure is local."""

from collections.abc import Sequence
from html import escape
from typing import TYPE_CHECKING

from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.icons import Icons, icon
from src.domains.agents.display.values import first_present, scalar_text
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.display.components.base import BaseComponent, RenderContext

logger = get_logger(__name__)


def _unavailable(language: str, item: object) -> str:
    label = escape(card_label("unavailable", language))
    identity = (
        scalar_text(first_present(item, "subject", "summary", "name", "title"))
        if isinstance(item, dict)
        else ""
    )
    title = (
        f'<p class="lia-card__title">{icon(Icons.WARNING)} {escape(identity)}</p>'
        if identity
        else ""
    )
    return (
        '<div class="lia-response-wrapper" data-card-version="2">'
        '<div class="lia-card lia-card--unavailable" data-render-state="unavailable">'
        f'{title}<p class="lia-card__meta">{label}</p></div></div>'
    )


def render_collection_item(
    component: BaseComponent,
    item: object,
    ctx: RenderContext,
    *,
    first: bool = False,
    last: bool = False,
) -> str:
    """Rendering is pure; never retry a provider or disclose malformed raw data."""
    if not isinstance(item, dict):
        return _unavailable(ctx.language, item)
    try:
        html = component.render(item, ctx, is_first_item=first, is_last_item=last)
        reference = item.get("_lia_card_ref")
        return (
            f'<div class="lia-card-binding" data-card-ref="{escape(reference)}">{html}</div>'
            if html and isinstance(reference, str)
            else html
        )
    except (AttributeError, TypeError, ValueError, OverflowError, KeyError) as error:
        logger.warning(
            "card_item_render_failed",
            component=type(component).__name__,
            error_type=type(error).__name__,
        )
        return _unavailable(ctx.language, item)


def fold_card_collection(cards: Sequence[str], limit: int, language: str) -> str:
    """The limit controls the initial view, never the selected result set."""
    visible = max(1, limit)
    initial = "\n".join(cards[:visible])
    remaining = cards[visible:]
    if not remaining:
        return initial
    label = escape(V3Messages.get_see_more(language))
    return (
        f'{initial}<details class="lia-card-collection" data-card-version="2">'
        f"<summary>{label} <span>({len(remaining)})</span></summary>"
        f'<div class="lia-card-collection__content">{"\n".join(remaining)}</div></details>'
    )
