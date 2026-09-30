"""How installing a skill proposed in the chat can be refused (ADR-327).

Every refusal names itself with a stable code (``detail.code``) the chat card
translates in the reader's language. The service raises
:class:`ProposalRefusal`; the router turns it into the API's answer through
:func:`refuse`, on the central taxonomy (rule #18) — kept in the domain because
``core/exceptions.py`` is size-frozen, like the skill library's raisers.
"""

from __future__ import annotations

from typing import Final, NoReturn

from fastapi import status

from src.core.exceptions import BaseAPIException

#: The proposal expired, was replaced by newer ones, or never was this account's.
NOT_FOUND: Final = "skill_proposal_not_found"
#: The skill it replaces changed since, or a skill of that name appeared.
STALE: Final = "skill_proposal_stale"
#: Another click is installing it right now.
BUSY: Final = "skill_proposal_busy"
#: The operator switched off skills written in the chat.
DISABLED: Final = "skill_proposal_disabled"
#: A system skill, or a skill installed from a library or a plugin, holds the name.
NAME_TAKEN: Final = "skill_proposal_name_taken"
#: The account holds as many skills as the instance allows.
QUOTA_REACHED: Final = "skill_proposal_quota_reached"
#: The package is no longer accepted by the import checks.
INVALID: Final = "skill_proposal_invalid"
#: The proposals could not be read (the cache is unreachable).
UNAVAILABLE: Final = "skill_proposal_unavailable"

#: What each refusal answers.
STATUSES: Final[dict[str, int]] = {
    NOT_FOUND: status.HTTP_404_NOT_FOUND,
    STALE: status.HTTP_409_CONFLICT,
    BUSY: status.HTTP_409_CONFLICT,
    DISABLED: status.HTTP_403_FORBIDDEN,
    NAME_TAKEN: status.HTTP_409_CONFLICT,
    QUOTA_REACHED: status.HTTP_409_CONFLICT,
    INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}


class ProposalRefusal(Exception):
    """A refusal to install a proposal, named by its code."""

    def __init__(self, code: str) -> None:
        """Name the refusal.

        Args:
            code: One of this module's codes.
        """
        super().__init__(code)
        self.code = code


def refuse(refusal: ProposalRefusal) -> NoReturn:
    """Answer a refusal with its stable code.

    Args:
        refusal: What the service refused.

    Raises:
        BaseAPIException: With ``detail = {"code": code}``.
    """
    status_code = STATUSES[refusal.code]
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": refusal.code},
        log_level="info" if status_code < 500 else "warning",
        log_event="skill_proposal_refused",
        refusal=refusal.code,
    )
