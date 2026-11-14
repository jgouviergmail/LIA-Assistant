"""Measure which skill the query analyzer detects — real models, stated requests.

A MEASUREMENT, never a gate: it calls real provider APIs and spends money. A
skill is detected by the query analyzer reading its description (ADR-160), for
every account it is active for: a description that over-matches takes requests
that are not its own (the July 2026 incident, where `skill-generator` took
image requests), and one that under-matches is never run. Every request of the
corpus is asked of the analyzer by the production function (``analyze_query``),
with the system skills of THIS checkout in its list, and what it detects is
compared with what the request expects: one skill, or none.

The corpus is ENGLISH: the analyzer reads the semantic pivot, the English
translation of the person's message, never their own words. It holds triggers of
the skills under test and neighbours — requests one domain away (a list of
unread mail, this week's meetings) that a loose description would take. Read
first the hijacks (a neighbour taken by a skill under test), then the misses (a
trigger left to the planner).

``--models`` names the families to ask (``provider:model[@level]``); without it
the instance's own analyzer slot is asked, as the database configures it. Run
inside the API container, which holds the model configuration and the tariffs::

    python -m scripts.skills.measure_skill_detection --dry-run
    python -m scripts.skills.measure_skill_detection --models deepseek:deepseek-flash
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final
from unittest.mock import patch

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.callbacks import AsyncCallbackHandler  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.outputs import LLMResult  # noqa: E402

from scripts.llm_families import Family, family_llm, parse_families  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.core.llm_agent_config import LLMAgentConfig  # noqa: E402
from src.domains.agents.services.query_analyzer_service import (  # noqa: E402
    QueryAnalysisResult,
    analyze_query,
)
from src.domains.llm_config.cache import LLMConfigOverrideCache  # noqa: E402
from src.domains.skills.cache import SkillsCache  # noqa: E402
from src.domains.skills.injection import build_analyzer_skill_list  # noqa: E402
from src.infrastructure.cache.pricing_cache import (  # noqa: E402
    get_cached_cost_usd_eur,
    refresh_pricing_cache,
)
from src.infrastructure.database.session import get_db_context  # noqa: E402
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache  # noqa: E402
from src.infrastructure.llm.usage_metadata import (  # noqa: E402
    model_name_of_response,
    tokens_from_usage_metadata,
)

ANALYZER_SLOT: Final = "query_analyzer"
#: The skills a run measures: their triggers must be found, their neighbours left alone.
UNDER_TEST: Final = ("revue-hebdomadaire", "tri-boite-reception", "skill-generator")
#: Where the system skills of the checkout are, relative to the API's working directory.
DEFAULT_SKILLS_DIR: Final = Path(settings.skills_system_path)


@dataclass(frozen=True)
class Request:
    """One English pivot, and the skill the analyzer should detect for it (None: none)."""

    text: str
    expected: str | None


CORPUS: Final[tuple[Request, ...]] = (
    # The weekly review.
    Request("Do my weekly review", "revue-hebdomadaire"),
    Request("Review my week", "revue-hebdomadaire"),
    Request(
        "Give me a weekly recap: what I finished, what is still open and what is coming "
        "next week",
        "revue-hebdomadaire",
    ),
    Request("Can you do my end-of-week review?", "revue-hebdomadaire"),
    Request("Weekly check-in please", "revue-hebdomadaire"),
    # The inbox triage.
    Request("Triage my inbox", "tri-boite-reception"),
    Request("Sort my inbox", "tri-boite-reception"),
    Request("Sort my emails: what needs a reply and what can wait", "tri-boite-reception"),
    Request("What in my mail needs my attention?", "tri-boite-reception"),
    Request("Do an inbox triage for me", "tri-boite-reception"),
    # A skill made from what was just done (lot 20): the generator's own trigger.
    Request("Turn what we just did into a skill I can reuse", "skill-generator"),
    Request("Save this as a skill", "skill-generator"),
    Request(
        "Make a skill out of what we just did so I can run it again every morning",
        "skill-generator",
    ),
    Request("Create a reusable skill from this conversation", "skill-generator"),
    # ... and its classic trigger: a skill described in words.
    Request("Create a skill that summarizes my unread emails every morning", "skill-generator"),
    Request("I want to build my own skill to prepare my meetings", "skill-generator"),
    # Neighbours: one domain away, never a skill under test.
    Request("What are my meetings this week?", None),
    Request("Show my tasks", None),
    Request("What is due tomorrow?", None),
    Request("List my overdue tasks", None),
    Request("What is on my calendar next week?", None),
    Request("Show my unread emails", None),
    Request("Read the last email from Paul", None),
    Request("Reply to Marie's email", None),
    Request("Which emails have I not answered yet?", None),
    Request("Archive the newsletters in my inbox", None),
    Request("Summarize the emails I received today", None),
    Request("Give me my daily briefing", "briefing-quotidien"),
)


@dataclass
class Detection:
    """What the analyzer detected for one request, and what it cost."""

    model: str
    request: str
    expected: str | None
    detected: str | None = None
    correct: bool | None = None
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cost_eur: float = 0.0
    seconds: float = 0.0


@dataclass(eq=False)
class _Usage(AsyncCallbackHandler):
    """The usage every model call of one analysis reports, read where LangChain hands it.

    Hashed by identity (``eq=False``): a provider's native structured output keeps
    its callbacks in a set, and an unhashable handler fails every call there.
    """

    calls: list[tuple[str, int, int, int, int]] = field(default_factory=list)

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                usage = tokens_from_usage_metadata(getattr(message, "usage_metadata", None))
                self.calls.append(
                    (
                        model_name_of_response(message) or "",
                        usage.prompt,
                        usage.completion,
                        usage.cached,
                        usage.cache_write,
                    )
                )


def read_detection(result: QueryAnalysisResult) -> tuple[str | None, str | None]:
    """The skill an analysis detected, or why it detected nothing.

    ``analyze_query`` answers a failure with a fallback carrying no skill: read
    as « no skill », a timeout would pass for a neighbour correctly left alone.

    Args:
        result: What ``analyze_query`` returned.

    Returns:
        ``(detected skill, error)``; at most one of them is set.
    """
    error = result.raw_output.get("error") if isinstance(result.raw_output, dict) else None
    if error:
        return None, str(error)
    return result.skill_name, None


def totals(rows: list[Detection]) -> dict[str, dict[str, int]]:
    """Per model: asked, errors, correct, misses and hijacks — the last two can overlap.

    A miss is a trigger of a skill under test not detected as it; a hijack is a
    skill under test detected for a request that is not its own. A trigger of one
    detected as the other is both.
    """
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        counts = out.setdefault(
            row.model,
            {"asked": 0, "errors": 0, "correct": 0, "misses": 0, "hijacks": 0, "other": 0},
        )
        counts["asked"] += 1
        if row.error:
            counts["errors"] += 1
            continue
        if row.detected == row.expected:
            counts["correct"] += 1
            continue
        missed = row.expected in UNDER_TEST
        hijacked = row.detected in UNDER_TEST
        counts["misses"] += missed
        counts["hijacks"] += hijacked
        counts["other"] += not (missed or hijacked)
    return out


def require_skills_on() -> None:
    """Refuse to measure an instance whose skills are off.

    ``analyze_query`` lists no skill there, whatever the cache holds: every
    trigger would read as a miss, a measure of the switch and not of a
    description.

    Raises:
        SystemExit: ``SKILLS_ENABLED`` is off.
    """
    if not settings.skills_enabled:
        raise SystemExit("skills are switched off on this instance: the analyzer lists none")


def analyzer_skill_list(skills_dir: Path) -> str:
    """Load the checkout's system skills, and render the list the analyzer reads.

    Args:
        skills_dir: The system skills directory of the checkout.

    Returns:
        The analyzer's skill list, every skill active.
    """
    SkillsCache.load_from_disk(str(skills_dir), str(skills_dir / ".no-user-skills"))
    return build_analyzer_skill_list("", None, enabled=True)


@contextmanager
def _asked(llm: BaseChatModel, config: LLMAgentConfig) -> Iterator[None]:
    """Make the analyzer ask ``llm`` under ``config``: it reads both at call time."""

    def model(*args: Any, **kwargs: Any) -> BaseChatModel:
        return llm

    def configuration(*args: Any, **kwargs: Any) -> LLMAgentConfig:
        return config

    with (
        patch("src.infrastructure.llm.get_llm", model),
        patch("src.core.llm_config_helper.get_llm_config_for_agent", configuration),
    ):
        yield


async def detect(
    request: Request, model: str, llm: BaseChatModel, config: LLMAgentConfig
) -> Detection:
    """Ask the analyzer one request on one family.

    Args:
        request: The request and the skill it expects.
        model: The family's model name, for the report.
        llm: The family's model.
        config: The configuration it was built from (its provider shapes the call).

    Returns:
        What it detected, judged, with its tokens and cost.
    """
    row = Detection(model, request.text, request.expected)
    usage = _Usage()
    started = time.perf_counter()
    with _asked(llm, config):
        result = await analyze_query(query=request.text, base_config={"callbacks": [usage]})
    row.seconds = round(time.perf_counter() - started, 1)
    row.detected, row.error = read_detection(result)
    if row.error is None:
        row.correct = row.detected == request.expected
    for name, prompt, completion, cached, cache_write in usage.calls:
        row.tokens_in += prompt
        row.tokens_out += completion
        cost_usd, cost_eur = get_cached_cost_usd_eur(
            name or model, prompt, completion, cached, cache_write_tokens=cache_write
        )
        row.cost_usd += cost_usd
        row.cost_eur += cost_eur
    return row


def _summary(rows: list[Detection]) -> str:
    lines = [
        "| model | asked | correct | misses | hijacks | other | errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, counts in totals(rows).items():
        lines.append(
            f"| {model} | {counts['asked']} | {counts['correct']} | {counts['misses']} "
            f"| {counts['hijacks']} | {counts['other']} | {counts['errors']} |"
        )
    wrong = [row for row in rows if row.correct is False]
    if wrong:
        lines += ["", "| model | request | expected | detected |", "|---|---|---|---|"]
        lines += [
            f"| {row.model} | {row.request} | {row.expected} | {row.detected} |" for row in wrong
        ]
    return "\n".join(lines)


async def _measure(
    families: list[Family | None], requests: list[Request], reps: int, budget_eur: float
) -> list[Detection]:
    """Ask every family every request, until the budget is reached."""
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    await refresh_pricing_cache()
    rows: list[Detection] = []
    spent = 0.0
    for family in families:
        model, llm, config = family_llm(ANALYZER_SLOT, family)
        for request in requests:
            for _ in range(reps):
                if spent > budget_eur:  # every remaining request is skipped, none is cut
                    break
                row = await detect(request, model, llm, config)
                rows.append(row)
                spent += row.cost_eur
                print(json.dumps(asdict(row), ensure_ascii=False), flush=True)
    if spent > budget_eur:
        print(f"stopped: {budget_eur} EUR reached", file=sys.stderr)
    return rows


async def _amain(args: argparse.Namespace) -> int:
    require_skills_on()
    listed = analyzer_skill_list(args.skills_dir)
    missing = [skill for skill in UNDER_TEST if f"**{skill}**" not in listed]
    if missing:
        raise SystemExit(f"not in the analyzer's list: {', '.join(missing)}")
    requests = [r for r in CORPUS if args.only is None or r.expected in args.only.split(",")]
    if args.dry_run:
        print(listed)
        for request in requests:
            print(json.dumps(asdict(request), ensure_ascii=False))
        return 0
    started = time.perf_counter()
    rows = await _measure(parse_families(args.models), requests, args.reps, args.budget_eur)
    report = {
        "totals": totals(rows),
        "cost_eur": round(sum(row.cost_eur for row in rows), 4),
        "cost_usd": round(sum(row.cost_usd for row in rows), 4),
        "seconds": round(time.perf_counter() - started, 1),
        "rows": [asdict(row) for row in rows],
    }
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_summary(rows))
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        help="provider:model[@level],... (default: the instance's own analyzer slot)",
    )
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument(
        "--only", help="Comma-separated expected skills to ask (default: the whole corpus)"
    )
    parser.add_argument("--budget-eur", type=float, default=0.20, help="Stop past this spend (EUR)")
    parser.add_argument(
        "--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR, help="System skills directory"
    )
    parser.add_argument("--out", type=Path, help="Write the JSON report here")
    parser.add_argument("--dry-run", action="store_true", help="Print what is asked, ask nothing")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
