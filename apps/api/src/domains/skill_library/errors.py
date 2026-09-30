"""How the skill library can refuse (ADR-327).

Every refusal names itself with a stable code (``detail.code``) the web app
translates in the reader's language; a fact the reader needs (the audit's
risk, when GitHub's limit lifts, the largest skill accepted) travels beside it.
The domain raises :class:`LibraryRefusal`; the router turns it into the API's
answer through :func:`refuse`, on the central taxonomy (rule #18: never a raw
``HTTPException``) — kept in the domain because ``core/exceptions.py`` is
size-frozen, like the radio's and the e-mail share's raisers.
"""

from __future__ import annotations

from typing import Any, Final, NoReturn

from fastapi import status

from src.core.exceptions import BaseAPIException

#: The search text is shorter or longer than the published bounds.
QUERY_INVALID: Final = "skill_library_query_invalid"
#: The repository, address or folder given does not read as one.
SOURCE_INVALID: Final = "skill_library_source_invalid"
#: The portal lists this skill at an origin LIA does not read (not GitHub).
ORIGIN_UNSUPPORTED: Final = "skill_library_origin_unsupported"
#: The repository, the ref or the skill folder does not exist.
NOT_FOUND: Final = "skill_library_not_found"
#: The repository names several folders the skill could be; one must be chosen.
AMBIGUOUS: Final = "skill_library_ambiguous"
#: The portal or GitHub could not be read.
UNREACHABLE: Final = "skill_library_unreachable"
#: GitHub's request allowance is spent; ``reset_at`` says when it comes back.
RATE_LIMITED: Final = "skill_library_rate_limited"
#: The repository or the skill is larger than what an install accepts.
TOO_LARGE: Final = "skill_library_too_large"
#: An audit rated the skill at or above the instance's refusal level.
AUDIT_BLOCKED: Final = "skill_library_audit_blocked"
#: A skill of that name exists and was not installed from this folder.
NAME_TAKEN: Final = "skill_library_name_taken"
#: This skill is already installed from this folder: it is updated, not installed.
ALREADY_INSTALLED: Final = "skill_library_already_installed"
#: The skill was not installed from a library.
NOT_INSTALLED: Final = "skill_library_not_installed"
#: The new version carries another name: it is a new skill, installed as one.
RENAMED: Final = "skill_library_renamed"
#: The account holds as many skills as the instance allows.
QUOTA_REACHED: Final = "skill_library_quota_reached"
#: The skill's files were read but its manifest was refused by the import checks.
INVALID_SKILL: Final = "skill_library_invalid_skill"

#: What each refusal answers.
STATUSES: Final[dict[str, int]] = {
    QUERY_INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    SOURCE_INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ORIGIN_UNSUPPORTED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NOT_FOUND: status.HTTP_404_NOT_FOUND,
    AMBIGUOUS: status.HTTP_409_CONFLICT,
    UNREACHABLE: status.HTTP_502_BAD_GATEWAY,
    RATE_LIMITED: status.HTTP_503_SERVICE_UNAVAILABLE,
    TOO_LARGE: status.HTTP_422_UNPROCESSABLE_CONTENT,
    AUDIT_BLOCKED: status.HTTP_409_CONFLICT,
    NAME_TAKEN: status.HTTP_409_CONFLICT,
    ALREADY_INSTALLED: status.HTTP_409_CONFLICT,
    NOT_INSTALLED: status.HTTP_404_NOT_FOUND,
    RENAMED: status.HTTP_409_CONFLICT,
    QUOTA_REACHED: status.HTTP_409_CONFLICT,
    INVALID_SKILL: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


class LibraryRefusal(Exception):
    """A refusal of the library, with the facts its sentence quotes."""

    def __init__(self, code: str, **detail: Any) -> None:
        """Name the refusal.

        Args:
            code: One of this module's codes.
            **detail: Facts beside the code (``risk``, ``reset_at``, ``max_files``...).
        """
        super().__init__(code)
        self.code = code
        self.detail = {k: v for k, v in detail.items() if v is not None}


def refuse(refusal: LibraryRefusal) -> NoReturn:
    """Answer a refusal with its stable code.

    Args:
        refusal: What the domain refused.

    Raises:
        BaseAPIException: With ``detail = {"code": code, **facts}``.
    """
    status_code = STATUSES[refusal.code]
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": refusal.code, **refusal.detail},
        log_level="info" if status_code < 500 else "warning",
        log_event="skill_library_refused",
        refusal=refusal.code,
    )
