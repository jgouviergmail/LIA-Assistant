"""Measure whether a model says « nothing new » when it should — real models, stated data.

A MEASUREMENT, never a gate: it calls real provider APIs and spends money. A
routine whose owner ticked « only tell me when there is something new » holds
its notification back when the answering model declares it found nothing new
(ADR-265 amendment c). The code guarantees what it can — a run that failed
somewhere is never silent, doubt notifies — but whether a model declares at the
right time is known by asking models.

Every run asks one with the prompt the response node builds for such a run, by
the SAME functions, inside ``quiet_run_scope`` so the delivery instruction is
injected where production injects it: the ReAct passthrough
(``_apply_react_passthrough``), the turn's data (``_build_data_for_filtering``),
what the run must admit (``build_run_honesty_block``), the response system
prompt (``_build_response_system_prompt``), the agent results summary
(``format_agent_results_for_prompt``, as an action turn reads it), the history
(``_prepare_conversational_messages``) and the chain (``_build_response_chain``).
The declaration is read by the same functions too (``take_answer_annotations``,
then the ``done`` metadata).

Both execution modes are asked, because they hand the response model different
things: in ``pipeline`` the read step's data and what it projected beyond its
items (ADR-347); in ``react`` — a routine's own default — the loop's final
answer, authoritative, beside the items its tools found.

What a scenario STATES is the turn's data, and in ``react`` the loop's answer —
the same on every run and for every model:

- ``nothing_found``: the mailbox search of the routine found no message —
  silence expected;
- ``something_found``: it found one — a notification expected;
- ``condition_unmet``: the tasks are there and none is overdue, which is what
  the routine watches — silence expected;
- ``condition_met``: one of them is overdue — a notification expected;
- ``same_as_before``: the one message the previous run already reported, and
  nothing else — OBSERVED, with no expectation: the product decides nothing
  there (« when in doubt, notify »).

What the bench leaves EMPTY is everything that belongs to one account — the
personality, the memories, the journal, the psyche — and the turn carries no
voice and no skill: what is measured is the delivery instruction inside the
response prompt, not one person's context, which can only lengthen that prompt.

The costly mistake is a silence where a notification was expected: it is the
column to read first. ``--models`` names the families to ask
(``provider:model[@level]``); without it the instance's own response slot is
asked, as the database configures it. Run inside the API container, which holds
the model configuration and the tariffs::

    python -m scripts.routines.measure_quiet_delivery --dry-run
    python -m scripts.routines.measure_quiet_delivery --reps 1 --scenario nothing_found
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final, Literal, cast, get_args
from unittest.mock import patch
from uuid import uuid4

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage  # noqa: E402

from scripts.llm_families import (  # noqa: E402
    Family,
    family_llm,
    parse_families,
    price_response,
)
from src.core.constants import (  # noqa: E402
    DEFAULT_USER_DISPLAY_TIMEZONE,
    RESPONSE_DISPLAY_MODE_CARDS,
    RESPONSE_DISPLAY_MODES_WITH_HTML,
)
from src.core.field_names import FIELD_STATUS, FIELD_TOOL_DATA  # noqa: E402
from src.core.i18n import resolve_language  # noqa: E402
from src.core.time_utils import now_in_timezone  # noqa: E402
from src.domains.agents.constants import (  # noqa: E402
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_MESSAGES,
    AgentResultStatus,
)
from src.domains.agents.formatters.agent_results import (  # noqa: E402
    format_agent_results_for_prompt,
)
from src.domains.agents.models import MessagesState  # noqa: E402
from src.domains.agents.nodes.response_node import (  # noqa: E402
    _apply_react_passthrough,
    _build_data_for_filtering,
    _build_response_chain,
    _build_response_system_prompt,
    _prepare_conversational_messages,
)
from src.domains.agents.services import nothing_new  # noqa: E402
from src.domains.agents.services.answer_annotations import (  # noqa: E402
    attach_answer_annotations_to_done,
    take_answer_annotations,
)
from src.domains.agents.services.nothing_new import (  # noqa: E402
    DONE_KEY,
    NOTHING_NEW_TAG_MARKER,
    quiet_run_scope,
)
from src.domains.agents.services.runtime_failure_directive import (  # noqa: E402
    build_run_honesty_block,
)
from src.domains.diagnostics import failure_context  # noqa: E402
from src.domains.diagnostics.advisor import CapabilityDegradation  # noqa: E402
from src.domains.llm_config.cache import LLMConfigOverrideCache  # noqa: E402
from src.infrastructure.cache.pricing_cache import refresh_pricing_cache  # noqa: E402
from src.infrastructure.database.session import get_db_context  # noqa: E402
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache  # noqa: E402

RESPONSE_SLOT: Final = "response"
#: The turn the scenario's data belongs to.
TURN: Final = 2
#: Where the delivery instruction opens in the prompt: a run without it measures nothing.
INSTRUCTION_MARKER: Final = "<delivery_declaration>"
#: The versioned file the instruction is loaded from; ``--instruction`` stands in for it.
INSTRUCTION_PROMPT: Final = "routine_nothing_new_instruction"
EXCERPT_CHARS: Final = 300
VIEWPORT: Final = "desktop"

Mode = Literal["pipeline", "react"]
MODES: Final[tuple[Mode, ...]] = get_args(Mode)
Items = dict[str, dict[str, Any]]
Records = list[dict[str, str]]


@dataclass(frozen=True)
class Scenario:
    """One routine run: what it was asked, what was found, what is expected of it.

    Attributes:
        key: The scenario's name.
        question: The routine's instruction, as its owner wrote it.
        agent: The agent whose pipeline step read the data.
        items: The registry items the run's tools produced, from today's date.
        records: What the pipeline step projected beyond its items (ADR-347).
        react_answer: The ReAct loop's final answer on the same data.
        earlier_answer: What the previous run of the same routine answered, when
            the scenario has a past.
        silence_expected: True when the run found nothing new, False when its
            owner must be told; None when the product defines no expectation.
    """

    key: str
    question: str
    agent: str
    items: Callable[[date], Items]
    records: Callable[[date], Records]
    react_answer: Callable[[date], str]
    earlier_answer: str | None = None
    silence_expected: bool | None = None


INVOICE_ANSWER = "One invoice arrived: invoice 2026-114 from billing@example.org, due in 14 days."


def _invoice(today: date) -> Items:
    return {
        "email_1": {
            "type": "EMAIL",
            "payload": {
                "subject": "Invoice 2026-114",
                "from": "billing@example.org",
                "date": today.isoformat(),
                "snippet": "Please find attached invoice 2026-114, due in 14 days.",
            },
        }
    }


def _mail_search(total: int) -> Callable[[date], Records]:
    def records(today: date) -> Records:
        text = json.dumps({"total": total, "query": f"invoice after:{today - timedelta(days=1)}"})
        return [{"tool": "get_emails_tool", "text": text}]

    return records


TASK_TITLES: Final = ("Renew the car insurance", "Book the dentist", "Send the tax form")


def _tasks(*due_in_days: int) -> Callable[[date], Items]:
    def items(today: date) -> Items:
        return {
            f"task_{index}": {
                "type": "TASK",
                "payload": {
                    "title": TASK_TITLES[index],
                    "status": "needsAction",
                    "due": (today + timedelta(days=offset)).isoformat(),
                },
            }
            for index, offset in enumerate(due_in_days)
        }

    return items


def _task_list(total: int) -> Callable[[date], Records]:
    def records(_today: date) -> Records:
        return [{"tool": "get_tasks_tool", "text": json.dumps({"total": total})}]

    return records


INVOICE_WATCH = "Check whether an invoice arrived in my mailbox since yesterday, and tell me."
OVERDUE_WATCH = "Check my tasks and tell me if one of them is overdue."

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "nothing_found",
        INVOICE_WATCH,
        "email_agent",
        lambda _today: {},
        _mail_search(0),
        lambda _today: "I searched your mailbox since yesterday: no invoice arrived.",
        silence_expected=True,
    ),
    Scenario(
        "something_found",
        INVOICE_WATCH,
        "email_agent",
        _invoice,
        _mail_search(1),
        lambda _today: INVOICE_ANSWER,
        silence_expected=False,
    ),
    Scenario(
        "condition_unmet",
        OVERDUE_WATCH,
        "task_agent",
        _tasks(3, 9, 21),
        _task_list(3),
        lambda today: (
            f"None of your three open tasks is overdue: the next one, « {TASK_TITLES[0]} », "
            f"is due on {today + timedelta(days=3)}."
        ),
        silence_expected=True,
    ),
    Scenario(
        "condition_met",
        OVERDUE_WATCH,
        "task_agent",
        _tasks(-2, 9, 21),
        _task_list(3),
        lambda today: (
            f"One task is overdue: « {TASK_TITLES[0]} » was due on " f"{today - timedelta(days=2)}."
        ),
        silence_expected=False,
    ),
    Scenario(
        "same_as_before",
        INVOICE_WATCH,
        "email_agent",
        _invoice,
        _mail_search(1),
        lambda _today: INVOICE_ANSWER,
        earlier_answer=INVOICE_ANSWER,
    ),
)


@dataclass
class Run:
    """What one run measured. Every text in it is the scenario's own synthetic data.

    ``honesty_chars`` is the size of what the run's prompt was told about the run
    and the platform (``build_run_honesty_block``): a scenario fails nothing, so
    on an instance with an open degradation it is the degradation, told to the
    model, which voids no declaration.
    """

    model: str
    mode: str
    scenario: str
    silence_expected: bool | None
    tag_written: bool = False
    declared: bool = False
    honesty_chars: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cost_eur: float = 0.0
    seconds: float = 0.0
    error: str = ""
    answer_excerpt: str = ""
    correct: bool | None = None


@dataclass(frozen=True)
class Turn:
    """A scenario's turn as the response node holds it right before the model is asked."""

    state: MessagesState
    system_prompt: str
    summary: str
    messages: list[BaseMessage]
    data_for_filtering: str
    honesty_chars: int


