"""Is an embedding failure worth another attempt? One answer, one place.

Two retry loops used to decide this independently — the RAG system indexer,
which classified STRUCTURALLY, and the embedding client, which did not classify
at all because it could not retry. Two classifiers on one provider is one that
drifts, and the drift is silent: a failure the indexer retries and the client
gives up on looks like two different providers.

The structural reading comes first, and the reason is written in the indexer
that pioneered it: **matching text inside an exception message is how a
provider's wording change silently turns a retry into a hard failure.** The
status code the SDK sets on its errors survives rewording; the sentence does
not.

The message is still read, but only as a fallback and only when no code was
found anywhere in the chain. Measured on 2026-09-01, the failure that reached
the callers was a ``GoogleGenerativeAIError`` whose payload named the quota
while the wrapper itself carried no ``code`` — dropping the fallback would have
made the real production incident unretryable.
"""

from __future__ import annotations

import re

from src.core.constants import EMBEDDING_RETRYABLE_STATUS_CODES

#: Phrases that identify a transient provider failure when — and only when — no
#: status code could be read from the exception chain. Kept short: every entry
#: here is a guess about someone else's wording.
_TRANSIENT_TEXT_MARKERS: tuple[str, ...] = (
    "resource_exhausted",
    "quota exceeded",
    "internal error",
    "unavailable",
    "deadline exceeded",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
)

#: The same status codes as the structural reading, matched on WORD BOUNDARIES.
#:
#: DERIVED from the set above, never restated: written by hand it had already
#: drifted — 408 was in the structural set and missing from the prose one, so a
#: timeout reported with a code was retried and the identical timeout reported
#: without one was not.
#:
#: The boundaries are not decoration. As plain substrings these are a trap:
#: "500" occurs inside "1500", so a permanent 400 whose message reads "input
#: token count 1500 exceeds the maximum" would be classified transient and
#: retried until the budget ran out — a hard failure turned into a slow one.
_TRANSIENT_STATUS_RE = re.compile(
    r"\b(" + "|".join(str(code) for code in sorted(EMBEDDING_RETRYABLE_STATUS_CODES)) + r")\b"
)


def embedding_retry_reason(exc: BaseException) -> str | None:
    """Why this embedding failure deserves another attempt, or None.

    Walks ``__cause__`` because langchain re-raises every provider failure
    wrapped in ``GoogleGenerativeAIError``, so the code that matters is rarely
    on the exception the caller catches.

    Args:
        exc: Exception raised by an embedding call.

    Returns:
        A short reason label for logging, or None when the failure is permanent
        — a malformed input or an invalid key fails identically every time, and
        retrying only delays the caller learning it.
    """
    seen: set[int] = set()
    saw_status_code = False
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, int):
            saw_status_code = True
            if code in EMBEDDING_RETRYABLE_STATUS_CODES:
                return f"http_{code}"
        if isinstance(current, TimeoutError | ConnectionError):
            return type(current).__name__
        current = current.__cause__

    if saw_status_code:
        # The provider TOLD us, and it said permanent. Reading the prose after
        # that would let a number quoted in a sentence — "gave up after 429
        # attempts" — overturn the fact.
        return None

    # No code anywhere in the chain, so the message is all there is. See the
    # module docstring: the production incident arrived exactly like this.
    #
    # Only the OUTERMOST message is read, deliberately. The structural walk goes
    # deep because a status code is a fact; this heuristic stays shallow because
    # broadening a guess multiplies its false positives, and a false positive
    # here retries something that will never succeed.
    text = str(exc).lower()
    status = _TRANSIENT_STATUS_RE.search(text)
    if status is not None:
        return f"message:http_{status.group(1)}"
    for marker in _TRANSIENT_TEXT_MARKERS:
        if marker in text:
            return f"message:{marker}"
    return None


def is_transient_embedding_error(exc: BaseException) -> bool:
    """Whether an embedding failure should be retried."""
    return embedding_retry_reason(exc) is not None


#: The ``@type`` of the detail that carries the provider's own delay
#: (``google.rpc.RetryInfo``), matched on its suffix: the host part is a URL.
_RETRY_INFO_TYPE = "google.rpc.RetryInfo"
#: A protobuf ``Duration`` in its JSON form: seconds, an optional fraction, ``s``.
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)s")


def provider_retry_delay_seconds(exc: BaseException) -> float | None:
    """The wait the provider itself asks for before another attempt, or None.

    A quota refusal says when to come back: ``error.details[]`` of the response
    carries a ``RetryInfo`` whose ``retryDelay`` is a duration (``"40s"``). The
    SDK keeps the response on its error (``details``) and langchain chains that
    error as the cause of its own, so the chain is walked like the status code
    is.

    Structural or nothing, with no fallback on the sentence: the wording of a
    refusal is the provider's to change, and an unreadable delay must leave the
    caller its own backoff rather than a guess. The structured value is rounded
    DOWN to whole seconds — measured on 2026-11-09, ``40s`` beside a message
    reading « retry in 40.38414246s » — so a caller that waits it adds a margin.

    Args:
        exc: Exception raised by an embedding call.

    Returns:
        The delay in seconds, or None when the provider named none.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        delay = _retry_info_delay(getattr(current, "details", None))
        if delay is not None:
            return delay
        current = current.__cause__
    return None


def _retry_info_delay(payload: object) -> float | None:
    """The ``RetryInfo`` delay of one provider response, or None."""
    error = payload.get("error") if isinstance(payload, dict) else None
    entries = error.get("details") if isinstance(error, dict) else None
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict) or not str(entry.get("@type", "")).endswith(
            _RETRY_INFO_TYPE
        ):
            continue
        raw_delay = entry.get("retryDelay")
        match = _DURATION_RE.fullmatch(raw_delay) if isinstance(raw_delay, str) else None
        if match is not None:
            return float(match.group(1))
    return None
