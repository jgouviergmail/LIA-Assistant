# Portrait: whole material, real brief — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The compiled user portrait is fed from every record LIA keeps about the person, read whole; its brief is a synthesis written as its own claims; the budgets bound the publication after the review; a journal change marks the portrait stale instead of wiping it — all measured on dev before the definitive surfaces are written.

**Architecture:** The seam `domains/shared/portrait_sources.py` keeps its closed vocabulary and grows from four to nine sources, each domain installing a reader whose only bound is the slot's context window; `journals/portrait_sources.py` assembles them under one stated window share. `consolidation_output.py` carries a `placement` per claim and packs each format from its own claims AFTER `portrait_review.py` approved them. `lifecycle.py` keeps the words on a change and `portrait_read.py` serves them with a `stale` flag. A measurement script seeds a synthetic persona into the proof account on dev and runs the real consolidation, before and after.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy 2 / Pydantic 2 (backend), pytest (`asyncio_mode = auto`), Next.js 16 / React 19 / vitest (frontend), Task, Docker dev stack (`lia-api-dev`, `lia-postgres-dev`).

**Spec:** `docs/superpowers/specs/2026-10-12-portrait-whole-material-and-real-brief.md`

## Global Constraints

- **No git action by the executor**: no commit, no branch, no stash — the owner commits. Every "Commit" step of the skill template is replaced by "Run the task's gate".
- **No Anthropic API call anywhere in the measurement** (`feedback_no_anthropic_api_spend`): the dev `journal_consolidation` slot is `deepseek-flash`; the harness refuses to run if `get_llm_config_for_agent(settings, "journal_consolidation").provider == "anthropic"`.
- **Measurement budget: at most 0.50 € for the whole simulation**, announced to the owner; the proof account only (`id` starts with `d7db1a08`, e-mail under `proof-lia.dev`), never the owner's.
- **Nothing of anyone's in the repository**: the corpus is invented French about an invented person; no real locality, name, employer or incident (`reference_infra_denylist_personal_locality`).
- Backend strings a person reads go through the i18n tables in six languages (`en, fr, de, es, it, zh`); frontend keys in `apps/web/locales/{lang}/translation.json` with strict parity; what only the MODEL reads is technical English (ADR-323).
- Prompt text lives in `apps/api/src/domains/agents/prompts/v1/*.txt`; every `{placeholder}` has a producer; one-line scaffolds live in `journal_portrait_source_lines.txt` and are read through `portrait_lines()` (ADR-284).
- A reader never raises, reads its gates at call time, answers `used | empty | disabled | unavailable` with an exact total (ADR-292).
- No `AsyncSession` shared across tasks; readers run one at a time; no session held across a network call (ADR-304).
- All datetimes UTC-aware; the person's local day through `resolve_user_timezone`.
- Logs above DEBUG carry facts, never a person's words (ADR-317).
- MyPy strict, Black 100, Ruff; a file stays under 600 logical SLOC (`scripts/audit/measure_sloc.py`); touched frozen files only shrink.
- Settings read from environment; a tunable number lives in `core/constants.py` + `core/config/journals.py` + `.env.example` + `.env.prod.example` (and the local `.env` / `.env.prod`, which the owner keeps aligned — change the KEYS there too, never copy an empty value).
- `AGENTS.md` is generated: edit `CLAUDE.md`, then `task docs:sync-agents`.

## Review Focus

1. **An account whose material exceeds the window share** (a 128 000-token slot and thousands of memories): the last sections lose items from their end, the provenance states `used` of `total` with `reason: over_budget`, nothing is cut mid-item — pinned in Task 5 (`test_the_window_share_cuts_the_last_sections_at_item_boundaries_and_says_so`).
2. **A brief claim the model forgot to mark** (every claim `placement: full`): the brief is `None`, the full is published, nothing invents a brief — pinned in Task 7 (`test_no_brief_claims_leaves_the_brief_empty`).
3. **A reviewed set larger than the full budget** (ten approved paragraphs, 300 tokens): the publication keeps the first that fit WHOLE in the model's order, the provenance counts the rest in `omitted_claims` — pinned in Task 7 (`test_publication_packs_approved_claims_in_order_under_the_budget`).
4. **A stale portrait whose supports were deleted by the person** (lever 1): the words are served with `stale: true` and their date until the next consolidation, never silently as current — pinned in Task 11 (`test_a_journal_change_marks_the_portrait_stale_without_wiping_it`).
5. **A new source the person switched off** (open loops capability off, bookmarks disabled): the reader answers `disabled`, the section is absent, the provenance says so, and the freshness probe's `allowed` keeps the gate honest — pinned per reader in Task 3 (`test_a_closed_gate_answers_disabled`).

---

**Status (2026-10-12, 15:45):** Phase 1 DONE and measured — Tasks 1 to 9 executed natively;
two amendments found by the measurement and applied (spec D7): a provisional claim's facet is
REPAIRED and an unprovable claim is DROPPED and counted (never fatal to the batch), and the
review prompt judges GROUNDED synthesis instead of strict entailment. The report is
`docs/superpowers/plans/2026-10-12-portrait-whole-material-simulation.md`.

**Status (2026-10-12, 19:00):** Phase 2 DONE (Tasks 10 to 14) under the owner's decisions
« budget 400, the synthesis is complete » (the budgets are targets; every verified claim is
published). The cold adversarial review (Task 14) returned 18 findings; the ones in this lot
were fixed and their tests written: the removal door was blocked by the former wipe check
(erasure now WITHDRAWS the claims a removed entry supported — `withdraw_journal_supports`);
a batch whose every claim was dropped wiped the words and reported success (it now keeps
them, `no_op`); a pass that compiled nothing re-stamped the old words as current (the
previous provenance is kept whole); a claim the batch rule excluded could reach the words
unreviewed (nothing admitted means nothing publishable); the bookmark excerpt's ellipsis
made every long kept answer invisible to the model (no marker, the bound in the header; an
item line is cut at `PORTRAIT_ITEM_MAX_CHARS`, never dropped); the review ceiling raised
after the paid generation (`fit_portrait_review`, `reviewed_count`); a repeating reminder's
next instant reopened the consolidation at every firing; the boot installed five sources
four times; the assembler re-tokenised the section per item (bisection) and reported a
budget drop as « could not be read »; the card now names the cut sources and starts on the
format it has; German dative and Italian agreement fixed; the harness restores the account
columns it overwrites. Left as found, in writing (ADR-343 « Left open »): the freshness
probes' cost at every ambient read, the habit payload probe and the debriefs' daily expiry
(both predate the lot), the deploy's `.env.encrypted` copies.

**Status (2026-10-12, 21:30):** the owner read the measured output and named the objective:
a GLOBAL ANALYTICAL synthesis fed by all the sources, never a reformulation. The rupture was
dated (commit `499c4cecc`, v3.0.0, 2026-10-11, ADR-335 to 338, none naming the portrait: the
v1.45 « faceted synthesis of the living person » replaced by « describe only what the cited
evidence supports »). The v1.45 contract is restored on nine sources (STEP 7 rewritten, seven
facets, `PORTRAIT_CLAIM_SUPPORTS_MAX` 40, policy `analytical_reading_v5`), measured on the proof
account (five runs, 0.128 €, harness oracles `restatement_ratio` / `enumerations` /
`mean_source_kinds`): the generation wrote readings (0 restatement, 0 enumeration, 2 to 2.3
record kinds per reading) and the semantic review rejected 70 to 80 % of them after two
recalibrations. With the owner's agreement the review is REMOVED as a publication gate
(`portrait_review.py`, its prompt, receipt, ceiling and tests deleted; `admit_portrait_claims`
is the deterministic admission; one model call per consolidation again); ADR-343 § 4-6 and the
map texts rewritten in six languages. Left for a lot of its own: the maintenance contract that
voids a whole paid run for one invalid L2 action.

**Status (2026-10-12, 22:30):** the cold review of the removal lot returned 14 findings, the
real ones fixed: the harness oracle read an `item_id` stored claims never carry (it reads the
canonical quotes now); the six-language approval texts and the application specs still named a
« portrait review »; the prompt promised a verifier; one unreadable claim voided the whole paid
run through the payload schema (claims are read one by one, repaired or rejected alone,
`rejected_claims`); a brief alone replaced a good full with nothing; deterministic guards now
drop a paragraph restating one item, a name the evidence carries, a figure, an address or a date
in the prose; only an action that actually changed its entry bars the claims citing it; the
residual ellipsis rule of `_section_proof` is gone; docs and comments aligned (ADR-343 § 4-6
and 8, JOURNALS.md, CLAUDE.md, ADR-079 supersession note).

# Phase 1 — Build the candidate and MEASURE it (ends with the owner's validation)

### Task 1: The measurement harness and its synthetic corpus (run the BASELINE before any code changes)

**Files:**
- Create: `apps/api/scripts/journals/__init__.py` (empty)
- Create: `apps/api/scripts/journals/portrait_corpus.json`
- Create: `apps/api/scripts/journals/measure_portrait.py`
- Create: `apps/api/tests/unit/scripts/test_portrait_corpus.py`
- Modify: `Taskfile.yml` (after `react:recovery:measure`, around line 652)

**Interfaces:**
- Consumes: `src.domains.journals.consolidation_service.consolidate_journals_for_user(user_id, personality_instruction, personality_code, user_language, consolidation_with_history, ..., manual=True)`; `src.domains.users.models.User`; the ORM models of memories, interests, habits (`UserHabit`, `UserHabitProfile`), relation debriefs (`RelationDebrief`), open loops, workboard tickets, scheduled actions, reminders, bookmarks; `src.domains.habits.rhythm.RhythmProfile`.
- Produces: `python scripts/journals/measure_portrait.py --seed --runs N --state /tmp/portrait_seed.json --report /tmp/portrait_report.json`, `--teardown --state …`; a report JSON `{"runs": [...], "corpus": {...}, "slot": {...}}`.

- [ ] **Step 1: Write the corpus** — `apps/api/scripts/journals/portrait_corpus.json`. Invented French persona (« une personne qui restaure des meubles anciens le week-end et coordonne une petite équipe de support informatique en semaine »). Shape, every list sized as written:

```json
{
  "language": "fr",
  "timezone": "Europe/Paris",
  "memories": [
    {"content": "Je préfère qu'on me donne les chiffres avant les explications.", "category": "personal", "emotional_weight": 1, "importance": 0.8, "pinned": true, "days_ago": 40}
    // 60 entries: 20 about work habits, 15 about family rhythm (invented first names only: Noé, Lila, Sacha), 10 about tastes, 10 about health routine, 5 pinned principles; days_ago 1..180
  ],
  "interests": [
    {"topic": "restauration de meubles anciens", "category": "hobby", "subject": "vernis au tampon", "positive_signals": 14, "negative_signals": 1, "days_ago": 3}
    // 20 entries, categories among hobby|tech|culture|sport|other, weights from +18 to -3
  ],
  "habits": {
    "rhythm": {"weekday": [[7, 9], [20, 22]], "weekend": [[9, 12]], "active_days_fraction": 0.74},
    "recurring": [
      {"key": "weekly_team_recap", "shape": "every Friday afternoon", "trigger_hour": 16.5, "usual_intent": "summarise the support tickets of the week"},
      {"key": "sunday_workshop_plan", "shape": "Sunday morning", "trigger_hour": 9.0, "usual_intent": "plan the week-end workshop session"}
    ]
  },
  "journal_entries": [
    {"theme": "user_observations", "title": "Chiffres d'abord", "content": "WHEN presenting a technical recommendation -> DO give the measured figures first and the explanation after BECAUSE the person asks for numbers before prose.", "level": "L1", "confidence": "medium", "evidence_count": 3, "contradiction_count": 0, "search_hints": ["chiffres", "recommandation"]}
    // 45 entries: 8 L0 low, 28 L1 medium, 4 L1 contradicted (contradiction_count 1), 4 L2 medium, 1 L3 high; themes spread over the four
  ],
  "relation_debriefs": [
    {"display_name": "Noé", "headline": "Un binôme de confiance au support, sollicité pour les escalades.", "where_we_stand": "Les échanges sont fréquents et tournent autour des escalades clients ; la dernière date de cette semaine.", "open_points": ["Répartition des astreintes de novembre"], "days_ago": 1}
    // 3 debriefs, days_ago 1..5
  ],
  "open_loops": [
    {"subject": "Renvoyer le devis du vernis à l'ébéniste", "counterparty": "l'ébéniste", "direction": "user_owes", "due_in_days": 3}
    // 4 loops, two user_owes, two waiting_on_other
  ],
  "workboard": [
    {"title": "Préparer la grille d'astreintes de novembre", "description": "Compiler les disponibilités de l'équipe et proposer deux options.", "status": "in_progress", "priority": "high", "due_in_days": 6, "assignee_kind": "lia"}
    // 4 tickets, statuses todo|in_progress|waiting|done
  ],
  "routines": [
    {"title": "Résumé des tickets du vendredi", "action_prompt": "Résume les tickets de support ouverts cette semaine et signale ceux sans réponse depuis 48 h.", "recurrence": {"freq": "weekly", "byweekday": [5], "times": {"mode": "at", "at": [{"hour": 16, "minute": 30}]}, "anchor_date": "2026-09-04"}}
    // 3 routines
  ],
  "reminders": [
    {"content": "Appeler le fournisseur de vernis", "original_message": "Rappelle-moi d'appeler le fournisseur de vernis jeudi matin", "trigger_in_days": 2, "recurrence": {"freq": "once", "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]}, "anchor_date": "2026-10-14"}}
    // 3 reminders
  ],
  "bookmarks": [
    {"request_content": "Comment retirer un vernis au tampon sans abîmer le placage ?", "content": "Travaillez par petites zones avec de l'alcool à brûler sur un chiffon non pelucheux…", "days_ago": 12}
    // 3 bookmarks
  ]
}
```

Write the 60 / 20 / 45 / 3 / 4 / 4 / 3 / 3 items in full (invented, coherent with the persona). Every journal `content` under 800 characters; every memory under 400.

- [ ] **Step 2: Write the failing corpus test** — `apps/api/tests/unit/scripts/test_portrait_corpus.py`:

```python
"""The portrait measurement corpus is complete, invented and sized as declared."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).resolve().parents[3] / "scripts" / "journals" / "portrait_corpus.json"


def _corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_the_corpus_holds_every_source_at_its_declared_size() -> None:
    corpus = _corpus()
    assert corpus["language"] == "fr"
    assert len(corpus["memories"]) == 60
    assert len(corpus["interests"]) == 20
    assert len(corpus["habits"]["recurring"]) == 2
    assert len(corpus["journal_entries"]) == 45
    assert len(corpus["relation_debriefs"]) == 3
    assert len(corpus["open_loops"]) == 4
    assert len(corpus["workboard"]) == 4
    assert len(corpus["routines"]) == 3
    assert len(corpus["reminders"]) == 3
    assert len(corpus["bookmarks"]) == 3


def test_journal_entries_cover_the_eligibility_classes() -> None:
    entries = _corpus()["journal_entries"]
    levels = {(e["level"], e["confidence"], e["contradiction_count"] > 0) for e in entries}
    assert ("L0", "low", False) in levels
    assert ("L1", "medium", False) in levels
    assert ("L1", "medium", True) in levels
    assert ("L2", "medium", False) in levels
    assert ("L3", "high", False) in levels
    assert all(len(e["content"]) <= 800 for e in entries)


def test_the_corpus_names_people_by_a_first_name_alone_and_carries_no_contact_detail() -> None:
    # Invented, and checked structurally — never against a list of real names or
    # places, which would write them into the repository.
    corpus = _corpus()
    corpus.pop("timezone")  # an IANA zone names a city by construction
    for debrief in corpus["relation_debriefs"]:
        assert len(debrief["display_name"].split()) == 1
    text = json.dumps(corpus, ensure_ascii=False)
    assert "@" not in text
    assert re.search(r"\b\d{5}\b", text) is None  # a postcode
    assert re.search(r"(?:\+|\b0)\d[\d .-]{8,}\d", text) is None  # a phone number
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/scripts/test_portrait_corpus.py -v`
Expected: FAIL (file missing until Step 1 is complete, then PASS once the corpus is written — write the corpus to the counts above).

- [ ] **Step 4: Write the harness** — `apps/api/scripts/journals/measure_portrait.py`:

```python
"""Seed a synthetic persona into the PROOF account and measure what the portrait publishes.

A MEASUREMENT, never a gate, and never on anyone's account: it refuses every
account whose e-mail is not under ``proof-lia.dev``, refuses an Anthropic slot,
and removes what it seeded. It runs the real ``consolidate_journals_for_user``
(manual, so pacing does not apply) and reads what the run wrote on the user row
— claims, placements, review verdicts, characters, proxy tokens, cost — so the
same script measures the pipeline before and after a change.

Usage (inside the API container, PYTHONPATH=/app)::

    python scripts/journals/measure_portrait.py --seed --runs 2 \
        --state /tmp/portrait_seed.json --report /tmp/portrait_baseline.json
    python scripts/journals/measure_portrait.py --teardown --state /tmp/portrait_seed.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from src.infrastructure.database.registry import import_all_models

import_all_models()

from sqlalchemy import delete, select, update  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.core.llm_config_helper import get_llm_config_for_agent  # noqa: E402
from src.domains.bookmarks.models import MessageBookmark  # noqa: E402
from src.domains.habits.models import UserHabit, UserHabitProfile  # noqa: E402
from src.domains.habits.rhythm import ClaimedWindow, ClassRhythm, RhythmProfile  # noqa: E402
from src.domains.interests.models import UserInterest  # noqa: E402
from src.domains.journals.consolidation_service import consolidate_journals_for_user  # noqa: E402
from src.domains.journals.models import JournalEntry  # noqa: E402
from src.domains.memories.models import Memory  # noqa: E402
from src.domains.open_loops.models import OpenLoop  # noqa: E402
from src.domains.relations.debrief.models import RelationDebrief  # noqa: E402
from src.domains.reminders.models import Reminder  # noqa: E402
from src.domains.scheduled_actions.models import ScheduledAction  # noqa: E402
from src.domains.users.models import User  # noqa: E402
from src.domains.workboard.models import WorkboardTicket  # noqa: E402
from src.infrastructure.database.session import get_db_context  # noqa: E402
from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter  # noqa: E402

PROOF_DOMAIN = "proof-lia.dev"
CORPUS = Path(__file__).with_name("portrait_corpus.json")
MODELS: dict[str, type] = {
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


async def _proof_user(db: Any) -> User:
    user = (
        await db.execute(select(User).where(User.email.like(f"%@{PROOF_DOMAIN}")))
    ).scalars().first()
    if user is None or not str(user.id).startswith("d7db1a08"):
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


async def seed(state_path: Path) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    created: dict[str, list[str]] = {key: [] for key in MODELS}
    async with get_db_context() as db:
        user = await _proof_user(db)
        uid = user.id
        now = datetime.now(UTC)
        for m in corpus["memories"]:
            row = Memory(
                user_id=uid, content=m["content"], category=m["category"],
                emotional_weight=m["emotional_weight"], trigger_topic="portrait-measure",
                usage_nuance="measurement", importance=m["importance"], pinned=m["pinned"],
                char_count=len(m["content"]), created_at=_ago(m["days_ago"]),
            )
            db.add(row); await db.flush(); created["memories"].append(str(row.id))
        for i in corpus["interests"]:
            row = UserInterest(
                user_id=uid, topic=i["topic"], category=i["category"], subject=i.get("subject"),
                positive_signals=i["positive_signals"], negative_signals=i["negative_signals"],
                status="active", last_mentioned_at=_ago(i["days_ago"]),
            )
            db.add(row); await db.flush(); created["interests"].append(str(row.id))
        profile = UserHabitProfile(
            user_id=uid, payload=_rhythm(corpus["habits"]["rhythm"]), computed_at=now,
            source_max_created_at=now,
        )
        db.add(profile); await db.flush(); created["habits"].append(f"profile:{uid}")
        for h in corpus["habits"]["recurring"]:
            row = UserHabit(
                user_id=uid, kind="recurring_request", key=h["key"],
                payload={"shape": h["shape"], "trigger_hour": h["trigger_hour"], "usual_intent": h["usual_intent"]},
                positive_signals=5, negative_signals=0, status="active",
                last_observed_at=now, muted_until_reproof=False,
            )
            db.add(row); await db.flush(); created["habits"].append(str(row.id))
        for e in corpus["journal_entries"]:
            row = JournalEntry(
                user_id=uid, theme=e["theme"], title=e["title"], content=e["content"],
                mood="reflective", status="active", source="conversation",
                session_id="portrait-measure", char_count=len(e["content"]),
                search_hints=e.get("search_hints"), confidence=e["confidence"],
                evidence_count=e["evidence_count"], contradiction_count=e["contradiction_count"],
                level=e["level"], revision=1,
            )
            db.add(row); await db.flush(); created["journal_entries"].append(str(row.id))
        for d in corpus["relation_debriefs"]:
            row = RelationDebrief(
                user_id=uid, name_key=d["display_name"].lower(), display_name=d["display_name"],
                generated_for=(now - timedelta(days=d["days_ago"])).date(), generated_at=_ago(d["days_ago"]),
                language="fr", scope_digest="measure", evidence_digest="measure",
                sections_used=["messages"], unavailable=[], state="ready",
                body={"headline": d["headline"], "where_we_stand": d["where_we_stand"],
                      "open_points": d["open_points"], "suggested_next_step": None, "notable_facts": []},
            )
            db.add(row); await db.flush(); created["relation_debriefs"].append(str(row.id))
        for o in corpus["open_loops"]:
            row = OpenLoop(
                user_id=uid, subject=o["subject"], counterparty=o["counterparty"],
                direction=o["direction"], due_hint=now + timedelta(days=o["due_in_days"]),
                source_kind="conversation", status="open", nudge_count=0,
            )
            db.add(row); await db.flush(); created["open_loops"].append(str(row.id))
        for t in corpus["workboard"]:
            row = WorkboardTicket(
                owner_user_id=uid, title=t["title"], description=t["description"], status=t["status"],
                priority=t["priority"], due_at=now + timedelta(days=t["due_in_days"]),
                assignee_kind=t["assignee_kind"], position=0, created_by="user",
                status_changed_at=now, execution_mode="react",
            )
            db.add(row); await db.flush(); created["workboard"].append(str(row.id))
        for r in corpus["routines"]:
            row = ScheduledAction(
                user_id=uid, title=r["title"], action_prompt=r["action_prompt"], recurrence=r["recurrence"],
                user_timezone=corpus["timezone"], next_trigger_at=now + timedelta(days=1),
                trigger_kind="time", is_enabled=True, status="active", execution_mode="react",
            )
            db.add(row); await db.flush(); created["routines"].append(str(row.id))
        for r in corpus["reminders"]:
            row = Reminder(
                user_id=uid, content=r["content"], original_message=r["original_message"],
                recurrence=r["recurrence"], trigger_at=now + timedelta(days=r["trigger_in_days"]),
                user_timezone=corpus["timezone"], status="pending", retry_count=0,
            )
            db.add(row); await db.flush(); created["reminders"].append(str(row.id))
        for b in corpus["bookmarks"]:
            row = MessageBookmark(
                user_id=uid, content=b["content"], request_content=b["request_content"],
                answered_at=_ago(b["days_ago"]),
            )
            db.add(row); await db.flush(); created["bookmarks"].append(str(row.id))
        await db.execute(
            update(User).where(User.id == uid).values(
                journals_enabled=True, memory_enabled=True, habits_enabled=True,
                relation_debrief_enabled=True, language=corpus["language"], timezone=corpus["timezone"],
                journal_portrait_full=None, journal_portrait_brief=None,
                journal_portrait_compiled_at=None, journal_portrait_sources=None,
                journal_last_attempted_at=None, journal_consolidation_held_until=None,
            ).execution_options(synchronize_session=False)
        )
        await db.commit()
    state_path.write_text(json.dumps({"user_id": str(uid), "created": created}), encoding="utf-8")
    print(f"seeded {sum(len(v) for v in created.values())} rows for {str(uid)[:8]}")


async def teardown(state_path: Path) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    uid = UUID(state["user_id"])
    async with get_db_context() as db:
        for key, ids in state["created"].items():
            model = MODELS[key]
            plain = [UUID(i) for i in ids if not i.startswith("profile:")]
            if plain:
                await db.execute(delete(model).where(model.id.in_(plain)))
            if any(i.startswith("profile:") for i in ids):
                await db.execute(delete(UserHabitProfile).where(UserHabitProfile.user_id == uid))
        await db.execute(
            update(User).where(User.id == uid).values(
                journal_portrait_full=None, journal_portrait_brief=None,
                journal_portrait_compiled_at=None, journal_portrait_sources=None,
            ).execution_options(synchronize_session=False)
        )
        await db.commit()
    print("teardown done")


def _tokens(text: str | None) -> int:
    return OpenAITokenCounter().count(text or "", "gpt-4o")


async def _snapshot(uid: UUID) -> dict[str, Any]:
    async with get_db_context() as db:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        prov = user.journal_portrait_sources if isinstance(user.journal_portrait_sources, dict) else {}
        claims = prov.get("claims") or []
        review = prov.get("portrait_review") or {}
        return {
            "status": user.journal_last_attempt_status,
            "full": user.journal_portrait_full,
            "brief": user.journal_portrait_brief,
            "full_chars": len(user.journal_portrait_full or ""),
            "brief_chars": len(user.journal_portrait_brief or ""),
            "full_tokens": _tokens(user.journal_portrait_full),
            "brief_tokens": _tokens(user.journal_portrait_brief),
            "published": len(claims),
            "placements": [c.get("placement", "full" if not c.get("in_brief") else "brief") for c in claims],
            "facets": [c.get("facet") for c in claims],
            "support_kinds": sorted({s["source"].split(":")[0] for c in claims for s in c.get("supports", [])}),
            "omitted_claims": prov.get("omitted_claims"),
            "approved": review.get("approved_indices"),
            "rejected": review.get("rejected"),
            "sources": prov.get("sources"),
            "cost_eur": float(user.journal_last_cost_eur or 0),
        }


async def measure(state_path: Path, runs: int, report_path: Path) -> None:
    _refuse_anthropic()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    uid = UUID(state["user_id"])
    results = []
    for index in range(runs):
        started = monotonic()
        await consolidate_journals_for_user(uid, None, None, "fr", False, manual=True)
        snap = await _snapshot(uid)
        snap["duration_s"] = round(monotonic() - started, 1)
        snap["run"] = index + 1
        results.append(snap)
        print(json.dumps({k: v for k, v in snap.items() if k not in ("full", "brief")}, ensure_ascii=False))
        async with get_db_context() as db:  # the next run must be a fresh compilation
            await db.execute(
                update(User).where(User.id == uid).values(
                    journal_portrait_sources=None, journal_last_attempted_at=None,
                ).execution_options(synchronize_session=False)
            )
            await db.commit()
    cfg = get_llm_config_for_agent(settings, "journal_consolidation")
    report_path.write_text(
        json.dumps({"slot": {"provider": cfg.provider, "model": cfg.model}, "runs": results},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"report written: {report_path}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--teardown", action="store_true")
    parser.add_argument("--runs", type=int, default=0)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("/tmp/portrait_report.json"))
    args = parser.parse_args(argv)
    if args.seed:
        asyncio.run(seed(args.state))
    if args.runs:
        asyncio.run(measure(args.state, args.runs, args.report))
    if args.teardown:
        asyncio.run(teardown(args.state))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Note for the executor: `consolidate_journals_for_user`'s positional parameters are `(user_id, personality_instruction, personality_code, user_language, consolidation_with_history, …)` — read its signature at `consolidation_service.py:809` before calling; the lease reads the row's own language and preferences.

- [ ] **Step 5: Wire the task** — `Taskfile.yml`, after `react:recovery:measure`:

```yaml
  journals:portrait:measure:
    desc: Seed a synthetic persona into the PROOF account on dev and measure what the portrait publishes (NETWORK, billed, on demand)
    dir: "{{.API_DIR}}"
    # A MEASUREMENT, never a gate: the real consolidation, twice its model calls,
    # on the proof account only (the script refuses any other, and an Anthropic
    # slot). apps/api/scripts/journals/portrait_corpus.json is INVENTED.
    cmds:
      - cmd: .venv/Scripts/python scripts/journals/measure_portrait.py {{.CLI_ARGS}}
        platforms: [windows]
      - cmd: .venv/bin/python scripts/journals/measure_portrait.py {{.CLI_ARGS}}
        platforms: [linux, darwin]
```

- [ ] **Step 6: Run the BASELINE on dev (current code, before Task 2)**

```bash
docker cp apps/api/scripts/journals lia-api-dev:/app/scripts/journals   # only if /app is not the bind mount; check `docker inspect lia-api-dev --format '{{json .Mounts}}'`
MSYS_NO_PATHCONV=1 docker exec -e PYTHONPATH=/app lia-api-dev sh -c 'cd /app && python scripts/journals/measure_portrait.py --seed --runs 2 --state /tmp/portrait_seed.json --report /tmp/portrait_baseline.json'
docker cp lia-api-dev:/tmp/portrait_baseline.json "$TMPDIR/portrait_baseline.json"
```

Expected: two runs, each `status: success`, a JSON line per run with `published`, `omitted_claims`, `rejected`, `full_tokens`, `brief_tokens`, `support_kinds`, `cost_eur`, `duration_s`. Keep the seed in place (do NOT tear down) — the candidate runs on the same rows.

- [ ] **Step 7: Run the task's gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/scripts/test_portrait_corpus.py -v && .venv/Scripts/ruff check scripts/journals && .venv/Scripts/mypy scripts/journals/measure_portrait.py`
Expected: PASS, no lint finding.

### Task 2: The seam grows to nine sources and loses its item budget

**Files:**
- Modify: `apps/api/src/domains/shared/portrait_sources.py`
- Modify: `apps/api/src/infrastructure/startup/registries.py:471-510`
- Test: `apps/api/tests/unit/domains/shared/test_portrait_sources.py`, `apps/api/tests/unit/infrastructure/startup/test_portrait_sources_boot.py`

**Interfaces:**
- Produces: `PORTRAIT_SOURCE_KEYS == ("memories", "interests", "habits", "relation_debriefs", "open_loops", "workboard", "routines", "reminders", "bookmarks")`; `PortraitSourceReader.__call__(self, *, user_id: UUID, language: str) -> PortraitSourceSection` (no `budget`); `flat_item(text: str) -> str` (newlines collapsed, nothing cut); `SourceBudget`, `ITEMS_BOUNDED_BY_SOURCE`, `clamp_item` and `FreshnessProbe.selection_query` are DELETED.

- [ ] **Step 1: Write the failing tests** — in `test_portrait_sources.py` replace the `_reader`/`_other` signatures (drop `budget`) and add:

```python
def test_the_vocabulary_names_every_record_about_the_person() -> None:
    assert PORTRAIT_SOURCE_KEYS == (
        "memories", "interests", "habits", "relation_debriefs",
        "open_loops", "workboard", "routines", "reminders", "bookmarks",
    )


def test_flat_item_collapses_newlines_and_cuts_nothing() -> None:
    from src.domains.shared.portrait_sources import flat_item

    long = "a" * 3000 + "\n\n" + "b" * 3000
    assert flat_item(long) == "a" * 3000 + " " + "b" * 3000
    assert "…" not in flat_item(long)
```