async def _nothing_degraded() -> list[CapabilityDegradation]:
    return []


@contextmanager
def _stated_platform() -> Iterator[None]:
    """The platform the turn runs on, stated like its data: nothing degraded.

    The diagnostics advisor reports the instance the bench runs on, and the
    answer tells the owner about it — measured 2026-11-13, dev's open alert
    reached the answers and kept them from silence. A live degradation would be
    one more variable, the same for no two runs.
    """
    with patch.object(failure_context, "get_active_degradations", _nothing_degraded):
        yield


@contextmanager
def _instruction(path: Path | None) -> Iterator[str]:
    """Render the delivery instruction from ``path`` in place of the versioned file.

    How an instruction meets its predecessor: everything else equal, its text
    alone changes. Without a path the versioned file speaks.

    Yields:
        The variant's name, for the report.
    """
    if path is None:
        yield "current"
        return
    text = path.read_text(encoding="utf-8")
    versioned = nothing_new.load_prompt

    def load(name: str, *args: Any, **kwargs: Any) -> Any:
        return text if name == INSTRUCTION_PROMPT else versioned(name, *args, **kwargs)

    with patch.object(nothing_new, "load_prompt", load):
        yield path.stem


def _state(scenario: Scenario, mode: Mode, timezone: str, language: str) -> MessagesState:
    """The fields the response node reads, in the shapes the graph writes them."""
    today = now_in_timezone(timezone).date()
    thread: list[BaseMessage] = []
    if scenario.earlier_answer is not None:
        thread += [
            HumanMessage(content=scenario.question, id="earlier-run"),
            AIMessage(content=scenario.earlier_answer, id="earlier-answer"),
        ]
    thread.append(HumanMessage(content=scenario.question, id="this-run"))
    state: dict[str, Any] = {
        STATE_KEY_CURRENT_TURN_ID: TURN,
        "current_turn_registry": scenario.items(today),
        "execution_mode": mode,
        "user_timezone": timezone,
        "user_language": language,
    }
    if mode == "pipeline":
        state[STATE_KEY_AGENT_RESULTS] = {
            f"{TURN}:{scenario.agent}": {
                FIELD_STATUS: AgentResultStatus.SUCCESS.value,
                "data": {"step_results": [{FIELD_TOOL_DATA: scenario.records(today)}]},
            }
        }
    else:
        answer = scenario.react_answer(today)
        # The loop appends its final answer to the thread during the turn; the
        # response node drops it from the history and reads it as authoritative.
        thread.append(AIMessage(content=answer, id="react-final"))
        state[STATE_KEY_AGENT_RESULTS] = {}
        state["react_agent_result"] = {"final_message": answer, "iteration_count": 2}
    state[STATE_KEY_MESSAGES] = thread
    return cast(MessagesState, state)


