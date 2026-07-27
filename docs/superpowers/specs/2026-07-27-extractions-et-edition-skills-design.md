# Post-Response Extractions & Skill Editing — Verified Design

**Date:** 2026-07-27 · **Status:** arbitrations signed off, L1 in progress
**Baseline:** HEAD `7850de3d` (v1.25.27), **clean working tree**.
**Scope:** 6 lots — L1 metrics, L2 triviality scoping, L3 channel parity, L4 six-language
triviality, L5 HITL extraction coverage, L6 skill editing.

> **Re-verified 2026-07-27 after HEAD moved** from `be22777f` (v1.25.25) to `7850de3d`
> (v1.25.27). The two releases absorbed the previously-uncommitted ADR-162/163 streams, so
> the working tree is now clean and the overlap table below is **resolved — no action
> needed**. Re-measured, all unchanged: every logical-SLOC figure, every cyclomatic-complexity
> figure, and every `response_node.py` line reference. **Only `constants.py` shifted, by a
> uniform +16 lines** — the references in this document are updated accordingly.
> **ADR-163 is now taken**: the next free number is **164** (re-check `ADR_INDEX.md` anyway).

Every claim below was verified in-code on 2026-07-27, with `file:line` evidence inline.
The two questions that triggered this audit were:

1. Do plain chat exchanges feed long-term memory, interests and personal journals?
2. Can the assistant modify an existing skill, not just generate a new one?

The short answers — **mostly yes, with four holes** and **yes, the write engine already
exists** — are both counter-intuitive and are evidenced below. Read
`docs/superpowers/specs/2026-07-22-ux-refinements-program.md` for the sibling document
format.

---

## Working tree overlap — RESOLVED

At drafting time an ADR-162 system-RAG stream and a landing/FAQ stream sat uncommitted and
touched `core/constants.py` and `metrics_agents.py`. Both were released as v1.25.26 and
v1.25.27; the tree is clean and **no conflict remains**.

Still re-run `git status` at every lot start: this program spans multiple sessions, and the
next drift will not announce itself either.

---

## How to resume (session protocol)

1. Read memory `project_extractions_and_skill_editing.md` and
   `reference_skill_subagent_no_hitl.md`, then this document. The **status tracker**
   (bottom) says where the program stands.
2. Check the real state: `git log --oneline -5`, `git status`. If HEAD moved past the
   baseline, re-verify the volatile assumptions of the target lot — exact line numbers,
   ratchet headroom, and the overlap table above.
3. Write the granular implementation plan for **that lot only** in
   `docs/superpowers/plans/YYYY-MM-DD-ext-<lot>.md`, following `superpowers:writing-plans`.
4. Characterize before changing: every lot starts by pinning current behavior in a test
   that passes on the unmodified code, so the change is *proven*, not assumed.
5. Update the status tracker at the end of the lot. Never mark a lot done without the
   verification evidence its section requires.

---

## Findings — verified evidence

### What already works (the hypothesis is disproved for the nominal path)

The conversational path (`router → response`, `graph.py:99-135`) does reach
`post_response_extractions.py`, scheduled from `response_node.py:3724`. Six background
extractions run there: memory, interests, open loops, journal, psyche, recurrence ledger.

`tests/agents/test_response_node.py:488` already proves it: a single conversational
message schedules **both** memory and interest extraction.

`user_msg_is_trivial` is **not** a "simple exchange" filter. It requires ≤ 15 characters
**and** a match against one of three patterns (`user_message_embedding.py:82-103`,
`USER_MESSAGE_TRIVIAL_MAX_LENGTH = 15` in `constants.py:4289`). It means "ok / thanks / 👍",
not "a light conversation". The journal has no blocking floor either
(`JOURNAL_EXTRACTION_MIN_MESSAGES_DEFAULT = 1`, `constants.py:4255`).

### D1 — External channels never feed journals or psyche

`channels/inbound_handler.py:220-229` calls `stream_chat_response` with
`user_memory_enabled` but **neither** `user_journals_enabled` **nor**
`user_psyche_enabled`. The signature defaults then apply — `False`
(`agents/api/service.py:492-493`) — while the DB columns default to `True`
(`users/models.py:338` and `:431`).

The whole channel chain only knows `memory_enabled`: `channels/message_router.py:209`,
`channels/router.py:417`. The skip is logged at `debug`
(`post_response_extractions.py:249-253`), so it is invisible in practice.

