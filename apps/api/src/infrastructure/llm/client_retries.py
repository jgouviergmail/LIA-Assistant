"""Who may send a failed model call again (ADR-100 and ADR-221 amendments).

The vendor SDKs under LangChain's chat classes retry a transient failure on their
own, with backoff and the provider's ``Retry-After``; the relaunch policy
(``providers/retry_policy.py``, owner decision Q3 (a) of 2026-10-28) sets that budget
to ``LLM_TRANSIENT_RETRY_MAX`` and forbids any relaunch once the request may have
reached the provider. LangChain exposes the budget as the class's public
``max_retries``: an integer, or ``None`` on the OpenAI wire for « the SDK's default ».
A class without the field — the Ollama client — has no retry loop of its own, so a
caller's loop is the only one it gets.

A caller's loop (the structured-output door, the compaction, the agents' retry
middleware) therefore never second-guesses a client that owns its retries — zero
included: zero is the policy's answer, not an absence — and never sends again a call
whose outcome is unknown. Retry at one layer only. Whether a request may have left is
decided once, in ``infrastructure/utils/request_outcome.py``, shared with the connectors.
"""

from __future__ import annotations

import aiohttp
import anthropic
import httpx
import openai
from langchain_core.runnables import RunnableBinding

from src.core.config import settings
from src.infrastructure.llm.structured_output_errors import provider_answered, provider_refused
from src.infrastructure.utils.request_outcome import (
    error_chain,
    never_reached_the_server,
    outcome_unknown,
)

_ABSENT = object()

#: The note a streamed call's failure carries once its first chunk had arrived: the
#: generation had begun, and is never sent again in any form (Q3 (a)).
STREAM_BEGAN_NOTE = "lia: the model stream had begun"

#: Errors only the wire raises: a vendor SDK's or a transport's. A failure with one of
#: them in its chain is the provider's, whether or not it carries a status — an error
#: event inside an OpenAI stream carries none, nor does a cut inside aiohttp.
_WIRE_ERRORS: tuple[type[BaseException], ...] = (
    openai.APIError,
    anthropic.APIError,
    httpx.HTTPError,
    aiohttp.ClientError,
)


def client_owns_its_retries(llm: object) -> bool:
    """Whether ``llm`` has a retry loop of its own, whatever its budget.

    Args:
        llm: A chat model, or a binding of one (``bind_tools``, ``with_config``).

    Returns:
        True when the class declares ``max_retries`` (an integer — zero included — or
        ``None`` for the SDK's default); False when it has no such loop (Ollama).
    """
    model = llm.bound if isinstance(llm, RunnableBinding) else llm
    return getattr(model, "max_retries", _ABSENT) is not _ABSENT


def caller_may_relaunch(llm: object, error: BaseException, relaunches_made: int) -> bool:
    """Whether a caller's own loop may send a failed model call again.

    Args:
        llm: The chat model the call was made on.
        error: What the call raised.
        relaunches_made: How many times this caller already sent it again.

    Returns:
        True only for a call that never reached the provider, on a client with no retry
        loop of its own, within ``LLM_TRANSIENT_RETRY_MAX``.
    """
    return (
        not client_owns_its_retries(llm)
        and never_reached_the_server(error)
        and relaunches_made < settings.llm_transient_retry_max
    )


def may_send_in_another_form(llm: object, error: BaseException) -> bool:
    """Whether a caller may answer a failed model call with ANOTHER request.

    The buffered twin of a streamed call (the planner, the ReAct loop), the next door of
    the structured output: each is a second generation unless the first generated
    nothing. Measured by the fresh review of 2026-10-29: after a read timeout the SDK
    correctly sent nothing again, and the caller then sent the whole generation again.

    Args:
        llm: The chat model the call was made on, or a binding of one.
        error: What the call raised.

    Returns:
        False once the stream had begun (``stream_began``); True for a failure with no
        trace of the wire — no status, no vendor or transport error in its chain (a
        capture or framework defect: the request may never have been made) —, a
        deterministic refusal (the provider answered and generated nothing), or a call
        the caller may relaunch itself (``caller_may_relaunch``); False for every other
        provider failure — an unknown outcome, or a transient one whose relaunch budget
        the client already spent.
    """
    if stream_began(error):
        return False
    if not _from_the_wire(error):
        return True
    return provider_refused(error) or caller_may_relaunch(llm, error, 0)


def stream_began(error: BaseException) -> bool:
    """Whether a failed streamed call had received its first chunk (``STREAM_BEGAN_NOTE``)."""
    return any(STREAM_BEGAN_NOTE in getattr(link, "__notes__", ()) for link in error_chain(error))


def _from_the_wire(error: BaseException) -> bool:
    """Whether the provider or the transport raised it — positive evidence only."""
    return (
        provider_answered(error)
        or never_reached_the_server(error)
        or outcome_unknown(error)
        or any(isinstance(link, _WIRE_ERRORS) for link in error_chain(error))
    )
