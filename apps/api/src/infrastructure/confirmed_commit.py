"""A confirmed write publishes a receipt only after a known commit acknowledgment."""

import asyncio
from collections.abc import Awaitable
from typing import Protocol

from pydantic import JsonValue
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.preference_cas import PreferenceWriteReceipt


class CommitCompletionUnknown(RuntimeError):
    """The commit was sent; an automatic replay could repeat a completed effect."""


class CommitConfirmation(Protocol):
    @property
    def receipt(self) -> PreferenceWriteReceipt: ...
    def check(self) -> Awaitable[None]: ...


async def commit_confirmed_write(
    db: AsyncSession,
    confirmation: CommitConfirmation | None,
    values: dict[str, JsonValue],
    *,
    no_op: bool = False,
) -> None:
    if confirmation is not None:
        await confirmation.check()
    try:
        await db.commit()
    except SQLAlchemyError, asyncio.CancelledError:
        if confirmation is not None:
            raise CommitCompletionUnknown() from None
        raise
    if confirmation is not None:
        confirmation.receipt.committed = True
        confirmation.receipt.no_op = no_op
        confirmation.receipt.values = values