No ADR and no test justifies excluding journals from channels — searched and confirmed
absent. This is a propagation omission, not a product decision.

### D2 — A HITL draft flow extracts nothing at all

| Turn | Path | Extraction |
|---|---|---|
| 1 — rich message → draft | `interrupt()` at `hitl_dispatch_node.py:671` suspends the graph **before** `response_node` | none |
| 2 — confirmation | `draft_action_result` set at `hitl_dispatch_node.py:737` / `:756` → fast path `response_node.py:3517-3547` `return`s **before** line 3724 | none |

The extraction prompt explicitly targets "the LAST user message"
(`prompts/v1/memory_extraction_prompt.txt:1`), so a later turn does not recover it.

**What makes the fix cheap:** draft resumption is a bare `Command(resume=...)` with **no
message injection** (`hitl/resumption_strategies.py:1057-1069`). At the fast path, the last
`HumanMessage` in state is still the original rich message. No message-selection logic is
needed — only the scheduling call.

**Constraint discovered:** `psyche_appraisal` (line 3640) and `final_content` (3632) are
defined **after** the fast path (3517). The call must pass `psyche_appraisal=None` — an
explicitly supported case (`psyche/service.py:1197` and docstring) — and
`final_content=short_response`. Verified available at 3517: `context_bundle` (3342-3344),
`previous_journal_injected_ids` (3407), `personality_instruction`, `user_language`,
`current_turn_registry`.

### D3 — The inverse defect: extraction runs on a synthetic message

On a tool-level HITL refusal, a fabricated `HumanMessage` is injected into state
(`hitl/resumption_strategies.py:756-763`) whose body is system scaffolding:
`[REFUS UTILISATEUR] … IMPORTANT: … NE mentionne AUCUN problème technique`
(`core/i18n_hitl.py:1434-1443`). It exceeds 15 characters, so it is not trivial: an
embedding is computed and four extraction LLM calls run against system scaffolding. Risk of
polluting long-term memory and the journal, plus pure cost.

**The marking mechanism already exists** — do not invent one.
`additional_kwargs["proactive_notification"]`, set at
`agents/services/orchestration/service.py:280`, is already honored by all three extractors:
`memory_extractor.py:222`, `interests/services/extraction_service.py:479`,
`journals/extraction_service.py:333`.

**Nuance:** the existing filter applies to *context formatting*, not to *target selection*
(memory picks the last `HumanMessage` at `memory_extractor.py:434-439`, before formatting).
Proactive messages are `AIMessage`s and are never the target; our synthetic message **is** a
`HumanMessage` and **is** the target. The new marker must therefore be honored in the
selection loop too, in all three extractors.

### D7 — Triviality is applied to inputs that are not user messages `[found while falsifying L4]`

`get_or_compute_embedding` runs `is_trivial_message` on **every** input
(`user_message_embedding.py:182`). Two callers do not pass a conversational message:

- `agents/tools/person_tools.py:179` — `get_or_compute_embedding(message=person_name)`,
  followed by `if not query_embedding: return None` (`:180-181`).
- `heartbeat/context_aggregator.py:924` — an internal hardcoded query.

Current patterns include `fine`, `cool`, `top`, `bien`, `super`, `parfait`
(`user_message_embedding.py:67-79`). **These are all real surnames.** Today, a contact named
Fine, Cool, Top or Bien silently loses every associated memory — the user concludes that
LIA "forgot".

This is a **pre-existing production defect**, independent of this program, and it makes L4
dangerous: adding `vale` (es), `bene` (it), `gut` / `ja` (de) adds more common surnames.
**L2 must therefore ship before L4, never the reverse.**

### D5 / D6 — Minor

- **No metric** on scheduled/skipped extractions. Only `journal_extraction_duration_seconds`
  exists (`metrics_journals.py:34`). This is precisely why the question could not be
  answered without reading the code.
- **Dead code**: `extract_memories_from_single_message` (`memory_extractor.py:872`) has no
  caller in `src/` or `tests/`. Violates the CLAUDE.md dead-code rule.
- **Hardcoded French**: `user_language = "fr"` at `channels/router.py:405`, where
  `message_router.py:209` correctly uses `settings.default_language`. Violates the i18n
  systemic rule.

### Skill editing — the write engine already exists

Upsert is a **designed** behavior, tested and documented:

- re-importing one's own skill is allowed (`skills/import_service.py:500-512`);
- exempt from quota (`:523-541`);
- atomic swap with backup and rollback (`:452-481`);
- tests: `test_own_reimport_allowed`, `test_quota_reimport_at_cap_allowed`,
  `test_swap_in_reimport_parks_previous_version` (`tests/unit/domains/skills/test_import_service.py`);
- documented in `docs/architecture/ADR-118-Chat-Driven-Skill-Import.md` lines 56, 88, 95.

Three locks prevent its use:

- **V1 — the manifest cannot be read.**
  `SKILLS_RESOURCE_SKIP_FILES = {"SKILL.md", "translations.json"}` (`constants.py:4014`)
  removes both from `all_resources` (`skills/loader.py:117-137`), and
  `read_skill_resource` rejects any path outside that list (`skills/tools.py:337`).
  `activate_skill` **strips the frontmatter** (`skills/activation.py:22`, `:42`). The
  assistant never sees `description`, `category`, `priority`, `plan_template`, `outputs`,
  `dialogue`, `compatibility`, `agent_visibility`.
- **V2 — silent data loss.** `_swap_in` replaces the **whole directory**. Any file not
  supplied disappears: `assets/preview.png` — served by the gallery
  (`skills/router.py:479`) and impossible to re-supply from chat since `.png` is absent
  from `SKILLS_IMPORT_TEXT_EXTENSIONS` (`constants.py:4023`) — and `translations.json`.
  Measured across the 14 system skills: **14/14 ship `assets/preview.png`**, 13/14 ship
  `translations.json`, 8/14 ship `scripts/`, 5/14 ship `references/`.
- **V3 — the prompt forbids updating.** `data/skills/system/skill-generator/SKILL.md:102-103`
  instructs: *"A name conflict means the name is taken: pick a close variant"*. The
  assistant is steered into creating a duplicate.

### Skill editing — where the code actually runs `[decisive]`

`_skill_needs_runner` returns `True` as soon as a skill ships a `scripts/` directory
(`response_node.py:1235-1240`). `skill-generator` ships `scripts/validate_skill.py`, so the
whole generation dialogue runs inside a `ReactSubAgentRunner` on an **isolated thread**
(`agents/tools/react_runner.py:92`, thread id at `:270`).

`react_runner.py` contains **no** mention of `draft`, `interrupt` or `pending`. A draft
created by a tool called from that sub-agent never reaches the main graph.

Consequences for confirmation:

- `hitl_required=True` is useless anyway — the pipeline's approval gate is a pass-through,
  documented at `agents/tools/devops_tools.py:191-195` and in CLAUDE.md;
- the draft is *"the ONLY mechanism that gates both execution modes"* (same comment), and it
  requires the tool to be called from the main graph — true for `devops_tools`, false for
  skills.

Confirmed available in the sub-agent: the full `skills_tools` list is wrapped and passed
(`response_node.py:1735`), i.e. `activate_skill_tool`, `run_skill_script`,
`read_skill_resource`, `import_user_skill` (`skills/tools.py:461`).

---

## Arbitrations signed off (2026-07-27)

| Question | Decision |
|---|---|
| Skill editing shape | **Full regeneration**, never a patch: read the manifest, understand the intent, rewrite the whole package |
| Delete-then-recreate vs re-import | **Re-import under the same name** — identical result, no destructive window, no skill-deletion tool handed to the model |
| Binary assets | **Server-side carry-over** from the backup for any extension chat cannot transport |
| Previous version | **Not kept** — irreversibility is accepted; the confirmation *is* the safeguard |
| Confirmation before overwrite | **Required** — see the two-phase mechanism below (HITL is unavailable in the sub-agent) |
| System skills | **Refused**, no fork offered |
| Another user's skill | **Refused**, existence not disclosed |
| Inactive skill | **Refused**, with a message telling the user to re-enable it |
| Channel parity | **Journals and psyche both enabled**, added latency accepted |

---

## Lots

Execution order is **L1 → L2 → L3 → L4 → L5 → L6**. L2 before L4 is a hard dependency
(D7). L5 before L6 is preferred: L6's confirmation flow exercises the draft/fast-path area
that L5 touches.

### L1 — Extraction observability

**Why first:** without it, L2-L5 are believed rather than verified.

**Change.** One counter in `infrastructure/observability/metrics_agents.py`, in its own
section (the parallel stream appends near line 1373 — keep distance):

```
post_response_extraction_scheduled_total{kind, outcome}
```