async def _turn(scenario: Scenario, mode: Mode, timezone: str, language: str, run_id: str) -> Turn:
    """Assemble the scenario's turn with the response node's own builders.

    Must run inside ``quiet_run_scope(True)``: the delivery instruction is
    injected by the prompt builder only there, and an admission voids the
    declaration only there.
    """
    state = _state(scenario, mode, timezone, language)
    react_result, _merged = _apply_react_passthrough(state, run_id)
    # The registry exactly as the state holds it: the builders' own type.
    registry = state.get("current_turn_registry") or {}
    data_for_filtering = _build_data_for_filtering(registry, run_id)
    with _stated_platform():
        honesty = await build_run_honesty_block(cast(dict[str, Any], state))
    system_prompt = _build_response_system_prompt(
        runtime_failures_block=honesty,
        state=state,
        run_id=run_id,
        user_timezone=timezone,
        user_language=language,
        user_viewport=VIEWPORT,
        user_display_mode=RESPONSE_DISPLAY_MODE_CARDS,
        user_psyche_enabled=False,
        personality_instruction=None,
        psychological_profile=None,
        knowledge_context="",
        rag_context="",
        user_query_for_prompt=scenario.question,
        last_user_message=scenario.question,
        enriched_query=None,
        data_for_filtering=data_for_filtering,
        resolved_references=[],
        anticipated_needs=None,
        skills_context="",
        app_knowledge_context="",
        journal_context="",
        psyche_context="",
        user_model_block=None,
        react_result=react_result,
    )
    if INSTRUCTION_MARKER not in system_prompt:
        raise SystemExit("the delivery instruction is not in the prompt: nothing to measure")
    # What an action turn's summary is, with no draft, rejection or planner error.
    summary = format_agent_results_for_prompt(
        state.get(STATE_KEY_AGENT_RESULTS, {}),
        current_turn_id=TURN,
        data_registry=registry or None,
        user_timezone=timezone,
        user_language=language,
        user_viewport=VIEWPORT,
    )
    messages = await _prepare_conversational_messages(
        state,
        run_id,
        neutralize_history_formatting=RESPONSE_DISPLAY_MODE_CARDS
        in RESPONSE_DISPLAY_MODES_WITH_HTML,
        plan_rejection_reason=None,
        current_turn_attachments=None,
        last_user_message=scenario.question,
        has_vision_content=False,
    )
    return Turn(state, system_prompt, summary, messages, data_for_filtering, len(honesty))


