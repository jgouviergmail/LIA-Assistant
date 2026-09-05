"""What reaches the Google SDK is an EXACT ``str`` — never a subclass.

Measured in production on 2026-09-05: every RAG query of every turn came back
``500 INTERNAL`` while the memory embedding of the SAME text, 0.3 s earlier,
succeeded. The difference was the TYPE of the text. ``HumanMessage.text`` is a
``TextAccessor`` — a ``str`` subclass langchain-core keeps so ``.text()`` still
works — and google-genai validates ``contents`` through a pydantic union in which
``Content`` (``from_attributes=True``) precedes ``str``: a subclass instance is
accepted as an attribute-less object and becomes an EMPTY ``Content``. On the
wire: ``"content": {}``. The memory path only survived because it sliced the text
(``message[:N]`` yields a plain ``str``).

The funnel is the one place every Gemini embedding goes through, so it is the one
place that normalises. These tests pin that contract for all four public methods,
with the real ``TextAccessor`` and with a bare ``str`` subclass, so no caller can
reintroduce the defect by forgetting to slice.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.infrastructure.llm.gemini_embeddings import GeminiRetrievalEmbeddings
from src.infrastructure.rate_limiting.slot_waiter import SlotOutcome

pytestmark = pytest.mark.unit

_SLOT = "src.infrastructure.llm.gemini_embeddings.wait_for_slot"


class _Sub(str):
    """A bare ``str`` subclass: the minimal shape that trips the SDK."""


def _embeddings() -> GeminiRetrievalEmbeddings:
    with patch("src.infrastructure.llm.gemini_embeddings.GoogleGenerativeAIEmbeddings"):
        return GeminiRetrievalEmbeddings(model="models/gemini-embedding-001")


def _subclass_inputs() -> list[str]:
    """The real offender and its minimal reproduction, both ``isinstance(str)``."""
    return [HumanMessage(content="bonjour").text, _Sub("bonjour")]


def _assert_exact(value: object) -> None:
    assert type(value) is str, f"the SDK received a {type(value).__name__}, not an exact str"
    assert value == "bonjour"


class TestAsyncQuery:
    @pytest.mark.parametrize("text", _subclass_inputs(), ids=["TextAccessor", "str_subclass"])
    async def test_the_sdk_receives_an_exact_str(self, text: str) -> None:
        assert isinstance(text, str), "precondition: the offender passes isinstance"
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(return_value=[0.1])

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            await embeddings.aembed_query(text)

        _assert_exact(embeddings._client.aembed_query.await_args.args[0])


class TestAsyncDocuments:
    async def test_every_text_of_the_batch_reaches_the_sdk_as_an_exact_str(self) -> None:
        embeddings = _embeddings()
        embeddings._client.aembed_documents = AsyncMock(return_value=[[0.1], [0.2], [0.3]])

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            await embeddings.aembed_documents(["bonjour", *_subclass_inputs()])

        sent = embeddings._client.aembed_documents.await_args.args[0]
        assert len(sent) == 3
        for value in sent:
            _assert_exact(value)


class TestSyncTwins:
    """Unshaped and unretried by design (nobody calls them), but the LangChain
    contract exposes them — a future caller must not find the trap waiting."""

    @pytest.mark.parametrize("text", _subclass_inputs(), ids=["TextAccessor", "str_subclass"])
    def test_embed_query_normalises(self, text: str) -> None:
        embeddings = _embeddings()
        embeddings._client.embed_query = MagicMock(return_value=[0.1])

        embeddings.embed_query(text)

        _assert_exact(embeddings._client.embed_query.call_args.args[0])

    def test_embed_documents_normalises_every_text(self) -> None:
        embeddings = _embeddings()
        embeddings._client.embed_documents = MagicMock(return_value=[[0.1], [0.2]])

        embeddings.embed_documents(_subclass_inputs())

        for value in embeddings._client.embed_documents.call_args.args[0]:
            _assert_exact(value)


class TestAPlainStrIsPassedThroughUntouched:
    async def test_the_same_object_is_forwarded(self) -> None:
        """Normalising must cost nothing on the nominal path: an exact ``str``
        is forwarded as-is, not copied."""
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(return_value=[0.1])
        text = "bonjour"

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            await embeddings.aembed_query(text)

        assert embeddings._client.aembed_query.await_args.args[0] is text