`kind` ∈ {memory, interests, open_loops, journal, psyche, recurrence}.
`outcome` ∈ {scheduled, automated_source, user_disabled, trivial, no_user, feature_disabled,
error}. Not every kind emits every outcome (memory has no global flag, open loops and psyche
do, recurrence additionally gates on intent) — 42 is the upper bound, not the expected
series count.

Instrument every branch of `post_response_extractions.py` — the file currently has one log
line per branch (`:78-93`, `:144-158`, `:199-206`, `:244-263`, `:311-321`, `:360-365`);
each gets a counter increment alongside, no restructuring.

**Tests.** `tests/unit/domains/agents/nodes/test_extraction_metrics.py` — one case per
outcome, asserting the label pair. Reuse the harness of
`test_open_loop_extraction_wiring.py`.

**Ratchet.** Size: `post_response_extractions.py` is at 303/600 logical SLOC — ample.
Complexity: `_schedule_post_response_extractions` is at **CC 41**, an existing hotspot. A
counter increment on an existing branch adds zero complexity — add no `if` there.

**Done when:** the six kinds and all outcomes are observable, and a local run of a
conversational turn shows `scheduled` on memory + interests.

### L2 — Scope triviality to conversational messages (D7)

**Why second:** it is a live user-visible bug, and L4 is unsafe without it.

**Change.** `is_trivial_message` must only govern *conversational* input. Add an explicit
opt-out parameter to `get_or_compute_embedding` (default preserves today's behavior for
conversational callers), and pass it from the two non-conversational callers:

- `agents/tools/person_tools.py:179` — a person name is never "trivial";
- `heartbeat/context_aggregator.py:924` — an internal query is never "trivial".

Do **not** silently reinterpret the flag: the parameter name must say what it means
(the docstring at `user_message_embedding.py:29-34` already lists which callers embed
something other than the user message — keep it in sync, per the CLAUDE.md rule that a
docstring contradicting the code is a bug).

**Tests.** `tests/unit/infrastructure/llm/test_user_message_embedding_scoping.py`:
a contact named `Fine` / `Bien` / `Top` yields an embedding (falsifies D7); a conversational
`ok` still yields `None`. Plus a regression test on `_fetch_person_memories` proving
memories are returned for such a contact.

**Ratchet.** `user_message_embedding.py` at 97/600 — ample.

**Done when:** the D7 test fails on unmodified code and passes after.

### L3 — Channel parity (D1 + D6)

**Change.** Propagate the two preferences across the three sites, mirroring
`user_memory_enabled` exactly:

- `channels/message_router.py:209` → read `journals_enabled` / `psyche_enabled`; `:234` →
  pass them;
- `channels/inbound_handler.py:55-75` (`handle`) and `:183` (`_stream…`) → add the
  parameters; `:228` → forward them to `stream_chat_response`;
- `channels/router.py:405` → replace the hardcoded `"fr"` with `settings.default_language`;
  `:417` → read the two preferences; `:455` → pass them.

**Latency note (accepted).** Channels go through the same `stream_chat_response`, hence
through `await_run_id_tasks(run_id, timeout=15.0)` (`agents/api/service.py:1366`). Two more
extraction tasks are awaited before the reply is sent. Measure it: record the delta on a
Telegram round-trip before/after and write it into the tracker.

**Verified non-risk.** Enabling psyche on channels cannot leak the `<psyche_eval>` tag:
streaming strips the fragments (`streaming/service.py:1905-1909`) and the channel prefers
`content_replacement` (`inbound_handler.py:283-290`), which carries the cleaned text.
Keep this property under test.

**Signature decision.** Make the two parameters **keyword-only and required**, mirroring
`user_memory_enabled` — an optional parameter with a `False` default would reproduce exactly
the defect being fixed the next time a caller is added. Consequence: the 15 existing call
sites in `tests/unit/domains/channels/test_inbound_handler.py` (14 `.handle(` calls) and
`test_message_router.py` (1) must be updated in the same commit. That is the point: the
compiler-like failure is the guard.

**Tests.** `tests/unit/domains/channels/test_preference_propagation.py`: the three sites
forward the DB values (mirroring the existing `user_memory_enabled` assertions at
`test_inbound_handler.py:166-175`); a missing user falls back to safe defaults; the psyche
tag never appears in the text returned by `_stream…`.

**Ratchet.** Size: `inbound_handler.py` 269/600, `message_router.py` 198/600 — ample.
Complexity: see the CC section — `_handle_hitl_callback` is at 14, **one branch from
crossing 15**. The preference reads go inside the existing `if user:` blocks as `getattr`
calls: zero new branches. Verify with `measure_cc.py --check-ratchet`.

