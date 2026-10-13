"""Seed a synthetic persona into the PROOF account and measure what the portrait publishes.

A MEASUREMENT, never a gate, and never on anyone's account: it refuses every
account whose e-mail is not under ``proof-lia.dev``, refuses an Anthropic
consolidation slot, and removes what it seeded. It runs the real
``consolidate_journals_for_user`` (manual, so the scheduler's pacing does not
apply) and reads what the run wrote on the user row — claims, placements,
facets, omitted claims, characters, proxy tokens, cost — and three deterministic
oracles over the stored claims (restatement, enumeration, source crossing), so
the same script measures the pipeline before and after a change, on the same rows.

The persona is seeded INERT (measured 2026-10-13): no background worker may act on
it while it lives. A ticket LIA holds is not runnable before the far future, the
routines and reminders are due after the seed's life, and the account's interest
notifications and heartbeat are off (restored at teardown) — at every earlier seed
the dev workboard runner executed the « todo » ticket on the dev slots, a paid
agent turn nobody had budgeted, and its moves made two consolidations ``stale``.
None of those fields is portrait material: the rendered sections are unchanged.

``portrait_corpus.json`` beside this script is INVENTED: a persona written for
the measurement, nothing of anyone's.

Usage (inside the API container, ``PYTHONPATH=/app``)::

    python scripts/journals/measure_portrait.py --seed --runs 2 \\
        --state /tmp/portrait_seed.json --report /tmp/portrait_baseline.json
    python scripts/journals/measure_portrait.py --teardown --state /tmp/portrait_seed.json
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

from src.infrastructure.database.registry import import_all_models

import_all_models()

# The application imports the agents services before the journals (the HITL
# chain reaches back into the consolidation); a script must do the same.
importlib.import_module("src.domains.agents.services")

from sqlalchemy import delete, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.core.llm_config_helper import get_llm_config_for_agent  # noqa: E402
from src.domains.bookmarks.indexing import discard_index, unlink_quietly  # noqa: E402
from src.domains.bookmarks.models import MessageBookmark  # noqa: E402
from src.domains.habits.models import UserHabit, UserHabitProfile  # noqa: E402
from src.domains.habits.rhythm import ClaimedWindow, ClassRhythm, RhythmProfile  # noqa: E402
from src.domains.interests.models import UserInterest  # noqa: E402
from src.domains.journals.consolidation_output import (  # noqa: E402
    content_words,
    item_words,
)
from src.domains.journals.consolidation_service import (  # noqa: E402
    consolidate_journals_for_user,
)
from src.domains.journals.models import JournalEntry  # noqa: E402
from src.domains.memories.models import Memory  # noqa: E402
from src.domains.open_loops.models import OpenLoop  # noqa: E402
from src.domains.relations.debrief.models import RelationDebrief  # noqa: E402
from src.domains.relations.debrief.schemas import RELATION_DEBRIEF_BODY_VERSION  # noqa: E402
from src.domains.reminders.models import Reminder  # noqa: E402
from src.domains.scheduled_actions.models import ScheduledAction  # noqa: E402
from src.domains.users.models import User  # noqa: E402
from src.domains.workboard.models import WorkboardTicket  # noqa: E402
from src.infrastructure.database.session import get_db_context  # noqa: E402
from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter  # noqa: E402

PROOF_DOMAIN = "proof-lia.dev"
#: How far a seeded ticket, routine or reminder is put out of every worker's reach.
INERT_FOR = timedelta(days=365)
PROOF_ID_PREFIX = "d7db1a08"
SEED_TAG = "portrait-measure"
CORPUS = Path(__file__).with_name("portrait_corpus.json")
MODELS: dict[str, type[Any]] = {
    "memories": Memory,
    "interests": UserInterest,
    "habits": UserHabit,
    "journal_entries": JournalEntry,
    "relation_debriefs": RelationDebrief,
    "open_loops": OpenLoop,
    "workboard": WorkboardTicket,
    "routines": ScheduledAction,
    "reminders": Reminder,
    "bookmarks": MessageBookmark,
}


def _ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def _proof_user(db: AsyncSession) -> User:
    """The proof account, and nothing else: an owner's row is refused."""
    rows = (await db.execute(select(User).where(User.email.like(f"%@{PROOF_DOMAIN}")))).scalars()
    user = next((row for row in rows if str(row.id).startswith(PROOF_ID_PREFIX)), None)
    if user is None:
        raise SystemExit("No proof account (e-mail under proof-lia.dev, id d7db1a08…) — refusing")
    return user


