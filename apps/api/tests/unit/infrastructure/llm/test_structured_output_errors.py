"""A provider refusal is read where the provider wrote it, through every wrapper.

langchain re-raises a provider failure wrapped (``ChatGoogleGenerativeAIError``
around google-genai's ``ClientError``), so the status that decides whether
resending the unchanged request can ever succeed is rarely on the exception the
structured-output door catches. Read on the outer exception alone, a Gemini 400
was retried at full price by ``get_structured_output_with_retry``.
"""

import pytest
from google.genai.errors import ClientError
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from src.infrastructure.llm.structured_output_errors import (
    StructuredOutputRefusedError,
    raise_if_provider_refused,
)

pytestmark = pytest.mark.unit


def _wrapped(code: int) -> ChatGoogleGenerativeAIError:
    """A Gemini failure as langchain-google-genai raises it: wrapped, the code on its cause."""
    cause = ClientError(code, {"error": {"code": code, "status": "INVALID_ARGUMENT"}}, None)
    try:
        raise ChatGoogleGenerativeAIError("Error calling model") from cause
    except ChatGoogleGenerativeAIError as error:
        return error


def test_a_wrapped_deterministic_refusal_is_read_through_its_cause() -> None:
    error = _wrapped(400)

    with pytest.raises(StructuredOutputRefusedError) as caught:
        raise_if_provider_refused(error, "gemini", "Answer")

    assert caught.value.status_code == 400
    assert caught.value.original_error is error


@pytest.mark.parametrize("code", [408, 409, 425, 429, 500, 503])
def test_a_wrapped_retryable_status_is_left_to_the_retry(code: int) -> None:
    raise_if_provider_refused(_wrapped(code), "gemini", "Answer")


def test_the_outermost_status_decides_over_a_cause() -> None:
    class _Throttled(Exception):
        status_code = 429

    cause = ClientError(400, {"error": {"code": 400}}, None)
    try:
        raise _Throttled() from cause
    except _Throttled as error:
        outer = error

    # The provider TOLD the caller to wait: a deeper status never overturns it.
    raise_if_provider_refused(outer, "gemini", "Answer")


def test_an_error_without_any_status_is_not_a_refusal() -> None:
    try:
        raise ValueError("unparsable") from KeyError("missing")
    except ValueError as error:
        raise_if_provider_refused(error, "gemini", "Answer")