### L4 — Six-language triviality

**Blocked by L2.** Do not start before L2 is merged and its test is green.

**Change.** Extend `_TRIVIAL_PATTERNS` (`user_message_embedding.py:67-79`) to de, es, it, zh.
CLAUDE.md requires all six languages; today only fr and en are covered, so `ja`, `sí`, `sì`,
`好的` each cost one embedding plus up to four extraction LLM calls.

**Mandatory precaution.** Every added token must be checked against the surname risk that
D7 exposed. Prefer patterns that are unambiguous acknowledgements; when in doubt, leave the
token out — a missed skip costs tokens, a false skip loses data.

**Tests.** Table-driven: one acknowledgement per language is trivial; one short meaningful
message per language is not; and — the regression oracle — the L2 person-name path is
unaffected by the new patterns.

### L5 — HITL extraction coverage (D2 + D3 + D5)

**Change A — schedule on the draft fast path.** Call
`_schedule_post_response_extractions` before the `return` at `response_node.py:3547`, with
`psyche_appraisal=None` and `final_content=short_response`. All other arguments are already
in scope (verified above).

**Change B — mark synthetic HITL messages.** The three extractors each repeat the same
"scan backwards for the last `HumanMessage`" loop, inside functions at CC 69, 76 and 34.
Extract **one shared helper** that skips marked messages, and call it from all three: this
deduplicates, makes the marker a single source of truth, and lowers all three hotspots
instead of growing them. Then, at
`hitl/resumption_strategies.py:756-763` (and the two fallback branches at `:783` and `:798`),
tag the injected `HumanMessage` with an `additional_kwargs` marker, mirroring
`proactive_notification`. Honor it in the three extractors, **in both** the target-selection
loop and the context formatter:
`memory_extractor.py:222` + `:434-439`, `interests/…/extraction_service.py:479`,
`journals/extraction_service.py:333`.

Never detect these messages by string-matching their content — the CLAUDE.md tool rule
forbids classification by message text, and the strings are localized.

**Change C — delete dead code.** Remove `extract_memories_from_single_message`
(`memory_extractor.py:872-893`).

**Verified non-risk.** The message-repair filter that deliberately drops
`additional_kwargs` only handles `AIMessage`s carrying `tool_calls`
(`agents/utils/message_filters.py:708`) — a marked `HumanMessage` is untouched. Add a test
pinning this, plus one proving the marker survives a checkpoint round-trip.

