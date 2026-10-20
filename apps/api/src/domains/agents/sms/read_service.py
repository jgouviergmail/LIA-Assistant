"""Assistant-only adapter; every operation uses the common fresh source gate."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.sms.projection import SmsToolPage, project_page
from src.domains.agents.sms.schemas import (
    SMS_TOOL_TOKEN_BUDGET,
    SmsGetRequest,
    SmsListRequest,
    SmsSearchRequest,
)
from src.domains.sms.facade import SmsFacade
from src.domains.sms.read_schemas import SmsPage, SmsQuery
from src.domains.sms.reads import require_read


class SmsToolReader:
    def __init__(self, db: AsyncSession, *, budget: int = SMS_TOOL_TOKEN_BUDGET) -> None:
        self.db = db
        self.facade = SmsFacade(db)
        self.budget = min(budget, SMS_TOOL_TOKEN_BUDGET)

    async def list(self, owner: UUID, request: SmsListRequest) -> SmsToolPage:
        return await self._list(owner, SmsQuery.model_validate(request.model_dump()))

    async def search(self, owner: UUID, request: SmsSearchRequest) -> SmsToolPage:
        return await self._list(owner, SmsQuery.model_validate(request.model_dump()))

    async def _list(self, owner: UUID, query: SmsQuery) -> SmsToolPage:
        page = await self.facade.list(owner, query, assistant=True)
        return project_page(page, owner=owner, budget=self.budget - 128 * len(page.items))

    async def get(self, owner: UUID, request: SmsGetRequest) -> SmsToolPage:
        item = await self.facade.get(owner, request.message_id, assistant=True)
        actor = await require_read(self.db, owner, assistant=True)
        page = SmsPage(
            items=[item], total=1, as_of=datetime.now(UTC), revision=actor.extraction_revision or 0
        )
        return project_page(
            page, owner=owner, body_offset=request.body_offset, budget=self.budget - 128
        )
