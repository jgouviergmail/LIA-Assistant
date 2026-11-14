"""Joined, explicit account tree removal after durable producers have stopped."""

import asyncio
import shutil
from pathlib import Path
from uuid import UUID

from src.infrastructure.async_utils import finish_owned_task


def _remove_tree(owner: UUID, root: str) -> int:
    """Resolve the exact configured child before recursive I/O; failures propagate."""
    base = Path(root).resolve()
    child = base / str(owner)
    resolved = child.resolve()
    if child.is_symlink() or resolved.parent != base or resolved.name != str(owner):
        raise ValueError("Account directory escapes its owner boundary")
    if not child.exists():
        return 0
    shutil.rmtree(child)
    return 1


async def remove_account_tree(owner: UUID, root: str) -> int:
    """A cancelled request still joins its disk worker; failed deletion stays retryable."""
    return await finish_owned_task(
        asyncio.create_task(asyncio.to_thread(_remove_tree, owner, root))
    )
