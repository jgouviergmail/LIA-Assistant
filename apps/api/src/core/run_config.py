"""Reading a graph run's ``RunnableConfig`` — the run id's one reader (ADR-231).

ADR-231 took run-scoped values off ``configurable``, which carries LangGraph
plumbing only (the thread id): the orchestration service writes the run id in
``metadata`` and nowhere else. Readers that kept looking in ``configurable``
read a key no writer writes. The effect register was one of them: it filed
every direct action under the THREAD id, so two turns of one conversation
claimed the same pipeline step key and the second was served the first one's
recorded result instead of running — measured in production on 2026-09-22, a
reminder never created — and the register never found a turn's acts to state.

Lives in ``core`` so every layer reads the run id the same way, the graph
nodes, the effect register and the tracing alike.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.core.field_names import FIELD_METADATA, FIELD_RUN_ID


def run_id_of(config: object, default: str = "") -> str:
    """The run id a graph config carries.

    Args:
        config: A ``RunnableConfig`` (anything else carries no run).
        default: What to return when the config carries none (a log line's
            ``unknown``) — a parameter, so no caller spells the fallback twice.

    Returns:
        The run id, or ``default`` when the config carries none.
    """
    if not isinstance(config, Mapping):
        return default
    metadata = config.get(FIELD_METADATA)
    run_id = metadata.get(FIELD_RUN_ID) if isinstance(metadata, Mapping) else None
    return str(run_id) if run_id else default
