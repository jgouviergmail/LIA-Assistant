"""Agent-history summarization on the ``compaction`` slot.

LangChain's ``SummarizationMiddleware`` holds the model it summarizes with for
the life of the agent that carries it, and LIA builds its generic agents once
per process. That left two defects this module removes:

- the model was named by a setting of its own and built outside the factory,
  with the OpenAI key: a model no administration screen showed, which an
  installation holding no OpenAI key could not call;
- the library wraps that model in a retry that relaunches on ANY failure, a
  timeout included -- a generation whose outcome is unknown, bought again
  (ADR-221).

« Context Compaction » is the slot where the model that compresses a history is
chosen (owner decision 2026-11-11). The summarizer asks the factory for it at
each summary: it follows the administration screen like every other call, and
the client the factory hands out carries the one retry policy.
"""

from __future__ import annotations

from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.middleware.summarization import ContextSize
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from src.infrastructure.llm.factory import LLMType, get_llm

#: The slot whose model compresses a history: « Context Compaction ».
SUMMARIZATION_LLM_TYPE: LLMType = "compaction"


class SlotSummarizationMiddleware(SummarizationMiddleware):
    """``SummarizationMiddleware`` whose model IS the ``compaction`` slot.

    It takes no model: the slot is the model. What the library keeps from its
    construction (``self.model``) only tunes its token estimates; every summary
    is written by the slot as it is configured when the summary is asked.
    """

    def __init__(self, *, keep: ContextSize, trigger: ContextSize | None = None) -> None:
        """Build the middleware on the slot's model.

        Args:
            keep: How much recent history stays verbatim.
            trigger: When a history is summarized; ``None`` never triggers.
        """
        super().__init__(get_llm(SUMMARIZATION_LLM_TYPE), trigger=trigger, keep=keep)

    @property
    def _summary_model(self) -> Runnable[LanguageModelInput, AIMessage]:
        """The slot's model as configured now, on its own client's retry policy."""
        return get_llm(SUMMARIZATION_LLM_TYPE)

    @_summary_model.setter
    def _summary_model(self, retried: Runnable[LanguageModelInput, AIMessage]) -> None:
        """Leave out the copy the library stores at construction.

        It is ``model.with_retry()``: the model of that day, relaunched on any
        failure. Neither is kept -- see the module docstring.

        Args:
            retried: The retry-wrapped model the library assigns.
        """
