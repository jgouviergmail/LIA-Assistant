"""A billed image is counted where Google bills it, on the turn that asked for it.

Cards carry proxy URLs — place photos, static maps, Street View — that the
browser fetches through this API with the deployment's key: every fetch is a
Google bill. The tools used to PRE-COUNT one call when they built the URL,
which is a claim rather than a count: the image may never load, it loads
again once the 24-hour browser cache expires, a photo carousel was never
counted past its first photo and the location map never at all (found
2026-09-19). So the proxy counts, at the instant Google bills, under its own
``TrackingContext`` — the one persistence path every family shares.

The euro still lands on the MESSAGE that asked: the URL carries the run id of
the turn that built it, SIGNED with the instance secret over (run id,
account). A bare run id in a URL would let any signed-in caller file a fetch
under another account's run — and, before that turn's own summary row
exists, CREATE the row under the wrong ``user_id``. An unsigned or foreign id
falls back to a fresh ``media_<hex>`` run: exact, attributed to the caller,
merely not joined to a message.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Final
from urllib.parse import quote
from uuid import UUID, uuid4

from src.core.config import settings
from src.core.context import current_tracker
from src.domains.chat.service import TrackingContext

#: Query parameters a media URL carries to join the turn that built it.
RUN_PARAM: Final = "run"
SIG_PARAM: Final = "sig"
#: Hex characters kept of the HMAC-SHA256 — 96 bits, plenty for a URL a
#: browser fetches, short enough not to bloat every card.
_SIGNATURE_LENGTH: Final = 24
#: Session id every media fetch files under (the summary row's own column).
_SESSION: Final = "media_proxy"


def _signature(run_id: str, user_id: UUID) -> str:
    """The instance-keyed signature binding a run id to an account."""
    payload = f"{run_id}:{user_id}".encode()
    return hmac.new(settings.secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()[
        :_SIGNATURE_LENGTH
    ]


def with_attribution(url: str) -> str:
    """Append the ambient turn's signed run id to a proxy URL.

    Outside any tracker (nothing to join) the URL is returned unchanged.

    Args:
        url: A site-relative proxy URL, with or without a query string.

    Returns:
        The URL carrying ``run`` and ``sig``, or the URL as given.
    """
    tracker = current_tracker.get()
    if tracker is None:
        return url
    joiner = "&" if "?" in url else "?"
    signature = _signature(tracker.run_id, tracker.user_id)
    return f"{url}{joiner}{RUN_PARAM}={quote(tracker.run_id, safe='')}&{SIG_PARAM}={signature}"


def attributed_run_id(run: str | None, sig: str | None, user_id: UUID) -> str:
    """The run id a fetch files under: the signed turn's, else a fresh one.

    Args:
        run: The ``run`` query parameter, if any.
        sig: The ``sig`` query parameter, if any.
        user_id: The authenticated caller — the only account a fetch may bill.

    Returns:
        ``run`` when its signature matches this account, else ``media_<hex>``.
    """
    if run and sig and hmac.compare_digest(sig, _signature(run, user_id)):
        return run
    return f"media_{uuid4().hex[:12]}"


def media_spend_context(run: str | None, sig: str | None, user_id: UUID) -> TrackingContext:
    """The accounting a proxy fetch runs under (an ``ACCOUNTING_DOORS`` entry).

    Args:
        run: The ``run`` query parameter, if any.
        sig: The ``sig`` query parameter, if any.
        user_id: The authenticated caller.

    Returns:
        A tracker on the attributed run id; what the fetch records is
        persisted when it exits.
    """
    return TrackingContext(attributed_run_id(run, sig, user_id), user_id, _SESSION, None)


__all__ = [
    "RUN_PARAM",
    "SIG_PARAM",
    "attributed_run_id",
    "media_spend_context",
    "with_attribution",
]
