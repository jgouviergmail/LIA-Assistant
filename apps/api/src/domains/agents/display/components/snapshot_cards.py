"""Read-only snapshots for lights and workboard tickets."""

from abc import abstractmethod
from typing import Any

from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    render_card_top,
    render_chip,
    render_chip_row,
    wrap_with_response,
)
from src.domains.agents.display.components.card_content import render_linked_title
from src.domains.agents.display.components.light_details import (
    render_light_details,
    render_light_level,
)
from src.domains.agents.display.components.ticket_details import render_ticket_details
from src.domains.agents.display.components.ticket_fields import ticket_core_fields
from src.domains.agents.display.values import scalar_text


class SnapshotCard(BaseComponent):
    """The same title, wrapper and read-only contract for compact snapshots."""

    domain = ""
    icon_name = "description"
    tone = "blue"

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        title = scalar_text(data.get("title")) or scalar_text(data.get("name"))
        header = render_card_top(
            self.icon_name,
            self.tone,
            render_linked_title(title or V3Messages.get_no_title(ctx.language), None),
        )
        card = f'<div class="lia-card lia-{self.domain} {self._nested_class(ctx)}">{header}{self.body(data, ctx)}</div>'
        if not with_wrapper:
            return card
        return wrap_with_response(
            card_html=card,
            assistant_comment=assistant_comment,
            suggested_actions=suggested_actions,
            domain=self.domain,
            with_top_separator=is_first_item,
            with_bottom_separator=is_last_item,
        )

    @abstractmethod
    def body(self, data: dict[str, Any], ctx: RenderContext) -> str:
        raise NotImplementedError


class HueLightCard(SnapshotCard):
    domain = "hues"
    icon_name = "lightbulb"
    tone = "amber"

    def body(self, data: dict[str, Any], ctx: RenderContext) -> str:
        chips: list[str] = []
        state = data.get("is_on")
        if isinstance(state, bool):
            chips.append(
                render_chip(
                    card_label("light_on" if state else "light_off", ctx.language),
                    "amber" if state else "gray",
                )
            )
        brightness: object = data.get("brightness")
        if (
            isinstance(brightness, int | float)
            and not isinstance(brightness, bool)
            and 0 <= brightness <= 100
        ):
            chips.append(
                render_chip(f'{card_label("brightness", ctx.language)} {brightness:g}%', "amber")
            )
        # The current tool's room is an opaque resource id, not a room label.
        return (
            render_chip_row(" ".join(chips))
            + render_light_level(brightness, ctx)
            + render_light_details(data, ctx)
        )


class TicketCard(SnapshotCard):
    domain = "tickets"
    icon_name = "view_kanban"
    tone = "indigo"

    def body(self, data: dict[str, Any], ctx: RenderContext) -> str:
        return ticket_core_fields(data, ctx) + render_ticket_details(data, ctx)
