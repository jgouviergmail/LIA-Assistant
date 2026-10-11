"""Withdraw an owned approval without changing any application setting."""

from sqlalchemy.exc import SQLAlchemyError

from src.domains.agents.application.command_repository import cancel_command
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def withdraw_application_draft(draft_id: str) -> bool:
    context = runtime_context_if_running()
    if context is None:
        return False
    try:
        async with get_db_context() as db:
            return await cancel_command(db, draft_id, context.user_id)
    except SQLAlchemyError:
        return False
