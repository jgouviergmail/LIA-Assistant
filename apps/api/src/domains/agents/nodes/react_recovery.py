"""A ReAct turn is judged on its result: a declared gap buys a recovery pass (ADR-310).

The loop ends when the model calls no tool. Until ADR-310 that was the whole
rule, so a fact the model could not get — a tool that served another day, an
error, an empty result — ended the turn as a stated gap the moment the model
chose to stop, however many sources it still had. Measured on 2026-09-23: a
forecast came back for the wrong day, the loop saw it, and answered « I could
not get it » after 4 iterations of the 70 its budget allowed, with a web search
it never tried.

The protocol, in one module:

- the model closes its final message with an ``<unresolved>`` block, one line
  per fact the answer needs but could not obtain (:func:`declared_unresolved`);
- ONE predicate says whether the turn may take a pass (:func:`should_recover`):
  a declared gap, a pass left under ``REACT_RECOVERY_PASSES_MAX``, and no stop
  condition — it CALLS ``react_exit_reason``, the one stop predicate, never a copy;
- :func:`react_recovery_node` calls no model: it removes the draft from the thread
  AT the pass — so every exit of the loop leaves it clean, the draft hand-off to
  the HITL dispatch included — and records the pass;
- every later model call of the turn is shown, right after the draft's place,
  the draft again and a directive naming the gaps (:func:`with_recovery_directives`).
  Both are composed per call and never written to ``messages``: no later turn
  reads the directive as something the person said, and the roles keep
  alternating on every provider;
- the finalize node merges what the passes achieved, counted once, into its
  result (:func:`recovery_report`, over :func:`recovery_outcome`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.utils.react_budget import react_exit_reason
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import agent_node_duration_seconds
from src.infrastructure.observability.metrics_react import react_recovery_turns_total
from src.infrastructure.observability.tracing import trace_node

if TYPE_CHECKING:
    from src.domains.agents.models import MessagesState

logger = structlog.get_logger(__name__)

__all__ = [
    "EMPTY_DECLARATIONS",
    "declared_unresolved",
    "react_recovery_node",
    "recovery_outcome",
    "recovery_report",
    "should_recover",
    "with_recovery_directives",
]

#: A block runs from the LAST opening before its closing: a model that names the
#: tag in its reasoning (« declare it in <unresolved> ») opens nothing — read from
#: the first opening, the prose between the two became twelve « facts » (measured
#: on dev, 2026-09-24).
_BLOCK = re.compile(
    r"<unresolved>((?:(?!<unresolved>).)*?)</unresolved>", re.IGNORECASE | re.DOTALL
)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
#: Stripped before the lookup, so the « ... » the prompt shows declares nothing
#: and a Chinese « 无。 » reads as the « 无 » it is.
_TRAILING = ".!…。．"

#: Lines that declare nothing. The prompt says to OMIT the block when nothing is
#: missing; a model that writes it anyway writes one of these, in the person's
#: language (the loop's final message is written in it). Six languages,
#: lower-cased, trailing punctuation stripped before the lookup.
EMPTY_DECLARATIONS: frozenset[str] = frozenset(
    {
        "",
        "-",
        "–",
        "—",
        "none",
        "n/a",
        "nothing",
        "aucun",
        "aucune",
        "rien",
        "keine",
        "keiner",
        "keines",
        "keins",
        "nichts",
        "nada",
        "ninguno",
        "ninguna",
        "nessuno",
        "nessuna",
        "niente",
        "无",
        "没有",
    }
)


def declared_unresolved(message: BaseMessage | None) -> tuple[str, ...]:
    """The facts a message declares unresolved, in order, without duplicates.

    Every ``<unresolved>`` block counts, wherever the model put it (inside its
    ``<thought>`` too): the declaration matters, not its place.

    Args:
        message: The message to read, or None.

    Returns:
        One entry per declared fact; empty when the message declares none.
    """
    if message is None:
        return ()
    facts: list[str] = []
    for block in _BLOCK.findall(coerce_content_to_text(message.content)):
        for raw in block.splitlines():
            fact = _BULLET.sub("", raw).strip()
            if fact.rstrip(_TRAILING).lower() in EMPTY_DECLARATIONS or fact in facts:
                continue
            facts.append(fact)
    return tuple(facts)


def should_recover(state: MessagesState) -> bool:
    """Whether the turn takes a recovery pass instead of finalizing.

    Guard clauses, cheapest first: the routing tests patch the settings with a
    mock, which no clean answer ever reaches.

    Args:
        state: Current graph state.

    Returns:
        True when the last message is a final answer that declares a gap, a pass
        is left, and no budget stops the loop.
    """
    messages = state.get("messages") or []
    if len(messages) < 2:
        return False
    draft, previous = messages[-1], messages[-2]
    if not isinstance(draft, AIMessage) or draft.tool_calls:
        return False
    if not draft.id or not previous.id or not declared_unresolved(draft):
        return False
    # Late import: the routing tests patch ``src.core.config.settings``.
    from src.core.config import settings as _settings

    passes = state.get("react_recovery_passes") or []
    if len(passes) >= int(_settings.react_recovery_passes_max):
        return False
    return react_exit_reason(state) is None


@trace_node("react_recovery")
@track_metrics(node_name="react_recovery", duration_metric=agent_node_duration_seconds)
async def react_recovery_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """Take a recovery pass: the draft leaves the thread, the pass is recorded.

    Args:
        state: Current graph state; its last message is the draft that declared gaps.
        config: RunnableConfig (unused: this node calls no model).

    Returns:
        The draft's removal and the turn's passes with this one appended.
    """
    messages = state["messages"]
    draft, previous = messages[-1], messages[-2]
    unresolved = list(declared_unresolved(draft))
    record: dict[str, Any] = {
        "anchor_id": previous.id,
        "draft": coerce_content_to_text(draft.content),
        "unresolved": unresolved,
    }
    passes = [*(state.get("react_recovery_passes") or []), record]
    logger.info(
        "react_recovery_pass_started",
        pass_number=len(passes),
        declared=len(unresolved),
        iteration=state.get("react_iteration", 0),
    )
    return {"messages": [RemoveMessage(id=str(draft.id))], "react_recovery_passes": passes}


def with_recovery_directives(
    messages: Sequence[BaseMessage], passes: Sequence[Mapping[str, Any]]
) -> list[BaseMessage]:
    """The messages of one call, with each pass's draft and directive shown in place.

    Each pass puts, after its anchor (the draft's predecessor) and after the
    system messages glued to it — the turn's context under ADR-308 stays right
    after its question — the draft as an assistant message, then the directive.
    Passes sharing an anchor (a pass whose reply called no tool leaves the next
    draft the same predecessor) are shown together, in the order they were taken.

    Args:
        messages: The composed messages of the call.
        passes: The turn's recovery records.

    Returns:
        A new list; the given one is never modified.
    """
    by_anchor: dict[str, list[BaseMessage]] = {}
    for record in passes:
        by_anchor.setdefault(str(record["anchor_id"]), []).extend(
            [
                AIMessage(content=record["draft"]),
                HumanMessage(content=_directive_text(record["unresolved"])),
            ]
        )
    out = list(messages)
    for anchor_id, shown in by_anchor.items():
        at = next((i for i, m in enumerate(out) if m.id == anchor_id), None)
        if at is None:
            logger.warning("react_recovery_anchor_missing", pass_count=len(passes))
            out.extend(shown)
            continue
        at += 1
        while at < len(out) and isinstance(out[at], SystemMessage):
            at += 1
        out[at:at] = shown
    return out


def _directive_text(unresolved: Sequence[str]) -> str:
    """The versioned directive, naming the declared facts."""
    return load_prompt("react_recovery_directive").format(
        unresolved="\n".join(f"- {fact}" for fact in unresolved),
    )


def _has_answer(message: BaseMessage | None) -> bool:
    """Whether the loop's last message carries an answer at all."""
    return isinstance(message, AIMessage) and bool(coerce_content_to_text(message.content).strip())


def recovery_outcome(
    passes: Sequence[Mapping[str, Any]], final: BaseMessage | None, *, cut: bool
) -> str | None:
    """What the passes achieved, for the metric and the debug panel.

    Args:
        passes: The turn's recovery records.
        final: The loop's last message.
        cut: Whether a budget ended the loop with calls still pending.

    Returns:
        ``resolved``, ``partial``, ``still_unresolved`` or ``cut``; None when the
        turn took no pass. A pass that brought back no answer resolved nothing:
        the draft's gaps stand.
    """
    if not passes:
        return None
    if cut:
        return "cut"
    if not _has_answer(final):
        return "still_unresolved"
    remaining = len(declared_unresolved(final))
    if remaining == 0:
        return "resolved"
    return "partial" if remaining < len(passes[0]["unresolved"]) else "still_unresolved"


def recovery_report(
    state: MessagesState, final: BaseMessage | None, *, cut: bool
) -> dict[str, Any]:
    """What the finalize node merges into ``react_agent_result``, counted once.

    A mapping to merge, never None, so the finalize node takes no branch of its
    own for it (its complexity is frozen by the ratchet). The draft left the
    thread AT the pass, so a pass that ends with no usable answer — an empty
    reply, or a budget that stopped it with calls pending — hands back the last
    draft as the final message: a complete answer the turn already had is never
    traded for nothing.

    Args:
        state: Current graph state.
        final: The loop's last message.
        cut: Whether a budget ended the loop with calls still pending.

    Returns:
        ``{"recovery": {"passes": n, "outcome": ...}}`` when the turn took a pass,
        with ``final_message`` when the last draft stands for the answer; else an
        empty mapping.
    """
    passes = state.get("react_recovery_passes") or []
    outcome = recovery_outcome(passes, final, cut=cut)
    if outcome is None:
        return {}
    restored = cut or not _has_answer(final)
    react_recovery_turns_total.labels(outcome=outcome).inc()
    logger.info(
        "react_recovery_settled", passes=len(passes), outcome=outcome, draft_restored=restored
    )
    report: dict[str, Any] = {"recovery": {"passes": len(passes), "outcome": outcome}}
    if restored:
        report["final_message"] = passes[-1]["draft"]
    return report