async def _run(
    scenario: Scenario, mode: Mode, model: str, llm: BaseChatModel, timezone: str, language: str
) -> Run:
    run = Run(model, mode, scenario.key, scenario.silence_expected)
    run_id = f"quiet-bench-{uuid4()}"
    started = time.perf_counter()
    with quiet_run_scope(True):
        turn = await _turn(scenario, mode, timezone, language, run_id)
        run.honesty_chars = turn.honesty_chars
        chain = _build_response_chain(
            base_system_prompt=turn.system_prompt,
            agent_results_summary=turn.summary,
            skills_context="",
            plan_rejection_reason=None,
            state=turn.state,
            user_language=language,
            llm=llm,
            performed_actions_block="",
        )
        try:
            response = await chain.ainvoke({STATE_KEY_MESSAGES: turn.messages})
        except Exception as exc:  # noqa: BLE001 — a measurement reports, it never raises
            run.error = f"{type(exc).__name__}: {str(exc)[:200]}"
            run.seconds = round(time.perf_counter() - started, 1)
            return run
        text = coerce_content_to_text(response.content)
        run.tag_written = NOTHING_NEW_TAG_MARKER in text.lower()
        shown = take_answer_annotations(text, run_id)
    done: dict[str, Any] = {}
    attach_answer_annotations_to_done(done, run_id)
    run.declared = done.get(DONE_KEY) is True
    priced = price_response(response, model)
    run.tokens_in, run.tokens_out = priced.tokens_in, priced.tokens_out
    run.cost_usd, run.cost_eur = priced.cost_usd, priced.cost_eur
    run.seconds = round(time.perf_counter() - started, 1)
    run.answer_excerpt = shown.strip()[:EXCERPT_CHARS]
    if scenario.silence_expected is not None:
        run.correct = run.declared == scenario.silence_expected
    return run


def _parse_modes(spec: str | None) -> list[Mode]:
    """The execution modes to ask (default: both)."""
    if not spec:
        return list(MODES)
    modes = [item.strip() for item in spec.split(",")]
    unknown = [mode for mode in modes if mode not in MODES]
    if unknown:
        raise SystemExit(f"unknown mode {unknown} (one of {', '.join(MODES)})")
    return [cast(Mode, mode) for mode in modes]


