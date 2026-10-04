"""Calendar identity and access, kept distinct from dated events."""

from typing import Any

from src.core.i18n_cards import card_label, is_calendar_access
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    render_card_top,
    render_chip,
    render_chip_row,
    render_d_item,
    wrap_with_response,
)
from src.domains.agents.display.components.calendar_details import render_calendar_details
from src.domains.agents.display.icons import Icons


class CalendarCard(BaseComponent):
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
        title = (
            data.get("summaryOverride")
            or data.get("summary")
            or data.get("name")
            or V3Messages.get_no_title(ctx.language)
        )
        header = render_card_top(
            Icons.CALENDAR,
            "purple",
            f'<span class="lia-card-top__title">{escape_html(title)}</span>',
        )
        chips: list[str] = []
        if data.get("primary") is True:
            chips.append(render_chip(card_label("primary", ctx.language), "purple", "star"))
        role = data.get("access_role")
        if is_calendar_access(role):
            chips.append(render_chip(card_label(role, ctx.language), "purple", "shield"))
        zone = data.get("time_zone") or data.get("timeZone")
        zone_html = (
            render_d_item(
                Icons.SCHEDULE,
                f'{escape_html(card_label("timezone", ctx.language))}{label_separator(ctx.language)}{escape_html(zone)}',
            )
            if zone
            else ""
        )
        description = (
            render_d_item(Icons.NOTE, escape_html(data["description"]))
            if data.get("description")
            else ""
        )
        markup = f'<div class="lia-card lia-calendar {self._nested_class(ctx)}">{header}{render_chip_row(" ".join(chips))}{zone_html}{description}{render_calendar_details(data, ctx)}</div>'
        if not with_wrapper:
            return markup
        return wrap_with_response(
            card_html=markup,
            assistant_comment=assistant_comment,
            suggested_actions=suggested_actions,
            domain="calendars",
            with_top_separator=is_first_item,
            with_bottom_separator=is_last_item,
        )
