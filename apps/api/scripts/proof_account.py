"""The account a measurement runs on: the PROOF account, and nothing else.

A paid measurement bills a real account — its usage, its ceilings, its
registers — and some write into it. It runs on the proof account alone: an
e-mail under ``proof-lia.dev`` whose id starts with the known prefix. Any other
account, an owner's above all, is refused rather than billed or written.

One door for every measurement script (``journals/measure_portrait.py``,
``document_generation/measure_writer.py``): a second spelling of the rule is
the one that drifts.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User

#: The domain every proof account's e-mail is under.
PROOF_DOMAIN = "proof-lia.dev"
#: The id prefix of THE proof account, among those of the domain.
PROOF_ID_PREFIX = "d7db1a08"


async def proof_user(db: AsyncSession) -> User:
    """The proof account, and nothing else: an owner's row is refused.

    Args:
        db: A session on the database the measurement runs against.

    Returns:
        The proof account's row.

    Raises:
        SystemExit: When no account matches — the measurement does not run.
    """
    rows = (await db.execute(select(User).where(User.email.like(f"%@{PROOF_DOMAIN}")))).scalars()
    user = next((row for row in rows if str(row.id).startswith(PROOF_ID_PREFIX)), None)
    if user is None:
        raise SystemExit(
            f"No proof account (e-mail under {PROOF_DOMAIN}, id {PROOF_ID_PREFIX}…) — refusing"
        )
    return user


__all__ = ["PROOF_DOMAIN", "PROOF_ID_PREFIX", "proof_user"]
