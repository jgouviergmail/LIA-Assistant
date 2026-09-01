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