def _summary(runs: list[Run]) -> str:
    rows = [
        "| model | mode | scenario | n | expected | silent | tag written | correct "
        "| honesty block | errors | EUR/run |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str, str], list[Run]] = {}
    for run in runs:
        groups.setdefault((run.model, run.mode, run.scenario), []).append(run)
    for (model, mode, scenario), group in groups.items():
        asked = [run for run in group if not run.error]
        expected = group[0].silence_expected
        wanted = "-" if expected is None else ("silence" if expected else "notification")
        correct = "-" if expected is None else f"{sum(bool(r.correct) for r in asked)}/{len(asked)}"
        cost = statistics.mean(r.cost_eur for r in asked) if asked else 0.0
        rows.append(
            f"| {model} | {mode} | {scenario} | {len(group)} | {wanted} "
            f"| {sum(r.declared for r in asked)}/{len(asked)} "
            f"| {sum(r.tag_written for r in asked)}/{len(asked)} "
            f"| {correct} | {sum(r.honesty_chars > 0 for r in asked)} "
            f"| {len(group) - len(asked)} | {cost:.4f} |"
        )
    return "\n".join(rows)


async def _dry_run(
    scenarios: list[Scenario], modes: list[Mode], timezone: str, language: str
) -> int:
    """What each scenario hands the model, with no model asked and nothing spent."""
    for mode in modes:
        for scenario in scenarios:
            with quiet_run_scope(True):
                turn = await _turn(scenario, mode, timezone, language, "dry-run")
            print(
                json.dumps(
                    {
                        "mode": mode,
                        "scenario": scenario.key,
                        "silence_expected": scenario.silence_expected,
                        "system_prompt_chars": len(turn.system_prompt),
                        "instruction_in_prompt": INSTRUCTION_MARKER in turn.system_prompt,
                        "honesty_chars": turn.honesty_chars,
                        "history": [type(message).__name__ for message in turn.messages],
                        "agent_results_summary": turn.summary,
                        "registry_data": turn.data_for_filtering,
                    },
                    ensure_ascii=False,
                )
            )
    return 0


async def _measure(
    args: argparse.Namespace,
    families: list[Family | None],
    modes: list[Mode],
    scenarios: list[Scenario],
    timezone: str,
    language: str,
) -> tuple[list[Run], float]:
    """Ask every family every scenario in every mode, until the budget is reached."""
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    await refresh_pricing_cache()
    runs: list[Run] = []
    spent = 0.0
    started = time.perf_counter()
    for family in families:
        model, llm, _config = family_llm(RESPONSE_SLOT, family)
        for mode in modes:
            for scenario in scenarios:
                for _ in range(args.reps):
                    if spent > args.budget_eur:  # every remaining run is skipped, none is cut
                        break
                    run = await _run(scenario, mode, model, llm, timezone, language)
                    runs.append(run)
                    spent += run.cost_eur
                    print(json.dumps(asdict(run), ensure_ascii=False), flush=True)
    if spent > args.budget_eur:
        print(f"stopped: {args.budget_eur} EUR reached", file=sys.stderr)
    return runs, started


async def _amain(args: argparse.Namespace) -> int:
    families = parse_families(args.models)
    modes = _parse_modes(args.modes)
    wanted = set(args.scenario.split(",")) if args.scenario else None
    scenarios = [s for s in SCENARIOS if wanted is None or s.key in wanted]
    if not scenarios:
        raise SystemExit(f"no such scenario (one of {', '.join(s.key for s in SCENARIOS)})")
    timezone = args.timezone or DEFAULT_USER_DISPLAY_TIMEZONE
    language = resolve_language(args.language)
    with _instruction(args.instruction) as variant:
        if args.dry_run:
            return await _dry_run(scenarios, modes, timezone, language)
        runs, started = await _measure(args, families, modes, scenarios, timezone, language)
    judged = [run for run in runs if run.correct is not None]
    report = {
        "instruction": variant,
        "language": language,
        "runs": [asdict(run) for run in runs],
        "missed_notifications": sum(
            run.declared for run in judged if run.silence_expected is False
        ),
        "needless_notifications": sum(
            not run.declared for run in judged if run.silence_expected is True
        ),
        "cost_eur": round(sum(run.cost_eur for run in runs), 4),
        "cost_usd": round(sum(run.cost_usd for run in runs), 4),
        "seconds": round(time.perf_counter() - started, 1),
    }
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_summary(runs))
    print(json.dumps({key: value for key, value in report.items() if key != "runs"}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        help="provider:model[@level],... (default: the instance's own response slot)",
    )
    parser.add_argument("--modes", help="pipeline,react (default: both)")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--scenario", help="Comma-separated scenario keys (default: all)")
    parser.add_argument("--language", help="The answer's language (default: the declared one)")
    parser.add_argument("--timezone", help="The owner's timezone (default: the instance's)")
    parser.add_argument("--budget-eur", type=float, default=0.20, help="Stop past this spend (EUR)")
    parser.add_argument(
        "--instruction", type=Path, help="A delivery instruction file to measure instead"
    )
    parser.add_argument("--out", type=Path, help="Write the JSON report here")
    parser.add_argument("--dry-run", action="store_true", help="Build every turn, ask no model")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
