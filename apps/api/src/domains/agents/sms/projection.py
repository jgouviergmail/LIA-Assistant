"""Whole metadata and exact Unicode body pages under a local token budget."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.agents.sms.schemas import SMS_TOOL_TOKEN_BUDGET
from src.domains.agents.utils.token_utils import count_external_tokens
from src.domains.sms.read_schemas import SmsPage, SmsView


class SmsToolItem(SmsView):
    model_config = ConfigDict(frozen=True, extra="forbid")
    owner_id: UUID
    revision: int
    body_offset: int
    next_body_offset: int | None = None


class SmsToolPage(BaseModel):
    owner_id: UUID
    model_config = ConfigDict(frozen=True, extra="forbid")
    sms_messages: list[SmsToolItem]
    total: int
    as_of: datetime
    revision: int
    next_cursor: str | None = None


projection_tokens = count_external_tokens


def _chunk(item: SmsToolItem, body: str, start: int, size: int) -> SmsToolItem:
    end = start + size
    return item.model_copy(
        update={"body": body[start:end], "next_body_offset": end if end < len(body) else None}
    )


def _fit_body(page: SmsToolPage, index: int, body: str, start: int, budget: int) -> SmsToolPage:
    item = page.sms_messages[index]

    def with_size(size: int) -> SmsToolPage:
        items = list(page.sms_messages)
        items[index] = _chunk(item, body, start, size)
        return page.model_copy(update={"sms_messages": items})

    full = with_size(len(body) - start)
    if projection_tokens(full.model_dump_json()) <= budget:
        return full
    low, high = 0, len(body) - start
    while low < high:
        middle = (low + high + 1) // 2
        if projection_tokens(with_size(middle).model_dump_json()) <= budget:
            low = middle
        else:
            high = middle - 1
    if not low and start < len(body):
        raise ValueError("SMS_PROJECTION_BUDGET_USE_LIMIT_ONE")
    return with_size(low)


def project_page(
    source: SmsPage, *, owner: UUID, body_offset: int = 0, budget: int = SMS_TOOL_TOKEN_BUDGET
) -> SmsToolPage:
    if body_offset < 0 or (body_offset and len(source.items) != 1):
        raise ValueError("INVALID_BODY_OFFSET")
    items = []
    for item in source.items:
        if body_offset > len(item.body):
            raise ValueError("INVALID_BODY_OFFSET")
        items.append(
            SmsToolItem(
                **{**item.model_dump(), "body": ""},
                owner_id=owner,
                revision=source.revision,
                body_offset=body_offset,
                next_body_offset=body_offset if item.body[body_offset:] else None,
            )
        )
    page = SmsToolPage(
        owner_id=owner,
        sms_messages=items,
        total=source.total,
        as_of=source.as_of,
        revision=source.revision,
        next_cursor=source.next_cursor,
    )
    if projection_tokens(page.model_dump_json()) > budget:
        raise ValueError("SMS_PROJECTION_BUDGET_USE_LIMIT_ONE")
    for index, source_item in enumerate(source.items):
        used = projection_tokens(page.model_dump_json())
        remaining = len(source.items) - index
        item_budget = used + (budget - used) // remaining
        page = _fit_body(page, index, source_item.body, body_offset, item_budget)
    return page
