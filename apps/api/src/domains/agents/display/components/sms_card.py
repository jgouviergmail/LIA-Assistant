"""Literal SMS text and one validated, localized link to the personal archive."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from src.core.i18n import resolve_language
from src.core.i18n_sms import SMS_CARD_LABELS
from src.core.i18n_types import frontend_language_code
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    format_date,
    render_card_top,
    wrap_with_response,
)


class SmsCardData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: UUID
    sender: str
    display_name: str
    body: str
    received_at: datetime
    date_kind: str
    next_body_offset: int | None = None


class SmsCard(BaseComponent):
    def render(
        self,
        data: dict[str, object],
        ctx: RenderContext,
        *,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        try:
            message = SmsCardData.model_validate(data)
        except ValidationError:
            return ""
        language = resolve_language(ctx.language)
        labels = SMS_CARD_LABELS[language]
        route_language = frontend_language_code(language)
        url = f"/{route_language}/dashboard/sms?message={message.id}"
        title = f'<a href="{url}">{escape_html(message.display_name)}</a>'
        header = render_card_top("sms", "blue", title)
        raw = (
            f'<div class="lia-secondary">{escape_html(message.sender)}</div>'
            if message.sender != message.display_name
            else ""
        )
        stamp = escape_html(
            format_date(message.received_at, language, ctx.timezone, "short", include_time=True)
        )
        date_note = (
            f' · {escape_html(labels["provided_time"])}' if message.date_kind != "received" else ""
        )
        more = (
            f'<div class="lia-secondary">{escape_html(labels["more"])}</div>'
            if message.next_body_offset is not None
            else ""
        )
        body = escape_html(message.body).replace("\n", "<br>")
        card = f'<div class="lia-card lia-sms">{header}{raw}<div class="lia-secondary">{stamp}{date_note}</div><div class="lia-card-content">{body}</div>{more}</div>'
        return wrap_with_response(
            card_html=card,
            domain="sms_messages",
            with_top_separator=is_first_item,
            with_bottom_separator=is_last_item,
        )