In `test_portrait_sources_boot.py`, import the nine modules (add `open_loops`, `workboard`, `scheduled_actions`, `reminders`, `bookmarks` `.portrait_source`) and keep the two tests (the second's spare key becomes `"peers"`).

- [ ] **Step 2: Run them to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/shared/test_portrait_sources.py tests/unit/infrastructure/startup/test_portrait_sources_boot.py -v`
Expected: FAIL (`PORTRAIT_SOURCE_KEYS` has four members; `flat_item` undefined; modules missing).

- [ ] **Step 3: Implement the seam change** — in `portrait_sources.py`: extend `PORTRAIT_SOURCE_KEYS`; delete `ITEMS_BOUNDED_BY_SOURCE`, `SourceBudget`, `clamp_item`, `FreshnessProbe.selection_query`; change the Protocol:

```python
class PortraitSourceReader(Protocol):
    """What a source offers the consolidation: one gated, whole, safe read."""

    async def __call__(self, *, user_id: UUID, language: str) -> PortraitSourceSection:
        """Render the WHOLE source for one account; never raises."""


def flat_item(text: str) -> str:
    """One line: newlines collapsed, nothing cut (an item is quoted whole)."""
    return " ".join(text.split())
```

Update the module docstring (nine records, one physical bound in the assembler) and `__all__`. In `registries._install_portrait_sources`, import and install the five new modules (`open_loops.portrait_source`, `workboard.portrait_source`, `scheduled_actions.portrait_source`, `reminders.portrait_source`, `bookmarks.portrait_source`), each as `install_portrait_source(mod.KEY, mod.read_<key>, mod.FRESHNESS)`; the reader names are `read_open_loops`, `read_workboard`, `read_routines`, `read_reminders`, `read_bookmarks` (Task 3 creates them; until then the boot test fails on import — Task 3 comes before the gate is run).

- [ ] **Step 4: Run the seam test**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/shared/test_portrait_sources.py -v`
Expected: PASS (the boot test passes after Task 3).

### Task 3: Five new readers, the four old ones read whole

**Files:**
- Create: `apps/api/src/domains/open_loops/portrait_source.py`, `apps/api/src/domains/workboard/portrait_source.py`, `apps/api/src/domains/scheduled_actions/portrait_source.py`, `apps/api/src/domains/reminders/portrait_source.py`, `apps/api/src/domains/bookmarks/portrait_source.py`
- Modify: `apps/api/src/domains/memories/portrait_source.py`, `apps/api/src/domains/interests/portrait_source.py`, `apps/api/src/domains/habits/portrait_source.py`, `apps/api/src/domains/relations/debrief/portrait_source.py`
- Modify: `apps/api/src/domains/agents/prompts/v1/journal_portrait_source_lines.txt`
- Modify: `apps/api/tests/unit/domains/agents/prompts/test_prompt_placeholders_are_produced.py:78-83` (add the five renderers)
- Test: `apps/api/tests/unit/domains/open_loops/test_portrait_source.py` (and one per new domain), plus the existing four readers' tests (find them: `grep -rl "read_memories\|read_interests\|read_habits\|read_relation_debriefs" apps/api/tests/unit`)

**Interfaces:**
- Consumes: `install_portrait_source`, `FreshnessProbe`, `PortraitSourceSection`, `empty_section`, `flat_item`, `portrait_lines` from the seam; `is_capability_enabled` + `PlatformCapability` members `OPEN_LOOPS`, `WORKBOARD`, `SCHEDULED_ACTIONS` (check the member names in `domains/feature_switches/registry.py` — use the ones that exist; reminders have no capability switch, bookmarks have `BOOKMARKS`).
- Produces: `read_open_loops`, `read_workboard`, `read_routines`, `read_reminders`, `read_bookmarks` (signature `(*, user_id: UUID, language: str) -> PortraitSourceSection`), each with `KEY` and `FRESHNESS`.

- [ ] **Step 1: Add the scaffold lines** to `journal_portrait_source_lines.txt` (after `debriefs_item`):

```
open_loops_header|## OPEN LOOPS (unfinished threads the person tracks; {shown} of {total})
open_loops_item|- {subject} ({direction}{counterparty}{due})
open_loops_direction_owes|the person owes it
open_loops_direction_waiting|the person is waiting on someone
open_loops_due|; due around {date}
workboard_header|## WORKBOARD (tickets the person owns or holds; {shown} of {total})
workboard_item|- {title} [{status}, priority {priority}{due}{holder}]{description}
workboard_holder_lia|, delegated to LIA
workboard_due|, due {date}
routines_header|## ROUTINES (what the person automated; {shown} of {total})
routines_item|- {title} — {schedule}: {instruction}
routines_condition|when {condition}
reminders_header|## PENDING REMINDERS ({shown} of {total})
reminders_item|- {content} ({when}{repeat})
reminders_repeat|, {schedule}
bookmarks_header|## KEPT ANSWERS (what the person chose to keep; {shown} of {total})
bookmarks_item|- Asked « {request} » ({date}) and kept: {excerpt}
```

- [ ] **Step 2: Write the failing reader test** — `apps/api/tests/unit/domains/open_loops/test_portrait_source.py`:

```python
"""The open loops offer themselves to the portrait: gated, whole, never raising."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.open_loops import portrait_source as source

pytestmark = pytest.mark.unit


def _loop(subject: str, direction: str, counterparty: str | None, due: datetime | None):
    return SimpleNamespace(subject=subject, direction=direction, counterparty=counterparty, due_hint=due)


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch):
    rows = [
        _loop("Renvoyer le devis", "user_owes", "l'ébéniste", datetime(2026, 10, 15, tzinfo=UTC)),
        _loop("Réponse du fournisseur", "waiting_on_other", None, None),
    ]

    class _Repo:
        def __init__(self, db):  # noqa: ANN001
            pass

        async def list_open_for_user(self, user_id, limit):  # noqa: ANN001
            return rows[:limit]

    @asynccontextmanager
    async def _ctx():
        yield object()

    monkeypatch.setattr(source, "OpenLoopRepository", _Repo)
    monkeypatch.setattr(source, "get_db_context", _ctx)
    monkeypatch.setattr(source, "_count_open", AsyncMock(return_value=2))
    return rows


async def test_every_open_loop_is_rendered_whole_with_its_direction(repo) -> None:
    with patch.object(source, "_allowed", AsyncMock(return_value=True)):
        section = await source.read_open_loops(user_id=uuid4(), language="fr")
    assert section.status == "used" and section.used == 2 and section.total == 2
    assert section.text.startswith("## OPEN LOOPS")
    assert "- Renvoyer le devis (the person owes it, l'ébéniste; due around 2026-10-15)" in section.text
    assert "- Réponse du fournisseur (the person is waiting on someone)" in section.text


async def test_a_closed_gate_answers_disabled(repo) -> None:
    with patch.object(source, "_allowed", AsyncMock(return_value=False)):
        section = await source.read_open_loops(user_id=uuid4(), language="fr")
    assert section.status == "disabled" and section.text == ""


async def test_a_failed_read_is_named_never_read_as_empty(repo, monkeypatch) -> None:
    monkeypatch.setattr(source, "_count_open", AsyncMock(side_effect=RuntimeError("db")))
    with patch.object(source, "_allowed", AsyncMock(return_value=True)):
        section = await source.read_open_loops(user_id=uuid4(), language="fr")
    assert section.status == "unavailable"
```

Write the same three tests for `workboard` (rows with `title/description/status/priority/due_at/assignee_kind`, expecting `- Préparer la grille [in_progress, priority high, due 2026-10-18, delegated to LIA]: Compiler…`), `scheduled_actions` (expect `- Résumé du vendredi — <describe(spec, "fr")>: Résume…`; patch `describe` to return `"chaque vendredi à 16:30"`), `reminders` (expect `- Appeler le fournisseur (2026-10-14 09:00)`), `bookmarks` (expect `- Asked « Comment retirer… » (2026-09-30) and kept: Travaillez par petites zones…`; the excerpt is `flat_item(markdown_to_plain_text(content))` bounded at `BOOKMARK_EXCERPT_MAX_CHARS = 600` characters with the one ellipsis — a kept answer can be pages long and the bound is the item's, published beside the item).

- [ ] **Step 3: Run them to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/open_loops/test_portrait_source.py -v`
Expected: FAIL (`portrait_source` has no attribute …).

- [ ] **Step 4: Write the open loops reader** — `apps/api/src/domains/open_loops/portrait_source.py`:

```python
"""The open loops as a portrait source (whole, gated, never raising).

Installed into ``domains/shared/portrait_sources`` so ``journals`` reads it
without importing this domain. Two gates read at call time: the deployment
ceiling (``settings.open_loops_enabled``) and the operator switch. Every OPEN
loop is rendered, earliest deadline first, beside the exact total; a failed
read is ``unavailable``.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.open_loops.models import OpenLoop, OpenLoopDirection, OpenLoopStatus
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    empty_section,
    flat_item,
    install_portrait_source,
    portrait_lines,
)
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "open_loops"


async def _allowed(user_id: UUID | None = None) -> bool:
    return bool(settings.open_loops_enabled) and await is_capability_enabled(
        PlatformCapability.OPEN_LOOPS
    )


async def _count_open(db: object, user_id: UUID) -> int:
    stmt = select(func.count()).where(
        OpenLoop.user_id == user_id, OpenLoop.status == OpenLoopStatus.OPEN.value
    )
    return int((await db.execute(stmt)).scalar_one())  # type: ignore[attr-defined]


async def read_open_loops(*, user_id: UUID, language: str) -> PortraitSourceSection:
    """Render every open loop of one account.

    Args:
        user_id: The account.
        language: Unused — a loop is stored as the person said it.

    Returns:
        The section; never raises.
    """
    try:
        if not await _allowed(user_id):
            return empty_section(KEY, "disabled")
        async with get_db_context() as db:
            total = await _count_open(db, user_id)
            rows = (
                await OpenLoopRepository(db).list_open_for_user(user_id, limit=max(total, 1))
                if total
                else []
            )
        if not rows:
            return empty_section(KEY, "empty", total=total)
        lines = portrait_lines()
        items = [
            lines["open_loops_item"].format(
                subject=flat_item(row.subject),
                direction=lines[
                    "open_loops_direction_owes"
                    if row.direction == OpenLoopDirection.USER_OWES.value
                    else "open_loops_direction_waiting"
                ],
                counterparty=f", {flat_item(row.counterparty)}" if row.counterparty else "",
                due=lines["open_loops_due"].format(date=f"{row.due_hint:%Y-%m-%d}") if row.due_hint else "",
            )
            for row in rows
        ]
        header = lines["open_loops_header"].format(shown=len(items), total=total)
        return PortraitSourceSection(
            key=KEY, status="used", text="\n".join([header, *items]), used=len(items), total=total
        )
    except Exception as exc:  # noqa: BLE001 — a blind source is named, never read as empty
        logger.warning("portrait_source_unavailable", source=KEY, error_type=type(exc).__name__)
        return empty_section(KEY, "unavailable")


FRESHNESS = FreshnessProbe(
    table="open_loops",
    user_column="user_id",
    stamp_column="updated_at",
    allowed=_allowed,
    semantic_columns=("subject", "counterparty", "direction", "due_hint", "status"),
)

install_portrait_source(KEY, read_open_loops, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_open_loops"]
```

Check `settings.open_loops_enabled` exists (`grep -n open_loops_enabled apps/api/src/core/config/*.py`); if the flag has another name, use it and keep the gate semantics.

- [ ] **Step 5: Write the workboard reader** — `apps/api/src/domains/workboard/portrait_source.py`, same skeleton; the read:

```python
async def read_workboard(*, user_id: UUID, language: str) -> PortraitSourceSection:
    try:
        if not await _allowed(user_id):
            return empty_section(KEY, "disabled")
        async with get_db_context() as db:
            stmt = (
                select(WorkboardTicket)
                .where(visible_predicate(user_id))
                .order_by(WorkboardTicket.due_at.asc().nulls_last(), WorkboardTicket.created_at.asc(), WorkboardTicket.id)
            )
            rows = list((await db.execute(stmt)).scalars().all())
        if not rows:
            return empty_section(KEY, "empty")
        lines = portrait_lines()
        items = [
            lines["workboard_item"].format(
                title=flat_item(row.title),
                status=row.status,
                priority=row.priority,
                due=lines["workboard_due"].format(date=f"{row.due_at:%Y-%m-%d}") if row.due_at else "",
                holder=lines["workboard_holder_lia"] if row.assignee_kind == AssigneeKind.LIA.value else "",
                description=f": {flat_item(row.description)}" if row.description else "",
            )
            for row in rows
        ]
        header = lines["workboard_header"].format(shown=len(items), total=len(items))
        return PortraitSourceSection(key=KEY, status="used", text="\n".join([header, *items]), used=len(items), total=len(items))
    except Exception as exc:  # noqa: BLE001
        logger.warning("portrait_source_unavailable", source=KEY, error_type=type(exc).__name__)
        return empty_section(KEY, "unavailable")
```

`_allowed` = `settings.workboard_enabled and await is_capability_enabled(PlatformCapability.WORKBOARD)` (verify names); `FRESHNESS` on `workboard_tickets`, `user_column="owner_user_id"`, `semantic_columns=("title", "description", "status", "priority", "due_at", "assignee_kind", "assignee_user_id")`. Tickets HELD by the person but owned by a peer are visible through `visible_predicate` yet outside the probe's `user_column`: add `related_probes=(FreshnessProbe(table="workboard_tickets", user_column="assignee_user_id", stamp_column="updated_at", semantic_columns=("title", "status", "priority", "due_at")),)`.

- [ ] **Step 6: Write the routines reader** — `apps/api/src/domains/scheduled_actions/portrait_source.py`: rows `ScheduledActionRepository(db).get_all_for_user(user_id, limit=max(total, 1))` after `total = count_for_user`; keep `status == "active"` and `is_enabled`; the schedule: `describe(RecurrenceSpec.model_validate(row.recurrence), language)` when `trigger_kind == "time"`, else `lines["routines_condition"].format(condition=row.condition_config.get("type", "a condition"))`; `instruction=flat_item(row.action_prompt)`; gate `settings.scheduled_actions…` — there is NO flag for scheduled actions (CLAUDE.md); gate on the capability switch only if `PlatformCapability` has a member for routines, else `_allowed` returns `True`. `FRESHNESS` on `scheduled_actions`, `semantic_columns=("title", "action_prompt", "recurrence", "trigger_kind", "condition_config", "is_enabled", "status")`.

- [ ] **Step 7: Write the reminders reader** — `apps/api/src/domains/reminders/portrait_source.py`: `ReminderRepository(db).get_all_pending_for_user(user_id)`; `when = f"{row.trigger_at.astimezone(resolve_user_timezone(user)):%Y-%m-%d %H:%M}"` (read the user row in the same session for its timezone); `repeat = lines["reminders_repeat"].format(schedule=describe(spec, language))` when `spec.freq != "once"`; gate: `settings.reminders_enabled` if it exists (`grep -n reminders_enabled apps/api/src/core/config/*.py`) else `True`. `FRESHNESS` on `reminders`, `semantic_columns=("content", "recurrence", "trigger_at", "status")`.

- [ ] **Step 8: Write the bookmarks reader** — `apps/api/src/domains/bookmarks/portrait_source.py`: direct `select(MessageBookmark).where(MessageBookmark.user_id == user_id).order_by(MessageBookmark.answered_at.desc(), MessageBookmark.id)`; `excerpt = _excerpt(row.content)` where

```python
BOOKMARK_EXCERPT_MAX_CHARS = 600


def _excerpt(content: str) -> str:
    text = flat_item(markdown_to_plain_text(strip_html_if_markup(content)))
    if len(text) <= BOOKMARK_EXCERPT_MAX_CHARS:
        return text
    return text[: BOOKMARK_EXCERPT_MAX_CHARS - 1].rstrip() + "…"
```

(find `markdown_to_plain_text` and `strip_html_if_markup`: `grep -rn "def markdown_to_plain_text\|def strip_html_if_markup" apps/api/src`). An excerpt ending in « … » is INELIGIBLE as a proof by the catalogue's rule (`"…" not in line`) — that is wanted: a cut answer cannot be quoted as a whole; the model still reads it as material. Gate: `await is_capability_enabled(PlatformCapability.BOOKMARKS)`. `FRESHNESS` on `message_bookmarks`, `stamp_column="created_at"`, `semantic_columns=("content", "request_content", "answered_at")`.

- [ ] **Step 9: Make the four existing readers read whole** — in each: drop the `budget` parameter; replace `clamp_item(x, budget.item_max_chars)` by `flat_item(x)`; memories: `repo.list_for_portrait(user_id, limit=total)` (check the method accepts a large limit; else add `limit: int | None` to it) and delete `_selected_ids` + `selection_query`; interests: `list_active_by_signals(user_id, limit=total)`; debriefs: iterate `rows` whole and render `open_points` too: extend `debriefs_item` to `- {person} (written {date}): {headline} — {where_we_stand}{open_points}` with `open_points=f" Open: {'; '.join(flat_item(p) for p in body.open_points)}" if body.open_points else ""`; habits: unchanged but `flat_item`. Update each reader's existing unit tests (they pass a `budget`; remove it and assert that a 1 500-character memory is rendered whole).

- [ ] **Step 10: Declare the five renderers** in `test_prompt_placeholders_are_produced.py` `RENDERED_BY["journal_portrait_source_lines"]` (add the five module paths).

- [ ] **Step 11: Run the task's gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/open_loops/test_portrait_source.py tests/unit/domains/workboard/test_portrait_source.py tests/unit/domains/scheduled_actions/test_portrait_source.py tests/unit/domains/reminders/test_portrait_source.py tests/unit/domains/bookmarks/test_portrait_source.py tests/unit/domains/memories tests/unit/domains/interests tests/unit/domains/habits tests/unit/domains/relations tests/unit/infrastructure/startup/test_portrait_sources_boot.py tests/unit/domains/agents/prompts/test_prompt_placeholders_are_produced.py -q`
Expected: PASS.

### Task 4: One window share instead of five caps (settings, source state, assembler)

**Files:**
- Modify: `apps/api/src/core/constants.py:5573-5577`, `apps/api/src/core/config/journals.py:149-185`
- Modify: `.env.example:1884-1890`, `.env.prod.example:1844-1850`, and the local `.env`, `.env.prod` (the same six keys; replace, never blank)
- Modify: `apps/api/src/domains/journals/portrait_sources.py`
- Modify: `apps/api/src/domains/journals/source_state.py`
- Modify: `apps/api/src/domains/journals/consolidation_service.py:614-620`
- Test: `apps/api/tests/unit/domains/journals/test_portrait_sources_assembly.py`, `apps/api/tests/unit/core/config/test_journal_settings.py` (create if absent)

**Interfaces:**
- Produces: `settings.journal_consolidation_sources_window_fraction: float` (default `JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION_DEFAULT = 0.5`, bounds `0 < x <= 0.9`); `build_portrait_source_sections(user_id, language, *, journal_entries: int, window_tokens: int) -> PortraitSourceBundle`; `portrait_source_state(db, user) -> dict` whose `_rendering` carries `"sources_window_fraction"` and no per-source `max_items / item_max_chars / total_cap`.

- [ ] **Step 1: Write the failing assembler tests** — replace in `test_portrait_sources_assembly.py` the `registry` fixture's settings namespace with `SimpleNamespace(journal_consolidation_sources_window_fraction=0.5)`, drop the `SourceBudget` assertions, and replace `test_a_section_that_breaks_the_global_cap_is_dropped_whole_and_reported` by:

```python
async def test_the_window_share_cuts_the_last_sections_at_item_boundaries_and_says_so(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter

    memory = "## LONG-TERM MEMORIES\n- first memory kept whole\n- second memory kept whole"
    interests = "## INTERESTS\n- first interest\n- second interest\n- third interest"
    registry["readers"]["memories"] = _reader("memories", text=memory, used=2, total=2)
    registry["readers"]["interests"] = _reader("interests", text=interests, used=3, total=3)
    monkeypatch.setattr(seam, "_REGISTRY", {k: (r, PROBE) for k, r in registry["readers"].items()})
    from src.domains.journals.portrait_catalogue import render_catalogue_sections

    whole_memories = render_catalogue_sections({"memories": memory})["memories"]
    one_interest = render_catalogue_sections({"interests": "## INTERESTS\n- first interest"})["interests"]
    budget = OpenAITokenCounter().count(whole_memories + "\n\n" + one_interest, "gpt-4o")
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=budget * 2
    )
    assert bundle.sections["memories"] == memory
    assert bundle.sections["interests"] == "## INTERESTS\n- first interest"
    assert bundle.provenance["sources"]["interests"] == {
        "status": "used", "used": 1, "total": 3, "reason": "over_budget",
    }
    assert bundle.provenance["sources"]["habits"]["status"] == "disabled"


async def test_nothing_is_cut_when_the_material_fits(registry: dict[str, Any]) -> None:
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=1_000_000
    )
    assert all("reason" not in v for v in bundle.provenance["sources"].values())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals/test_portrait_sources_assembly.py -v`
Expected: FAIL (`window_tokens` unexpected keyword; settings attribute missing).

- [ ] **Step 3: Settings** — in `core/constants.py` replace the five constants by `JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION_DEFAULT = 0.5` (comment: « the share of the consolidation slot's context window the portrait sources may take; items whole, the cut stated »). In `core/config/journals.py` delete the five fields and add:

```python
    journal_consolidation_sources_window_fraction: float = Field(
        default=JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION_DEFAULT,
        gt=0.0,
        le=0.9,
        description=(
            "Share of the journal_consolidation slot's effective context window the portrait "
            "sources may occupy; sections keep their order, items are whole, a cut is stated."
        ),
    )
```

In `.env.example` and `.env.prod.example` replace the five lines by `JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION=0.5          # Share of the consolidation slot's window the portrait sources may take (items whole, cut stated)` and rewrite the two-line comment above (« nine sources it reads »). Apply the same key change to the local `.env` and `.env.prod` (keep their other values).

- [ ] **Step 4: Assembler** — rewrite `build_portrait_source_sections` in `journals/portrait_sources.py`:

```python
async def build_portrait_source_sections(
    user_id: UUID, language: str, *, journal_entries: int, window_tokens: int
) -> PortraitSourceBundle:
    """Read every source for one account, in order, whole, under one stated share.

    Args:
        user_id: The account whose portrait is compiled.
        language: The account's language.
        journal_entries: How many entries the prompt carries (provenance).
        window_tokens: The consolidation slot's effective context window.

    Returns:
        The sections and the provenance; never raises.
    """
    budget = int(window_tokens * settings.journal_consolidation_sources_window_fraction)
    counter = OpenAITokenCounter()
    sections: dict[str, str] = dict.fromkeys(PORTRAIT_SOURCE_KEYS, "")
    provenance: dict[str, dict[str, Any]] = {}
    spent = 0
    for key, (reader, _probe) in installed_portrait_sources().items():
        section = await reader(user_id=user_id, language=language)
        eligible = eligible_source_items(key, section.text)
        omitted = max(section.used - len(eligible), 0)
        if section.status == "used":
            section = replace(
                section,
                status="used" if eligible else "empty",
                text=section.text if eligible else "",
                used=len(eligible),
            )
        if section.text:
            section, spent = _admit(section, counter, spent, budget)
        _count(section)
        if section.text:
            sections[key] = section.text
        provenance[key] = {"status": section.status, "used": section.used, "total": section.total}
        if omitted:
            provenance[key]["omitted_incomplete"] = omitted
        if section.reason:
            provenance[key]["reason"] = section.reason
    logger.info(
        "portrait_sources_assembled",
        user_id=str(user_id),
        tokens=spent,
        budget=budget,
        statuses={key: value["status"] for key, value in provenance.items()},
    )
    return PortraitSourceBundle(
        sections=sections,
        provenance={"version": PROVENANCE_VERSION, "journal_entries": journal_entries, "sources": provenance},
    )


def _admit(
    section: PortraitSourceSection, counter: OpenAITokenCounter, spent: int, budget: int
) -> tuple[PortraitSourceSection, int]:
    """Keep the longest prefix of the section's items whose rendered form fits; state a cut."""
    headers = [line for line in section.text.splitlines() if line.startswith("## ")]
    items = [line for line in section.text.splitlines() if line.startswith("- ")]
    kept = len(items)
    while kept > 0:
        candidate = "\n".join([*headers, *items[:kept]])
        rendered = render_catalogue_sections({section.key: candidate})[section.key]
        cost = counter.count(rendered, "gpt-4o")
        if spent + cost <= budget:
            if kept == len(items):
                return section, spent + cost
            logger.warning(
                "portrait_source_cut_at_window_share",
                source=section.key, kept=kept, total=len(items), spent=spent, budget=budget,
            )
            return (
                replace(section, text=candidate, used=kept, reason="over_budget"),
                spent + cost,
            )
        kept -= 1
    logger.warning("portrait_source_dropped_over_window_share", source=section.key, spent=spent, budget=budget)
    return replace(section, status="unavailable", text="", used=0, reason="over_budget"), spent
```

Delete `_budget_for` and `_over_cap`; import `OpenAITokenCounter`; `PortraitSourceSection.reason` keeps its `Literal["over_budget"]`. The rendering of an item line prefixed with `portrait_item_id` is what is counted (the prompt's real text).

- [ ] **Step 5: Source state** — in `source_state.py`, `portrait_source_state`: replace the `_rendering` keys `full_max_tokens/brief_max_tokens/with_history/max_total_chars/max_entry_chars/personality_id` block's siblings: add `"sources_window_fraction": settings.journal_consolidation_sources_window_fraction`; in the per-source `item`, delete `max_items`, `item_max_chars`, `total_cap`; `_source_identity` loses its `budget` parameter and the `selection_query` branch; `_budget_for` import goes.

- [ ] **Step 6: Service** — `consolidation_service.py:614`: `sources = await build_portrait_source_sections(user_id, user_language, journal_entries=len(entries), window_tokens=get_effective_context_window_for_slot("journal_consolidation"))` (the same door the call below already uses — move `context_window = get_effective_context_window_for_slot(...)` above and reuse it).

- [ ] **Step 7: Run the task's gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals -q -k "assembly or source or settings" && .venv/Scripts/pytest tests/unit/core/config -q && .venv/Scripts/mypy src/domains/journals src/domains/shared/portrait_sources.py && cd ../.. && apps/api/.venv/Scripts/python scripts/audit/check_code_hygiene.py`
Expected: PASS, and the hygiene check reports no setting missing from `.env.example`.

### Task 5: The prompt reads ONE sources placeholder, every section in order

**Files:**
- Modify: `apps/api/src/domains/agents/prompts/v1/journal_consolidation_prompt.txt:30-36` (the four section placeholders)
- Modify: `apps/api/src/domains/journals/prompt_builders.py:157-320`
- Modify: `apps/api/src/domains/journals/consolidation_service.py:630-651`
- Test: `apps/api/tests/unit/domains/journals/test_prompt_builders.py`, `apps/api/tests/unit/domains/journals/test_prompt_formatting_and_consolidation_parse.py`

**Interfaces:**
- Produces: `render_consolidation_prompt(template, persona_template, *, …, portrait_sources: Mapping[str, str], portrait_full_tokens, portrait_brief_tokens)`; `build_consolidation_prompt(*, …, portrait_sources: Mapping[str, str])`; the template placeholder `{portrait_sources}` (the four `{memories_section}` … `{debriefs_section}` are gone).

- [ ] **Step 1: Write the failing test** — in `test_prompt_builders.py` add:

```python
def test_the_prompt_renders_every_source_section_in_the_declared_order() -> None:
    from src.domains.journals.prompt_builders import render_consolidation_prompt
    from src.domains.shared.portrait_sources import PORTRAIT_SOURCE_KEYS

    sections = {key: f"## {key.upper()}\n- item of {key}" for key in PORTRAIT_SOURCE_KEYS}
    prompt = render_consolidation_prompt(
        "{portrait_sources}\n{portrait_full_tokens}/{portrait_brief_tokens}", "persona",
        all_entries="", current_chars=0, max_chars=1, size_warning="", current_datetime="now",
        conversation_history_section="", usage_patterns_section="", language_name="French",
        max_entry_chars=800, size_management_instruction="", health_signals_section="",
        personality_code=None, portrait_sources=sections, portrait_full_tokens=300,
        portrait_brief_tokens=70,
    )
    positions = [prompt.index(f"## {key.upper()}") for key in PORTRAIT_SOURCE_KEYS]
    assert positions == sorted(positions)
    assert "portrait_item_id=" in prompt
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals/test_prompt_builders.py -v -k declared_order`
Expected: FAIL (unexpected keyword `portrait_sources`).

- [ ] **Step 3: Implement** — in the template replace the four placeholders by one `{portrait_sources}` line; in `render_consolidation_prompt` replace the four `*_section` kwargs by `portrait_sources: Mapping[str, str]`, render `rendered = render_catalogue_sections(dict(portrait_sources))` and `template.format(..., portrait_sources="\n\n".join(rendered[key] for key in PORTRAIT_SOURCE_KEYS if rendered.get(key)))`; same in `build_consolidation_prompt`; the service passes `portrait_sources=sources.sections`. Fix the existing tests that pass the four kwargs.

- [ ] **Step 4: Run the task's gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals/test_prompt_builders.py tests/unit/domains/journals/test_prompt_formatting_and_consolidation_parse.py tests/unit/domains/agents/prompts/test_prompt_placeholders_are_produced.py -q`
Expected: PASS.

### Task 6: A claim declares its placement; the brief is packed from its own claims

**Files:**
- Modify: `apps/api/src/domains/journals/consolidation_output.py:84-91, 335-371`
- Modify: `apps/api/src/domains/journals/portrait_review.py:103-116`
- Modify: `apps/api/src/domains/agents/prompts/v1/journal_portrait_review_prompt.txt:27`
- Test: `apps/api/tests/unit/domains/journals/test_consolidation_output_strict.py:60-101`, `apps/api/tests/unit/domains/journals/test_consolidation_integrity.py:150-166`

**Interfaces:**
- Produces: `PortraitClaim.placement: Literal["full", "brief"] = "full"` (`in_brief` gone); `grounded_portraits(claims, entries, sections, *, published=None) -> tuple[str | None, str | None]` packing `full` from the `full` claims and `brief` from the `brief` claims, in order, whole, under their budgets; the review evidence items carry `"placement"`.

- [ ] **Step 1: Write the failing tests** — in `test_consolidation_output_strict.py` replace the `in_brief` test (lines ~60-101) by:

```python
def test_the_brief_is_packed_from_its_own_claims_never_from_the_full(monkeypatch) -> None:
    quote = "## LONG-TERM MEMORIES\n- the person reads figures before prose"
    support = PortraitSupport(source="memories", quote="- the person reads figures before prose")
    full_claim = PortraitClaim(
        facet="posture", placement="full", supports=[support],
        text="Je constate que cette personne lit les chiffres avant les explications et attend la mesure avant la conclusion.",
    )
    brief_claim = PortraitClaim(
        facet="posture", placement="brief", supports=[support], text="Les chiffres d'abord, la prose après."
    )
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 400)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 70)
    published: list[PortraitClaim] = []
    full, brief = grounded_portraits([full_claim, brief_claim], [], {"memories": quote}, published=published)
    assert full == full_claim.text
    assert brief == brief_claim.text
    assert [c.placement for c in published] == ["full", "brief"]


def test_no_brief_claims_leaves_the_brief_empty(monkeypatch) -> None:
    quote = "## LONG-TERM MEMORIES\n- the person reads figures before prose"
    support = PortraitSupport(source="memories", quote="- the person reads figures before prose")
    claim = PortraitClaim(facet="posture", supports=[support], text="Je constate que cette personne lit les chiffres d'abord.")
    full, brief = grounded_portraits([claim], [], {"memories": quote})
    assert full == claim.text and brief is None


def test_a_brief_claim_over_its_budget_is_omitted_whole(monkeypatch) -> None:
    quote = "## LONG-TERM MEMORIES\n- the person reads figures before prose"
    support = PortraitSupport(source="memories", quote="- the person reads figures before prose")
    claim = PortraitClaim(facet="posture", placement="brief", supports=[support], text="Un résumé bien trop long pour tenir. " * 20)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 10)
    published: list[PortraitClaim] = []
    full, brief = grounded_portraits([claim], [], {"memories": quote}, published=published)
    assert full is None and brief is None and published == []
```

In `test_consolidation_integrity.py:150-166` replace `in_brief=True` by `placement="brief"` and the assertion by `assert full is None and brief is None`.

- [ ] **Step 2: Run them to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals/test_consolidation_output_strict.py tests/unit/domains/journals/test_consolidation_integrity.py -q`
Expected: FAIL (`placement` is not a field).

- [ ] **Step 3: Implement** — `PortraitClaim`: replace `in_brief: bool = False` by `placement: Literal["full", "brief"] = "full"`. `grounded_portraits`:

```python
def grounded_portraits(claims, entries, sections, *, published=None):
    """Validate all proofs, then pack each format's own claims whole, in order, under its budget."""
    full: list[str] = []
    brief: list[str] = []
    counter = OpenAITokenCounter()
    for supported in validate_portrait_claims(claims, entries, sections):
        claim, text = supported.claim, supported.claim.text
        if claim.placement == "brief":
            target, budget = brief, settings.journal_portrait_brief_max_tokens
        else:
            target, budget = full, settings.journal_portrait_full_max_tokens
        if _fits_budget(counter, target, text, budget):
            target.append(text)
            if published is not None:
                published.append(claim)
    return "\n\n".join(full) or None, "\n\n".join(brief) or None
```

In `portrait_review.prepare_portrait_review`, `item["in_brief"] = claim.in_brief` becomes `item["placement"] = claim.placement`. In the review prompt line 27: « A brief facet still has to retain its conditions; … ». Grep `in_brief` across `apps/api` and `apps/web/src/hooks/useJournals.ts` (`in_brief: boolean` → `placement: 'full' | 'brief'`) until none remains.

- [ ] **Step 4: Run the task's gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals -q && grep -rn "in_brief" src ../web/src --include=*.py --include=*.ts --include=*.tsx --include=*.txt`
Expected: PASS; the grep prints nothing.

### Task 7: Review first, pack after

**Files:**
- Modify: `apps/api/src/domains/journals/portrait_review.py:103-116, 160-181`
- Modify: `apps/api/src/domains/journals/consolidation_settlement.py:140-170`
- Test: `apps/api/tests/unit/domains/journals/test_portrait_review.py`, `apps/api/tests/unit/domains/journals/test_portrait_partial_review.py`, `apps/api/tests/integration/domains/journals/test_partial_review_publication.py`

**Interfaces:**
- Produces: `prepare_portrait_review(output, entries, sources) -> PortraitReviewInput | None` admitting EVERY structurally valid claim (no budget); `reviewed_portrait(...)` returning the approved subset; `_publish_portrait` packing that subset with `grounded_portraits` (unchanged call) and recording `provenance["omitted_claims"] = len(output.portrait_claims) - len(published)`.

- [ ] **Step 1: Write the failing tests** — in `test_portrait_partial_review.py` add:

```python
def test_the_review_sees_every_valid_claim_whatever_the_budget(monkeypatch, portrait_case) -> None:
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 5)
    output, entries, sources = portrait_case["output"], portrait_case["entries"], portrait_case["sources"]
    candidate = prepare_portrait_review(output, entries, sources)
    assert candidate is not None
    assert len(candidate.claims) == len(output.portrait_claims)


def test_publication_packs_approved_claims_in_order_under_the_budget(monkeypatch, portrait_case) -> None:
    # Three approved paragraphs, a budget that holds two: the third is omitted whole and counted.
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", two_paragraphs_tokens(portrait_case))
    receipt = approve_all(portrait_case)
    selected = reviewed_portrait(portrait_case["output"], portrait_case["entries"], portrait_case["sources"], receipt)
    published: list[PortraitClaim] = []
    full, _ = grounded_portraits(selected.portrait_claims or [], portrait_case["entries"], portrait_case["sources"].sections, published=published)
    assert full.count("\n\n") == 1 and len(published) == 2
```

Build `portrait_case` with three valid `full` claims on one memory quote (the fixture style of `test_portrait_review.py:50-70`); `two_paragraphs_tokens` counts the first two texts joined by `"\n\n"` with `OpenAITokenCounter().count(..., "gpt-4o")`; `approve_all` returns `PortraitReviewReceipt(digest=_evidence_digest(evidence), model="m", reviewed_at=0.0, reviewed_digest=candidate.digest, approved_indices=(0, 1, 2))` where `evidence` is the candidate's evidence re-indexed (the shape `review_portrait` builds at its end).

- [ ] **Step 2: Run them to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals/test_portrait_partial_review.py -v`
Expected: FAIL (the candidate holds fewer claims under a 5-token budget).

- [ ] **Step 3: Implement** — `prepare_portrait_review`:

```python
def prepare_portrait_review(output, entries, sources):
    claims = output.portrait_claims or []
    admitted = [supported.claim for supported in validate_portrait_claims(claims, entries, sources.sections)]
    _unchanged_supports(output, admitted)
    if not admitted:
        return None
    evidence = render_exact_evidence(admitted, entries, sources.sections)
    for item, claim in zip(evidence, admitted, strict=True):
        item["placement"] = claim.placement
    return PortraitReviewInput(evidence, _evidence_digest(evidence), tuple(admitted))
```

`reviewed_portrait` is unchanged in shape (it re-prepares the approved subset and compares digests). In `_publish_portrait` nothing moves: `grounded_portraits(accepted.portrait_claims …, published=published)` now packs after the review by construction; keep `provenance["omitted_claims"]`. The review input ceiling (`JOURNAL_PORTRAIT_REVIEW_MAX_INPUT_TOKENS`) stays the one bound on the review request.

- [ ] **Step 4: Run the task's gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals -q && task test:backend:integration -- -k "journal" -q`
Expected: PASS (the integration suite needs the dev PostgreSQL + Redis; `test_partial_review_publication.py` adapts its `journal_portrait_brief_max_tokens` monkeypatch to the new semantics: a `brief` claim is required for a brief to exist).

### Task 8: STEP 7 of the prompt asks for the whole picture and a real brief; the policy moves

**Files:**
- Modify: `apps/api/src/domains/agents/prompts/v1/journal_consolidation_prompt.txt:125-199, 255-265`
- Modify: `apps/api/src/domains/journals/constants.py:16`
- Test: `apps/api/tests/unit/domains/journals/test_portrait_narrative.py` (the prompt's promises vs the code — read it first; adapt its assertions to the new wording)

- [ ] **Step 1: Rewrite STEP 7** (English, the model's language). Replace lines 136-199 by:

```
Return ordered `portrait_claims`, the most important first. Each claim separates
the visible synthesis from its internal evidence:
- `facet`: `context`, `posture`, `focus`, `interaction` or `uncertainty`.
- `placement`: `full` for a paragraph of the full portrait, `brief` for a
  sentence of the brief portrait. The two formats are written SEPARATELY.
- `text`: natural {user_language}, describing only what the cited evidence
  supports. A `full` claim is a complete paragraph that makes sense alone: its
  own subject, situation and conditions, never an antecedent from another
  paragraph. A `brief` claim is ONE short sentence.
- `supports`: one or more objects with `source` and `item_id`. `source` is
  `journal:<exact UUID>` or one of the section keys (`memories`, `interests`,
  `habits`, `relation_debriefs`, `open_loops`, `workboard`, `routines`,
  `reminders`, `bookmarks`). Copy the opaque `item_id` displayed beside that
  item (journal headers name it `portrait_item_id`). Only items with a
  displayed ID are eligible evidence; a brief claim may cite the items the full
  claims cite — it condenses them. Cite the minimum sufficient evidence. IDs
  and evidence stay private: never paste them into `text`.

THE FULL PORTRAIT: write EVERY supported facet the material carries — durable
cognitive style and standards, current focus or phase, the contexts,
relationships, commitments and automations that shape the person's days, the
known rhythm, the observed tensions and open questions. Eight to twelve `full`
claims when the material allows; the publication keeps, in your order, the
claims that fit WHOLE within {portrait_full_tokens} token proxies, and an
independent verifier may drop a claim, so order by importance and never fold
two facets into one paragraph. Do not fill a facet the material does not support.

THE BRIEF PORTRAIT: two or three `brief` claims, short dense sentences that
together express the core posture, the current focus and the primary
interaction rule — a synthesis of the whole, never a copy of a `full`
paragraph, fitting together within {portrait_brief_tokens} token proxies.

RULES:
```

Keep the existing RULES block (lines 165-196) and replace its last paragraph (« Select only useful claims that can fit WHOLE within the budgets. ») by « The publication, not you, applies the budgets. ». Update the output example (lines 255-264): one `full` claim and one `brief` claim with `"placement"`. In `constants.py`: `JOURNAL_PORTRAIT_POLICY_VERSION = "grounded_narrative_v4"`.

- [ ] **Step 2: Run the task's gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals tests/unit/domains/agents/prompts -q`
Expected: PASS (fix `test_portrait_narrative.py` assertions to the new wording where they quote it).

### Task 9: Measure the candidate on dev and write the report for the owner

**Files:**
- Create: `docs/superpowers/plans/2026-10-12-portrait-whole-material-simulation.md`

- [ ] **Step 1: Restart the dev API so the working tree is loaded** (`docker restart lia-api-dev`; wait for `healthy`: `docker ps --format '{{.Names}} {{.Status}}' | grep lia-api-dev`). The seed of Task 1 is still in place; check: `docker exec lia-postgres-dev sh -c 'psql -X -U $POSTGRES_USER -d $POSTGRES_DB -c "select count(*) from journal_entries where session_id='"'"'portrait-measure'"'"'"'` prints 45.

- [ ] **Step 2: Run the candidate** (three runs):

```bash
MSYS_NO_PATHCONV=1 docker exec -e PYTHONPATH=/app lia-api-dev sh -c 'cd /app && python scripts/journals/measure_portrait.py --runs 3 --state /tmp/portrait_seed.json --report /tmp/portrait_candidate.json'
docker cp lia-api-dev:/tmp/portrait_candidate.json "$TMPDIR/portrait_candidate.json"
```

Expected: three `success` runs; `published` ≥ 8; `placements` holds 2-3 `brief`; `support_kinds` names several of the nine sources; `brief_tokens` ≤ 70; `cost_eur` per run printed. If a run ends `invalid_output`, read the `journal_consolidation_invalid_output` log line in `docker logs lia-api-dev` and fix the prompt/schema mismatch before re-running (each re-run costs ~0.04 €; stop and report at 0.50 € total).

- [ ] **Step 3: Tear down the seed**

```bash
MSYS_NO_PATHCONV=1 docker exec -e PYTHONPATH=/app lia-api-dev sh -c 'cd /app && python scripts/journals/measure_portrait.py --teardown --state /tmp/portrait_seed.json'
```

- [ ] **Step 4: Write the report** — `docs/superpowers/plans/2026-10-12-portrait-whole-material-simulation.md`: a table baseline vs candidate per run (claims proposed = published + omitted, approved, rejected with their criteria, published, full chars/tokens, brief chars/tokens, sources cited, cost, duration), the material offered (sections, items, tokens from the `portrait_sources_assembled` log line), the two portraits of the proof account under the candidate (full and brief, verbatim — invented persona), and the D3 question answered with figures: how many approved `full` claims did NOT fit under 300 tokens, and how many would fit under 400.

- [ ] **Step 5: Stop and hand the report to the owner.** Phase 2 starts only on the owner's validation (and their decision on the full budget default).

---

# Phase 2 — Definitive implementation (after the owner's validation)

### Task 10: The full budget default follows the owner's decision

**Files:**
- Modify: `apps/api/src/core/constants.py:5571` (only if the owner chose 400), `.env.example`, `.env.prod.example`, local `.env`, `.env.prod`

- [ ] **Step 1:** Set `JOURNAL_PORTRAIT_FULL_MAX_TOKENS_DEFAULT` and the four env lines to the chosen value; run `cd apps/api && .venv/Scripts/pytest tests/unit/core/config -q`.

### Task 11: A journal change marks the portrait stale, never wipes it (backend)

**Files:**
- Modify: `apps/api/src/domains/journals/lifecycle.py:21-54`
- Modify: `apps/api/src/domains/journals/portrait_read.py`
- Modify: `apps/api/src/domains/journals/schemas.py:370-400` (`JournalPortraitResponse.stale: bool = False`)
- Modify: `apps/api/src/domains/journals/portrait_builder.py:51-77, 131-139`
- Modify: `apps/api/src/domains/agents/prompts/v1/journal_portrait_source_lines.txt` (two lines: `ambient_directive|…`, `ambient_dated|This synthesis was compiled on {date} and may be dated.`)
- Test: `apps/api/tests/unit/domains/journals/test_lifecycle_stale.py` (create), `apps/api/tests/unit/domains/journals/test_portrait_builder.py`, `apps/api/tests/integration/test_application_journal_portrait.py:20-61`, `apps/api/tests/integration/test_journal_reader_freshness.py`

**Interfaces:**
- Produces: `mark_journal_changed(db, user_id, *, invalidate_portrait=True)` bumps `journal_revision` and never touches the four portrait columns (the `invalidate_portrait` flag only decides whether an already-versioned provenance's `journal_revision` follows — the existing `else` branch — so a confirming reaction keeps the portrait CURRENT while any other change makes it STALE); `read_managed_portrait(db, actor) -> JournalPortraitResponse` with `stale = not await portrait_is_current(db, current)` when the words exist; `build_journal_user_model_block(...)` injecting a stale portrait with the dated sentence.

- [ ] **Step 1: Write the failing tests** — `test_lifecycle_stale.py`:

```python
"""A journal change marks the portrait stale; it never wipes the words (ADR-269's doctrine)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.journals import lifecycle

pytestmark = pytest.mark.unit


async def test_a_journal_change_marks_the_portrait_stale_without_wiping_it() -> None:
    db = AsyncMock()
    await lifecycle.mark_journal_changed(db, uuid4())
    statement = db.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "journal_revision" in compiled
    assert "journal_portrait_full" not in compiled
    assert "journal_portrait_brief" not in compiled
    assert "journal_portrait_compiled_at" not in compiled
```

In `test_application_journal_portrait.py` the scenarios become: `current` → words, `stale is False`; `stale_revision`, `source_moved`, `missing` → the SAME words, `stale is True`; `personal_off` → `None`. In `test_portrait_builder.py` add `test_a_stale_portrait_is_injected_with_its_date` (patch `portrait_is_current` to `False`, expect the block to contain the `ambient_dated` sentence rendered with the compiled date).

- [ ] **Step 2: Run them to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals/test_lifecycle_stale.py tests/unit/domains/journals/test_portrait_builder.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** — `mark_journal_changed`: delete the `values.update(journal_portrait_full=None, …)` branch (keep the `else` arithmetic for `invalidate_portrait=False`, and make it the unconditional provenance update when `invalidate_portrait` is False; when True, only `journal_revision` moves). `read_managed_portrait`:

```python
async def read_managed_portrait(db: AsyncSession, actor: User) -> JournalPortraitResponse:
    current = await db.scalar(select(User).where(User.id == actor.id).execution_options(populate_existing=True))
    if current is None or not current.is_active or current.deleted_at is not None or not current.journals_enabled:
        return JournalPortraitResponse()
    if not (current.journal_portrait_full or current.journal_portrait_brief):
        return JournalPortraitResponse()
    return JournalPortraitResponse(
        full=current.journal_portrait_full,
        brief=current.journal_portrait_brief,
        compiled_at=current.journal_portrait_compiled_at,
        sources=provenance_of(current.journal_portrait_sources),
        stale=not await portrait_is_current(db, current),
    )
```

`portrait_builder._read_current_portrait` returns `(text, compiled_at, stale)`; the block becomes `portrait + "\n" + lines["ambient_dated"].format(date=compiled_at:%Y-%m-%d)` when stale, then `lines["ambient_directive"]`; the directive text moves verbatim from the `.py` into the lines file. `test_journal_reader_freshness.py`'s `portrait` reader branch asserts the block is still returned when `journals_enabled` turned False? No — the gate `journals_enabled` still hides; keep that assertion.

- [ ] **Step 4: Run the task's gate**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/journals -q && task test:backend:integration -- -k "journal_portrait or reader_freshness or portrait_invalidation" -q`
Expected: PASS.

### Task 12: Frontend — stale line, nine provenance sources, no client-side wipe, longer timeout

**Files:**
- Modify: `apps/web/src/hooks/useJournals.ts:216-226, 297-306` (`JournalPortrait.stale?: boolean`; `invalidatePortrait` → `markPortraitStale` which sets `{...data, stale: true}` and keeps the words)
- Modify: `apps/web/src/components/settings/PortraitCard.tsx:46-60` (under the compiled line, when `portrait.stale`: `t('journals.portraitStale', 'A recompilation is pending — the text below may be dated.')`)
- Modify: `apps/web/src/components/settings/PortraitProvenance.tsx:22` (`SOURCE_KEYS` nine)
- Modify: `apps/web/src/lib/constants.ts:212` (`330_000`), `.env.example:272`, `.env.prod.example:314`, local `.env`, `.env.prod`
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — under `journals`: `portraitStale`; under `journals.provenance`: `open_loops_one/_other`, `workboard_one/_other`, `routines_one/_other`, `reminders_one/_other`, `bookmarks_one/_other`, and `source.open_loops|workboard|routines|reminders|bookmarks` (use the `lia-i18n` skill; zh duplicates `_one`)
- Test: `apps/web/src/components/settings/__tests__/PortraitCard.test.tsx`, `apps/web/src/components/settings/__tests__/PortraitProvenance.test.tsx`, `apps/web/src/hooks/__tests__/useJournals.transport.test.ts:88-105`, `apps/web/src/hooks/__tests__/useJournals.application.test.tsx:99-106`

- [ ] **Step 1: Write the failing tests**

```tsx
it('says a recompilation is pending on a stale portrait and keeps its words', () => {
  renderWithProviders(<PortraitCard {...props} portrait={portrait({ stale: true })} />);
  expect(screen.getByText('journals.portraitStale')).toBeInTheDocument();
  expect(screen.getByText('A person who plans in the evening.')).toBeInTheDocument();
});
```

In `PortraitProvenance.test.tsx`: a provenance with `open_loops: { status: 'used', used: 4, total: 4 }` renders `data-parts` containing `open_loops:4`. In `useJournals.transport.test.ts` the `it.each` becomes « marks the portrait stale after %s even when its GET fails » asserting `portrait?.stale === true` and `portrait?.full === storedPortrait.full`. In `useJournals.application.test.tsx:99` the expectation becomes `expect(result.current.portrait?.stale).toBe(true)` with the words kept.

- [ ] **Step 2: Run them to verify they fail**: `cd apps/web && pnpm vitest run src/components/settings/__tests__/PortraitCard.test.tsx src/components/settings/__tests__/PortraitProvenance.test.tsx src/hooks/__tests__/useJournals.transport.test.ts src/hooks/__tests__/useJournals.application.test.tsx` → FAIL.

- [ ] **Step 3: Implement** the four source files and the six locales.

- [ ] **Step 4: Run the task's gate**: `task test:frontend && task lint:i18n && task lint:frontend` → PASS.

### Task 13: The decision is written — ADR-343, index, living maps, JOURNALS.md, CLAUDE.md

**Files:**
- Create: `docs/architecture/ADR-343-Portrait-Reads-The-Whole-Material-And-Its-Brief-Is-A-Synthesis.md` (Status Accepted, date, Amends: the ADR-292 line, ADR-079, ADR-284, ADR-269, the pipeline of commit 499c4cecc; Context = the measured table of the spec; Decision = D1-D6 with the simulation's figures; Consequences; What is NOT a source and why)
- Modify: `docs/architecture/ADR_INDEX.md` (append the ADR-343 block in the file's own format)
- Modify: `apps/web/src/data/maps/history.json` (`{"adr": 343, "date": "<date>", "theme": "memory", "functional": ["f.journals", "f.memory", "f.interests", "f.habits", "f.relations", "f.openloops", "f.workboard", "f.routines", "f.reminders", "f.bookmarks"], "technical": ["t.promptsys"]}` — check each functional id exists in `functional.json`)
- Modify: `apps/web/src/data/maps/text/history.{fr,en,de,es,it,zh}.json` (`entries["343"]`: a title and two or three plain sentences, French first, the five translations)
- Modify: `docs/technical/JOURNALS.md` (§ « Consolidation lease, proof and settlement » and « The four portrait sources » → nine, the window share, placement, review-then-pack, stale served)
- Modify: `CLAUDE.md` (one pointer of 2-4 lines in « Useful Documentation Pointers », the ADR-292 style) then `task docs:sync-agents`

- [ ] **Step 1:** Write the ADR and the index block; add the history entry and the six text units; `task docs:maps` (stamps the translations, regenerates `facts.json` and the French documents); `task release:sync-counts`.
- [ ] **Step 2:** Update JOURNALS.md and CLAUDE.md; `task docs:sync-agents`.
- [ ] **Step 3: Run the task's gate**: `task lint:docs:preview` → no finding (stage nothing; the preview reads what `git add -A` would stage).

### Task 14: The whole-tree gates and the cold adversarial review

- [ ] **Step 1:** `task lint` → green (backend, frontend, i18n, docs, ratchets, hygiene, lockfiles, ci-parity).
- [ ] **Step 2:** `task test:backend:unit:fast` → green; `task test:frontend:coverage` → thresholds hold.
- [ ] **Step 3:** `task test:backend:integration -- -k journal` → green on the dev PostgreSQL + Redis.
- [ ] **Step 4:** `task ci:fast` → green.
- [ ] **Step 5:** Cold adversarial review of EVERY changed file, line by line (`feedback_exhaustive_adversarial_review`): a fresh reviewer agent reads the diff (`git diff` + untracked files) against the spec and this plan, reports findings; fix each; re-run Steps 1-4.
- [ ] **Step 6:** Report to the owner: what changed, the gates' exact commands and results, what was left out and why. No commit.
