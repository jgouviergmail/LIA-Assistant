"""A missing SQL acknowledgement cannot authorize restoration of older live files."""

import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class SkillImportCompletionUnknown(RuntimeError):
    """The commit was attempted; preserve live bytes and never automatically replay."""


async def commit_skill_import(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError:
        # The database explicitly rejected the transaction; restoration is safe.
        raise
    except (Exception, asyncio.CancelledError) as error:
        raise SkillImportCompletionUnknown("Skill import commit acknowledgement unknown") from error
