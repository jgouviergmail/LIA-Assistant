"""How the ntfy settings refuse (ADR-391).

Every refusal names itself with a stable code (``detail.code``) the web app translates in the
person's language (``ntfy-labels.ts``, held equal by ``test_ntfy_web_vocabulary.py``); a figure
the reader needs (the ceiling) travels beside it. What the person typed is never echoed: a topic
is a password and a token a credential. Built on the central taxonomy (rule #18: never a raw
``HTTPException``) and kept in the domain, like the e-mail sharing's raisers, because
``core/exceptions.py`` is size-frozen.
"""

from __future__ import annotations

from typing import Any, Final, NoReturn

from fastapi import status

from src.core.exceptions import BaseAPIException

#: The instance offers no ntfy server of its own.
INSTANCE_UNAVAILABLE: Final = "ntfy_instance_unavailable"
#: The operator keeps the instance's people on its own server.
CUSTOM_SERVERS_DISABLED: Final = "ntfy_custom_servers_disabled"
#: A person's server is reached over TLS only.
SERVER_URL_NOT_HTTPS: Final = "ntfy_server_url_not_https"
#: No address can be read from what was typed (or it carries what a server address must not).
SERVER_URL_INVALID: Final = "ntfy_server_url_invalid"
#: The address names a private network LIA must not reach for a person.
SERVER_URL_REFUSED: Final = "ntfy_server_url_refused"
#: ntfy would refuse the topic.
TOPIC_INVALID: Final = "ntfy_topic_invalid"
#: Not an access token ntfy issues.
TOKEN_INVALID: Final = "ntfy_token_invalid"
#: The account holds as many subscriptions as it may (``max`` beside the code).
SUBSCRIPTION_LIMIT: Final = "ntfy_subscription_limit"
#: The subscription's secrets no longer decrypt: it can only be removed.
SUBSCRIPTION_UNREADABLE: Final = "ntfy_subscription_unreadable"

#: What each refusal answers.
_STATUS: Final[dict[str, int]] = {
    INSTANCE_UNAVAILABLE: status.HTTP_409_CONFLICT,
    CUSTOM_SERVERS_DISABLED: status.HTTP_409_CONFLICT,
    SERVER_URL_NOT_HTTPS: status.HTTP_422_UNPROCESSABLE_CONTENT,
    SERVER_URL_INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    SERVER_URL_REFUSED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    TOPIC_INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    TOKEN_INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    SUBSCRIPTION_LIMIT: status.HTTP_409_CONFLICT,
    SUBSCRIPTION_UNREADABLE: status.HTTP_409_CONFLICT,
}

#: Every refusal code, in the order the web translates them.
REFUSAL_CODES: Final = tuple(_STATUS)


def refuse(code: str, **facts: Any) -> NoReturn:
    """Refuse a change of the ntfy settings with its stable code.

    Args:
        code: One of this module's codes.
        **facts: Figures the reader needs beside the code (``max``) — never what was typed.

    Raises:
        BaseAPIException: With ``detail = {"code": code, **facts}``.
    """
    raise BaseAPIException(
        status_code=_STATUS[code],
        detail={"code": code, **facts},
        log_level="info",
        log_event="ntfy_refused",
        refusal=code,
    )


__all__ = [
    "CUSTOM_SERVERS_DISABLED",
    "INSTANCE_UNAVAILABLE",
    "REFUSAL_CODES",
    "SERVER_URL_INVALID",
    "SERVER_URL_NOT_HTTPS",
    "SERVER_URL_REFUSED",
    "SUBSCRIPTION_LIMIT",
    "SUBSCRIPTION_UNREADABLE",
    "TOKEN_INVALID",
    "TOPIC_INVALID",
    "refuse",
]