def _refuse_anthropic() -> None:
    cfg = get_llm_config_for_agent(settings, "journal_consolidation")
    if cfg.provider == "anthropic":
        raise SystemExit("journal_consolidation runs on Anthropic here — refusing to spend")


def _rhythm(spec: dict[str, Any]) -> dict[str, Any]:
    def _class(windows: list[list[int]]) -> ClassRhythm:
        claimed = tuple(ClaimedWindow(start_hour=a, end_hour=b, presence=0.8) for a, b in windows)
        bins = tuple(0.8 if any(a <= h < b for a, b in windows) else 0.1 for h in range(24))
        return ClassRhythm(verdict="windows", windows=claimed, n_eff=20.0, bin_presence=bins)

    return RhythmProfile(
        weekday=_class(spec["weekday"]),
        weekend=_class(spec["weekend"]),
        active_days_fraction=float(spec["active_days_fraction"]),
        sparse=False,
    ).to_payload()


async def _add(db: AsyncSession, created: dict[str, list[str]], key: str, row: Any) -> None:
    db.add(row)
    await db.flush()
    created[key].append(str(row.id))


async def seed(state_path: Path) -> None:
    """Write the corpus into the proof account and remember every row written."""
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    created: dict[str, list[str]] = {key: [] for key in MODELS}
    async with get_db_context() as db:
        user = await _proof_user(db)
        uid = user.id
        preexisting_entries = [
            str(row_id)
            for row_id in (
                await db.execute(select(JournalEntry.id).where(JournalEntry.user_id == uid))
            ).scalars()
        ]
        now = datetime.now(UTC)
        for m in corpus["memories"]:
            await _add(
                db,
                created,
                "memories",
                Memory(
                    user_id=uid,
                    content=m["content"],
                    category=m["category"],
                    emotional_weight=m["emotional_weight"],
                    trigger_topic=SEED_TAG,
                    usage_nuance="measurement",
                    importance=m["importance"],
                    pinned=m["pinned"],
                    char_count=len(m["content"]),
                    created_at=_ago(m["days_ago"]),
                ),
            )
        for i in corpus["interests"]:
            await _add(
                db,
                created,
                "interests",
                UserInterest(
                    user_id=uid,
                    topic=i["topic"],
                    category=i["category"],
                    subject=i.get("subject"),
                    positive_signals=i["positive_signals"],
                    negative_signals=i["negative_signals"],
                    status="active",
                    last_mentioned_at=_ago(i["days_ago"]),
                ),
            )
        existing = (
            await db.execute(select(UserHabitProfile).where(UserHabitProfile.user_id == uid))
        ).scalar_one_or_none()
        previous_profile: dict[str, Any] | None = None
        if existing is not None:
            previous_profile = {
                "payload": existing.payload,
                "computed_at": existing.computed_at.isoformat(),
                "source_max_created_at": (
                    existing.source_max_created_at.isoformat()
                    if existing.source_max_created_at
                    else None
                ),
            }
            existing.payload = _rhythm(corpus["habits"]["rhythm"])
            existing.computed_at = now
            existing.source_max_created_at = now
        else:
            db.add(
                UserHabitProfile(
                    user_id=uid,
                    payload=_rhythm(corpus["habits"]["rhythm"]),
                    computed_at=now,
                    source_max_created_at=now,
                )
            )
        await db.flush()
        created["habits"].append(f"profile:{uid}")
        for h in corpus["habits"]["recurring"]:
            await _add(
                db,
                created,
                "habits",
                UserHabit(
                    user_id=uid,
                    kind="recurring_request",
                    key=h["key"],
                    payload={
                        "shape": h["shape"],
                        "trigger_hour": h["trigger_hour"],
                        "usual_intent": h["usual_intent"],
                    },
                    positive_signals=5,
                    negative_signals=0,
                    status="active",
                    last_observed_at=now,
                    muted_until_reproof=False,
                ),
            )
        for e in corpus["journal_entries"]:
            await _add(
                db,
                created,
                "journal_entries",
                JournalEntry(
                    user_id=uid,
                    theme=e["theme"],
                    title=e["title"],
                    content=e["content"],
                    mood="reflective",
                    status="active",
                    source="conversation",
                    session_id=SEED_TAG,
                    char_count=len(e["content"]),
                    search_hints=e.get("search_hints") or None,
                    confidence=e["confidence"],
                    evidence_count=e["evidence_count"],
                    contradiction_count=e["contradiction_count"],
                    level=e["level"],
                    revision=1,
                ),
            )
        for d in corpus["relation_debriefs"]:
            await _add(
                db,
                created,
                "relation_debriefs",
                RelationDebrief(
                    user_id=uid,
                    name_key=d["display_name"].lower(),
                    display_name=d["display_name"],
                    generated_for=(now - timedelta(days=d["days_ago"])).date(),
                    generated_at=_ago(d["days_ago"]),
                    language="fr",
                    scope_digest=SEED_TAG,
                    evidence_digest=SEED_TAG,
                    sections_used=["messages"],
                    unavailable=[],
                    state="ready",
                    body={
                        "version": RELATION_DEBRIEF_BODY_VERSION,
                        "headline": d["headline"],
                        "where_we_stand": d["where_we_stand"],
                        "open_points": d["open_points"],
                        "suggested_next_step": None,
                        "notable_facts": [],
                    },
                ),
            )
        for o in corpus["open_loops"]:
            await _add(
                db,
                created,
                "open_loops",
                OpenLoop(
                    user_id=uid,
                    subject=o["subject"],
                    counterparty=o["counterparty"],
                    direction=o["direction"],
                    due_hint=now + timedelta(days=o["due_in_days"]),
                    source_kind="conversation",
                    status="open",
                    nudge_count=0,
                ),
            )
        for t in corpus["workboard"]:
            await _add(
                db,
                created,
                "workboard",
                WorkboardTicket(
                    owner_user_id=uid,
                    title=t["title"],
                    description=t["description"],
                    status=t["status"],
                    priority=t["priority"],
                    due_at=now + timedelta(days=t["due_in_days"]),
                    assignee_kind=t["assignee_kind"],
                    position=0,
                    created_by="user",
                    status_changed_at=now,
                    execution_mode="react",
                    # The workboard runner takes a « todo » ticket LIA holds: never this one.
                    run_not_before=now + INERT_FOR,
                ),
            )
        for r in corpus["routines"]:
            await _add(
                db,
                created,
                "routines",
                ScheduledAction(
                    user_id=uid,
                    title=r["title"],
                    action_prompt=r["action_prompt"],
                    recurrence=r["recurrence"],
                    user_timezone=corpus["timezone"],
                    next_trigger_at=now + INERT_FOR,  # rendered as its recurrence
                    trigger_kind="time",
                    is_enabled=True,
                    status="active",
                    execution_mode="react",
                ),
            )
        for r in corpus["reminders"]:
            await _add(
                db,
                created,
                "reminders",
                Reminder(
                    user_id=uid,
                    content=r["content"],
                    original_message=r["original_message"],
                    recurrence=r["recurrence"],
                    # A repeating reminder renders its recurrence, a one-off its instant: the
                    # first is put out of reach, the second stays where the corpus put it.
                    trigger_at=(
                        now + INERT_FOR
                        if r["recurrence"].get("freq") != "once"
                        else now + timedelta(days=r["trigger_in_days"], hours=1)
                    ),
                    user_timezone=corpus["timezone"],
                    status="pending",
                    retry_count=0,
                ),
            )
        for b in corpus["bookmarks"]:
            await _add(
                db,
                created,
                "bookmarks",
                MessageBookmark(
                    user_id=uid,
                    content=b["content"],
                    request_content=b["request_content"],
                    answered_at=_ago(b["days_ago"]),
                ),
            )
        # What the seed overwrites on the account is saved first and restored at teardown.
        account = await db.get(User, uid)
        assert account is not None
        previous_account = {name: _jsonable(getattr(account, name)) for name in ACCOUNT_FIELDS}
        await db.execute(
            update(User)
            .where(User.id == uid)
            .values(
                journals_enabled=True,
                memory_enabled=True,
                habits_enabled=True,
                relation_debrief_enabled=True,
                # Proactive sweeps only; the interests SOURCE is not gated on this flag.
                interests_enabled=False,
                heartbeat_enabled=False,
                language=corpus["language"],
                timezone=corpus["timezone"],
                journal_portrait_full=None,
                journal_portrait_brief=None,
                journal_portrait_compiled_at=None,
                journal_portrait_sources=None,
                journal_last_attempted_at=None,
                journal_last_cost_eur=None,
                journal_consolidation_held_until=None,
                journal_consolidation_owner=None,
            )
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    state_path.write_text(
        json.dumps(
            {
                "user_id": str(uid),
                "created": created,
                "previous_profile": previous_profile,
                "previous_account": previous_account,
                "preexisting_entries": preexisting_entries,
            }
        ),
        encoding="utf-8",
    )
    print(f"seeded {sum(len(v) for v in created.values())} rows for {str(uid)[:8]}")


def _owner_of(model: type[Any]) -> Any:
    """The column naming the account a row belongs to (tickets name their owner)."""
    return getattr(model, "owner_user_id", None) or model.user_id


async def teardown(state_path: Path) -> None:
    """Remove exactly what the seed wrote, and the portrait it produced."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    uid = UUID(state["user_id"])
    if not str(uid).startswith(PROOF_ID_PREFIX):
        raise SystemExit("The state file names an account that is not the proof account")
    files: list[Path | None] = []
    async with get_db_context() as db:
        for key, ids in state["created"].items():
            model = MODELS[key]
            plain = [UUID(i) for i in ids if not i.startswith("profile:")]
            if key == "bookmarks" and plain:
                # The reconciliation may have projected a kept answer into the knowledge
                # space: its own door removes the projection (2026-10-13).
                kept = await db.execute(
                    select(MessageBookmark).where(
                        MessageBookmark.id.in_(plain), MessageBookmark.user_id == uid
                    )
                )
                files.extend([await discard_index(db, row) for row in kept.scalars()])
            if plain:
                # The owner predicate makes a tampered state file harmless to other accounts.
                await db.execute(delete(model).where(model.id.in_(plain), _owner_of(model) == uid))
            if any(i.startswith("profile:") for i in ids):
                previous = state.get("previous_profile")
                if previous is None:
                    await db.execute(
                        delete(UserHabitProfile).where(UserHabitProfile.user_id == uid)
                    )
                else:
                    await db.execute(
                        update(UserHabitProfile)
                        .where(UserHabitProfile.user_id == uid)
                        .values(
                            payload=previous["payload"],
                            computed_at=datetime.fromisoformat(previous["computed_at"]),
                            source_max_created_at=(
                                datetime.fromisoformat(previous["source_max_created_at"])
                                if previous["source_max_created_at"]
                                else None
                            ),
                        )
                        .execution_options(synchronize_session=False)
                    )
        preexisting = state.get("preexisting_entries")
        if preexisting is not None:
            # The runs' own maintenance may have CREATED entries: every entry of the
            # proof account that the seed did not find goes with the seed's.
            keep = [UUID(i) for i in preexisting]
            await db.execute(
                delete(JournalEntry).where(
                    JournalEntry.user_id == uid, JournalEntry.id.not_in(keep)
                )
            )
        previous_account = state.get("previous_account")
        if previous_account is None:
            # A state file from before the account snapshot: clear the portrait alone.
            values = dict.fromkeys(
                (
                    "journal_portrait_full",
                    "journal_portrait_brief",
                    "journal_portrait_compiled_at",
                    "journal_portrait_sources",
                )
            )
        else:
            values = {name: _restored(name, previous_account[name]) for name in ACCOUNT_FIELDS}
        await db.execute(
            update(User)
            .where(User.id == uid)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    for path in files:  # the projection's files, after the commit
        await asyncio.to_thread(unlink_quietly, path)
    print("teardown done")


#: The account columns the seed overwrites; each is restored verbatim at teardown.
ACCOUNT_FIELDS = (
    "journals_enabled",
    "memory_enabled",
    "habits_enabled",
    "relation_debrief_enabled",
    "interests_enabled",
    "heartbeat_enabled",
    "language",
    "timezone",
    "journal_portrait_full",
    "journal_portrait_brief",
    "journal_portrait_compiled_at",
    "journal_portrait_sources",
    "journal_last_attempted_at",
    "journal_last_cost_eur",
    "journal_consolidation_held_until",
    "journal_consolidation_owner",
)

#: The datetime columns among them (JSON carries them as ISO 8601 strings).
_DATETIME_FIELDS = frozenset(
    {
        "journal_portrait_compiled_at",
        "journal_last_attempted_at",
        "journal_consolidation_held_until",
    }
)


def _jsonable(value: Any) -> Any:
    """A column value as the state file carries it."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _restored(name: str, value: Any) -> Any:
    """The column value back from the state file."""
    if value is None:
        return None
    if name in _DATETIME_FIELDS:
        return datetime.fromisoformat(value)
    if name == "journal_last_cost_eur":
        return Decimal(value)
    return value


def _tokens(text: str | None) -> int:
    return OpenAITokenCounter().count(text or "", "gpt-4o")


def _placement(claim: dict[str, Any]) -> str:
    if "placement" in claim:
        return str(claim["placement"])
    return "brief" if claim.get("in_brief") else "full"


def _content_words(text: str) -> set[str]:
    """The admission's own reading of a text's content words (ONE implementation)."""
    return content_words(text or "")


def _support_words(support: dict[str, Any]) -> set[str]:
    """The content words of a stored support: its canonical quote, labels and date removed."""
    return item_words(str(support.get("quote") or ""))


#: Content words a sentence shares with a cited item for the item to read as NAMED.
_ITEM_NAMED_WORDS = 2


def _names_three_items(sentence: str, items: list[set[str]]) -> bool:
    """Whether one sentence carries the words of three cited items or more (a list)."""
    words = _content_words(sentence)
    return sum(len(words & item) >= _ITEM_NAMED_WORDS for item in items) >= 3


def _oracles(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Four deterministic readings of « analysis or inventory » (2026-10-12 b, c).

    restatement_ratio: share of claims whose content words are mostly those of ONE
    cited item (overlap >= 0.5, read on the stored canonical quotes — a stored
    support carries `quote`, never `item_id`). enumerations: claims holding a
    sentence with three commas or more. mean_source_kinds / multi_source_share:
    how many kinds of record one reading crosses. listed_grounds: share of claims
    holding a sentence that names three of their cited items or more — a pattern
    followed by the list of what grounds it, which the comma count cannot tell
    from dense analytical prose (2026-10-12 c).
    """
    restated = enumerations = multi = listed = 0
    kinds_total = 0
    for claim in claims:
        words = _content_words(str(claim.get("text", "")))
        best = 0.0
        kinds: set[str] = set()
        for support in claim.get("supports", []):
            source = str(support.get("source", ""))
            kinds.add(source.split(":")[0])
            item_words = _support_words(support)
            if words and item_words:
                best = max(best, len(words & item_words) / len(words))
        restated += best >= 0.5
        items = [_support_words(support) for support in claim.get("supports", [])]
        listed += any(
            _names_three_items(sentence, items)
            for sentence in re.split(r"(?<=[.!?])\s+", str(claim.get("text", "")))
        )
        enumerations += any(
            s.count(",") >= 3 for s in re.split(r"(?<=[.!?])\s+", str(claim.get("text", "")))
        )
        multi += len(kinds) >= 2
        kinds_total += len(kinds)
    n = len(claims) or 1
    return {
        "restatement_ratio": round(restated / n, 2),
        "listed_grounds": round(listed / n, 2),
        "enumerations": enumerations,
        "mean_source_kinds": round(kinds_total / n, 2),
        "multi_source_share": round(multi / n, 2),
    }


async def _snapshot(uid: UUID) -> dict[str, Any]:
    async with get_db_context() as db:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        prov = (
            user.journal_portrait_sources if isinstance(user.journal_portrait_sources, dict) else {}
        )
        claims = prov.get("claims") or []
    oracles = _oracles(claims) if claims else {}
    async with get_db_context() as db:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        return {
            "status": user.journal_last_attempt_status,
            "full": user.journal_portrait_full,
            "brief": user.journal_portrait_brief,
            "full_chars": len(user.journal_portrait_full or ""),
            "brief_chars": len(user.journal_portrait_brief or ""),
            "full_tokens": _tokens(user.journal_portrait_full),
            "brief_tokens": _tokens(user.journal_portrait_brief),
            "published": len(claims),
            "placements": [_placement(c) for c in claims],
            "facets": [c.get("facet") for c in claims],
            "support_kinds": sorted(
                {s["source"].split(":")[0] for c in claims for s in c.get("supports", [])}
            ),
            "omitted_claims": prov.get("omitted_claims"),
            # The stored claims, supports included: a measurement re-read at no cost.
            "claims": claims,
            "sources": prov.get("sources"),
            "cost_eur": float(user.journal_last_cost_eur or 0),
            **oracles,
        }


async def _reset_for_next_run(uid: UUID) -> None:
    """The next run must compile afresh: no current provenance, no pacing stamp."""
    async with get_db_context() as db:
        await db.execute(
            update(User)
            .where(User.id == uid)
            .values(
                journal_portrait_full=None,
                journal_portrait_brief=None,
                journal_portrait_compiled_at=None,
                journal_portrait_sources=None,
                journal_last_attempted_at=None,
                journal_last_cost_eur=None,
            )
            .execution_options(synchronize_session=False)
        )
        await db.commit()


async def measure(state_path: Path, runs: int, report_path: Path) -> None:
    """Run the real consolidation N times and keep what each run published."""
    # Without the caches the slots fall back on LLM_DEFAULTS (the lifespan's own
    # order: pricing, then configuration) — the trap every harness meets once.
    from src.infrastructure.startup.caches import init_config_caches, init_pricing_caches
    from src.infrastructure.startup.registries import _install_portrait_sources

    await init_pricing_caches()
    await init_config_caches()
    # The sources install themselves through the boot step, never by import alone
    # (ADR-270): without it the consolidation reads an EMPTY seam.
    _install_portrait_sources()
    _refuse_anthropic()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    uid = UUID(state["user_id"])
    if not str(uid).startswith(PROOF_ID_PREFIX):
        raise SystemExit("The state file names an account that is not the proof account")
    results = []
    for index in range(runs):
        started = monotonic()
        await consolidate_journals_for_user(uid, None, None, "fr", False, manual=True)
        snap = await _snapshot(uid)
        snap["duration_s"] = round(monotonic() - started, 1)
        snap["run"] = index + 1
        results.append(snap)
        print(
            json.dumps(
                {k: v for k, v in snap.items() if k not in ("full", "brief")}, ensure_ascii=False
            )
        )
        await _reset_for_next_run(uid)
    cfg = get_llm_config_for_agent(settings, "journal_consolidation")
    report_path.write_text(
        json.dumps(
            {"slot": {"provider": cfg.provider, "model": cfg.model}, "runs": results},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"report written: {report_path}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed", action="store_true", help="write the corpus into the proof account"
    )
    parser.add_argument("--teardown", action="store_true", help="remove what --seed wrote")
    parser.add_argument("--runs", type=int, default=0, help="consolidations to run and measure")
    parser.add_argument("--state", type=Path, required=True, help="where the seeded ids are kept")
    parser.add_argument("--report", type=Path, default=Path("/tmp/portrait_report.json"))
    args = parser.parse_args(argv)
    if args.seed and args.state.exists():
        raise SystemExit(
            f"{args.state} exists: tear the previous seed down first, or a second seed "
            "would overwrite the account values it must restore"
        )
    asyncio.run(_phases(args))
    return 0


async def _phases(args: argparse.Namespace) -> None:
    """Seed, measure and tear down in ONE event loop.

    The engine's pool belongs to the loop that opened its connections: one
    `asyncio.run` per phase terminated the seed's connections on a closed loop and
    failed the next phase's first query (measured 2026-10-12 c).
    """
    if args.seed:
        await seed(args.state)
    if args.runs:
        await measure(args.state, args.runs, args.report)
    if args.teardown:
        await teardown(args.state)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
