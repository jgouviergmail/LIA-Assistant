"""Optional original import boundaries: before live writes and after known commit."""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.models import Skill

BeforeSkillSwap = Callable[[AsyncSession], Awaitable[None]]
AfterSkillCommit = Callable[[Skill], None]