**Expectation calibration.** The memory prompt deliberately excludes *"transient logistics —
appointments, reservations, meetings, calls"*. Most HITL turns are exactly that, so the
memory gain is narrow by design. The real beneficiaries are **journals and interests**, plus
the minority of turns carrying a durable fact alongside the action ("tell Marie I'm moving
to Lyon"). Do not claim more in the changelog.

**Known limitation to state explicitly.** On a refusal, extraction now targets the original
rich message; the wording of the refusal itself ("no, she moved") is never extracted,
because it exists in history only embedded inside the system-scaffolded message.

**Tests.** Characterization first: pin that today a confirm turn schedules nothing. Then:
draft confirm / cancel / confirm_batch schedule **the extractions their own guards allow** —
not "all six" (psyche needs both flags, recurrence needs `intent == "action"` and a primary
domain, open loops needs `open_loops_enabled`); assert per kind, using the L1 counter as the
oracle. Plus: a refusal turn does not target the synthetic message, and the marker survives a
checkpoint round-trip.

**Ratchet — tight.** Size: `response_node.py` measures **2317** logical SLOC against a frozen
**2364** (`tests/unit/file_size_baseline.json`): **47 lines of headroom**. Change A must stay
small; if it does not fit, extract rather than raise the cap — the baseline is shrink-only.
Complexity: Change A adds a call, not a branch, to `response_node` (CC 24); Change B adds
`additional_kwargs` to three existing `HumanMessage` constructions in
`_build_tool_level_command` (CC 27) — zero branches. The shared helper above is what keeps
the three extractor hotspots from growing. Verify with `measure_cc.py --check-ratchet`.

**ADR.** This changes the systemic contract of which turns feed the user's long-term state.
Write an ADR (next free number after 162 — re-check `docs/architecture/ADR_INDEX.md` at
implementation time, a parallel stream may have claimed it) and index it.

### L6 — Skill editing

**Flow (as arbitrated).** The user asks for an adjustment → the assistant reads the
catalogue description **and** the `SKILL.md` to understand the skill's purpose → merges it
with the request → regenerates the **entire** package as if generating a new skill → the
package replaces the old one under the same name.

**Change A — unlock reading.** Allow `read_skill_resource` to serve `SKILL.md` and
`translations.json`. Implement this **in the tool only** (`skills/tools.py:336-341`), not by
editing `_discover_all_resources` (`skills/loader.py:117-137`): the latter feeds the
`<skill_resources>` block of **every** skill activation (`skills/activation.py:49-64`),
so changing it would inflate every prompt and alter behavior unrelated to editing.

Note: `read_skill_resource` currently performs blocking disk I/O on the async path
(`:354`, `:361`, `:369`) while `import_service` carefully offloads via `asyncio.to_thread`.
Fix it here (Boy Scout rule, CLAUDE.md async rule).

**Change B — two-phase confirmation, fail-closed.** HITL is unavailable in this execution
context (see the decisive finding). Therefore the confirmation lives **in the tool**:

1. `import_user_skill` detects that the name already exists and belongs to the caller →
   replacement mode.
2. Without an explicit confirmation argument it **refuses**, returning a structured failure
   enumerating exactly what would be lost — files present in the current version and absent
   from the supplied map.
3. The assistant surfaces that to the user and obtains agreement in conversation.
4. A second call carrying the confirmation performs the replacement.

The guarantee is **structural, not declarative**: even if the model ignores its prompt, it
cannot overwrite in a single call. This mirrors the intent stated at `devops_tools.py:188-190`
— the confirmation does not depend on an LLM judging the action destructive.

Two side effects to handle: the first refusal must not count as an error in the tool
metrics, and must not consume the rate-limit budget — `_RATE_LIMIT_IMPORT = 5` per 60 s
(`skills/tools.py:88`) would otherwise allow only 2.5 edits per minute.

**Change C — carry over non-transportable files.** In `_finalize`
(`import_service.py:405-441`), after `_swap_in`, copy back from `backup_dir` every file whose
extension is absent from `SKILLS_IMPORT_TEXT_EXTENSIONS`. **Chat path only**
(`import_files`): a zip upload must remain a full replacement, with no side effects.

**Change D — package integrity, blocking.** After reconstitution, reject (not warn):
`outputs` declaring `frame` or `image` with no `scripts/` file present; and any resource
listed under `## Ressources disponibles` that is absent from the package. Today this is only
a generator-side warning on the manifest text (`skill-generator/scripts/validate_skill.py:234`),
never checked against the real package.

**Change E — the three guards.** In `import_user_skill`, before anything else:
system skill → explicit refusal, **no fork offered**; another user's skill → the existing
undifferentiated 409 (`import_service.py:500-512`), unchanged; skill not active → refusal
telling the user to re-enable it. Use `get_active_skills_for_user`
(`skills/preference_service.py:50-56`). The third guard is not redundant: an inactive skill
is absent from the injected catalogue (`skills/injection.py:71-76`), but
`SkillsCache.get_by_name_for_user` does not filter on activity (`skills/cache.py:126-140`),
so a user naming it explicitly would otherwise edit a disabled skill unknowingly.

**Change F — orchestration.** Replace the conflict instruction at
`data/skills/system/skill-generator/SKILL.md:102-103` with an edit mode: read, understand,
regenerate in full, re-import under the same name, surface the confirmation.

**i18n.** Every new user-facing string (three refusals + the confirmation summary) goes
through the central backend i18n mechanisms in all six languages, `zh-CN` as the backend
canonical code. No inline French, including fallbacks and parameter defaults.

**Ratchet.** Size: `skills/tools.py` 322/600, `import_service.py` 317/600 — ample.
**`skills/router.py` is at exactly 600/600 — saturated.** No endpoint may be added there
without extracting a cohesive module first. This design deliberately requires none.
Complexity: `import_user_skill` is at CC 8 and this lot adds roughly six branches — the
sharpest crossing risk of the program. Put the three guards and the replacement detection in
dedicated helpers, not in the tool body. Verify with `measure_cc.py --check-ratchet`.

**ADR.** New tool contract plus a new destructive-confirmation pattern for sub-agent
context. Write an ADR and index it in `docs/architecture/ADR_INDEX.md` and `docs/INDEX.md`;
update `docs/technical/SKILLS_INTEGRATION.md` and cross-reference ADR-118.

---

## What was ruled out (do not re-investigate)

Each was suspected, investigated and **disproved** with evidence:

| Hypothesis | Verdict |
|---|---|
| Voice exchanges bypass extraction | **No** — voice goes through `/chat` (the request carries `stt_provider`, `stt_audio_duration_seconds`) |
| Telephony bypasses extraction | **Out of scope** — an outbound ElevenLabs agent calling a third party, not a user↔LIA exchange |
| Scheduled actions / heartbeat silently skipped | **By design** — `is_automated_source`, with a dedicated test (`test_response_node.py:453`) |
| Background tasks cancelled before completion | **No** — `await_run_id_tasks` is called on the nominal path (`agents/api/service.py:1366`) |
| Enabling psyche on channels leaks `<psyche_eval>` | **No** — stripped in streaming and superseded by `content_replacement` |
| The `additional_kwargs` marker is erased by message filters | **No** — that filter only handles `AIMessage`s with `tool_calls` |
| `psyche_appraisal=None` is unsafe | **No** — explicitly supported (`psyche/service.py:1197`) |
| A `.pyc` inside `skill-generator/scripts/` is committed | **No** — gitignored, a local artifact |
| Other callers of `stream_chat_response` need the same fix | **No** — four callers total; the fourth (`scheduled_action_executor.py:235`) must stay excluded |

---

## Cyclomatic complexity constraint (measured 2026-07-27)

The file-size ratchet is not the only structural gate. `apps/api/.cc-baseline.json` freezes
two **aggregate** caps — `over: 346` (functions at CC ≥ 15) and `max: 87` (worst function) —
and `test_cc_ratchet_guard.py` fails on regression only (`cur > base`).

The trap this creates: growing an already-counted hotspot is invisible to the gate, but a
function **crossing** 15 pushes `over` to 347 and reds the build. Independently, CLAUDE.md is
stricter than the gate: *"Do not add a function with cyclomatic complexity >= 15 **or grow an
existing hotspot**"*. Both rules apply.

| Function | CC | Touched by | Consequence |
|---|---|---|---|
| `journals/extraction_service.py::extract_journal_entry_background` | **76** | L5 | hotspot — must not grow |
| `memory_extractor.py::extract_memories_background` | **69** | L5 | hotspot — must not grow |
| `_schedule_post_response_extractions` | **41** | L1 | hotspot — must not grow |
| `interests/…::extract_interests_background` | **34** | L5 | hotspot — must not grow |
| `resumption_strategies.py::_build_tool_level_command` | **27** | L5 | hotspot — must not grow |
| `response_node.py::response_node` | **24** | L5 | hotspot — must not grow |
| `channels/message_router.py::route_message` | **18** | L3 | hotspot — must not grow |
| `channels/router.py::_handle_hitl_callback` | **14** | L3 | **one branch from crossing** |
| `channels/inbound_handler.py::handle` | **11** | L3 | close to the threshold |
| `skills/import_service.py::_finalize` | **10** | L6 | headroom |
| `skills/tools.py::read_skill_resource` | **9** | L6 | headroom |
| `skills/tools.py::import_user_skill` | **8** | L6 | **+6 estimated → grazes 15** |

**Strategies, per lot:**

- **L1** — a counter increment on an existing branch adds **zero** complexity. Add no `if`
  to `_schedule_post_response_extractions` (CC 41). If a helper feels needed, extract it;
  never inline logic there.
- **L3** — the two preference reads are `getattr` calls placed inside the **existing**
  `if user:` blocks (`channels/router.py:417`, `message_router.py:209`): zero new branches.
  Adding one guard to `_handle_hitl_callback` (CC 14) would cross the threshold and red the
  build — do not.
- **L5** — the three extractors repeat the same "find the last `HumanMessage`" loop
  (`memory_extractor.py:434-439` and equivalents). Do **not** add the marker check inline in
  three hotspots at CC 69/76/34. Extract one shared helper — it deduplicates, centralizes the
  marker as a single source of truth, and **lowers** all three host functions. Change A adds a
  call, not a branch, to `response_node` (CC 24). Change B adds `additional_kwargs` to three
  existing `HumanMessage` constructions in `_build_tool_level_command` (CC 27): zero branches.
- **L6** — this is the sharpest risk. `import_user_skill` sits at CC 8 and the lot adds three
  guards plus two-phase confirmation plus replacement detection (~+6). Put the guards in a
  dedicated helper (e.g. `_reject_uneditable_target`) rather than in the tool body, so the
  tool stays well under 15.

**Verification:** run `python scripts/audit/measure_cc.py --check-ratchet` at the end of every
lot, alongside the file-size guard. Never regenerate the baseline to absorb a regression;
`--update-ratchet` is only for real decomposition work.

## Cross-cutting constraints

- **Shrink-only ratchets.** Never raise a size baseline or lower a coverage floor. After
  each lot adds tests, consider raising the backend coverage floor to lock the gain,
  keeping ≥ 2 points of margin (`pyproject.toml` and `ci.yml` must move together).
- **Verification per lot:** `task lint`, `task test:backend:unit:fast`, the lot's own suite,
  **and `python scripts/audit/measure_cc.py --check-ratchet`**. `task ci:fast` before any
  push. Never `task test:backend:exhaustive`.
- **Test markers.** Every new test file must satisfy the F006 gate (`task test:markers`): a
  test running in zero CI jobs is a test nobody runs.
- **No git actions** without the user's explicit request.
- **Evidence before completion:** a lot is done when its characterization test failed on the
  old code and passes on the new one — not when the code "looks right".

---

## Status tracker

| Lot | Status | Evidence |
|---|---|---|
| L1 — extraction metrics | ✅ done | 9 tests; counter moved to a dedicated `metrics_extractions.py` — the file-size ratchet caught that `metrics_agents.py` is frozen at 829 SLOC; hotspot unchanged at CC 41 |
| L2 — triviality scoping (D7) | ✅ done | 11 tests; the person-memory test **failed before** the fix (`assert None == [...]`, DB never queried) |
| L3 — channel parity (D1, D6) | ✅ done | 8 tests + 15 existing call sites updated; duplication extracted to `channels/preferences.py`, which **lowered** `_handle_hitl_callback` 14→11 and `route_message` 18→16 |
| L4 — six-language triviality | ✅ done | 28 tests; `gut`/`vale`/`bene`/`claro` deliberately excluded as surnames, with a regression oracle pinning the exclusion |
| L5 — HITL coverage (D2, D3, D5) | ✅ done | 21 tests; falsified by removing the fix (test failed) then restoring (passed); shared helper **lowered** memory 69→67 and journal 76→74 |
| L6 — skill editing | ✅ done | 33 tests; ADR-164 + ADR-165 written and indexed; `import_user_skill` kept at CC 10 by extracting `_precheck_import` (it had reached 14, one branch from the threshold) |

**Verification (2026-07-27, after the review pass):** `task lint` EXIT=0 (backend +
frontend + i18n + docs + all shrink-only ratchets) · `pytest tests/unit` **14 449 passed,
0 failed** · `pytest tests/agents` **1 162 passed, 0 failed** ·
`measure_cc.py --check-ratchet` OK (346 / max 87, unchanged) · file-size ratchet green ·
F006 marker gate OK.

### Defects found reviewing this very work (all fixed)

Written down because each was invisible to the tests that shipped with it:

1. **The integrity check rejected `skill-generator` itself.** `_declared_resources`
   parsed the sample SKILL.md the generator *shows* inside a fenced code block as a real
   declaration. Fenced blocks are now stripped, and the extension pattern tightened so a
   bullet like "- 1.5 seconds" is not read as a file. Verified against all 14 shipped
   skills: 18 declared resources found, 0 missing.
2. **`confirm_replace=True` on the first call bypassed the confirmation.** The ADR
   claimed the guarantee was structural; a boolean the model can set unprompted made it
   declarative. Replaced by a content-derived `replace_token` the model can only obtain
   by being refused first — which additionally binds the approval to the exact package,
   so a summary shown and a package written can no longer differ.
3. **The embedding was computed on the fabricated HITL message.**
   `extract_last_user_message` did not skip synthetic messages, so on a refusal turn the
   triviality verdict, the paid embedding and the injected memory/journal context all
   keyed off system scaffolding — while the extractors, now fixed, targeted the real
   message. The two ends were desynchronized.
4. **`get_by_name` resolved any scope.** A name held by both a system skill and the
   caller's own could report read-only, refusing to edit something the user owns. The
   caller's skill now wins, mirroring the resolution the assistant sees.

**Deliberately not done** — needs a running stack, not a unit test: measuring the added
Telegram latency from the two extra awaited extractions (L3), and reading the new counter
against real traffic to confirm the extraction rates.
