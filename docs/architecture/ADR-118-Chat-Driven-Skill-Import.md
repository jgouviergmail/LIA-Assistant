# ADR-118: Chat-Driven Skill Import — Direct Delivery from the Skill Generator + Hardened Import Pipeline

**Status**: ✅ IMPLEMENTED (2026-07-09)
**Author**: Claude Code (Fable 5)
**Related**: `apps/api/src/domains/skills/import_service.py`, `apps/api/src/domains/skills/tools.py`, [SKILLS_INTEGRATION.md](../technical/SKILLS_INTEGRATION.md), [ADR-075 (Rich Skill Outputs)](ADR-075-Rich-Skill-Outputs.md), [ADR-063 (cross-worker cache invalidation)](ADR_INDEX.md)

## Context

The skill-generator produced complete, validated skills… and then asked the
user to copy each file from fenced code blocks, recreate the folder layout by
hand, zip it, and upload the result in Settings — four failure-prone manual
steps for content the backend already held in full. Worse, a 2026-07 audit of
the import pipeline the manual upload relies on found four defects:

1. **S1 — path traversal (critical).** `_extract_single_md` concatenated the
   frontmatter `name` into the destination path and wrote without validation
   (the loader only *warns* on invalid names). `name: ../../system/qr-code`
   let any authenticated user overwrite a **system** skill's SKILL.md —
   persistent instruction poisoning for every user, on skills that are
   trusted (no CSP injected on their frames).
2. **S2 — cross-scope name collision.** `skills.name` is globally unique
   while the cache implements per-user override semantics. A user import
   reusing a system skill's name silently rewrote the system row's
   description (DB is the display source of truth) for everyone; reusing
   another user's name updated *their* row and left the importer without a
   `user_skill_state` (ghost skill).
3. **S3 — zip expansion.** No decompressed-size or member-count guard
   (zip bomb: 100 KB compressed ≈ 100 MB inflated on the RPi5), and
   `extractall` wrote the entire archive even though only the first
   SKILL.md's directory was validated and registered — a multi-root zip
   could silently overwrite the user's other skills.
4. **S4 — validation divergence.** The generator's `validate_skill.py` was
   strict and promised "will be REJECTED by the importer"; the importer was
   lenient. Two contradicting sources of validation truth.

Additionally (**S5**), script-skills run in an isolated `ReactSubAgentRunner`
spawned fresh each turn with only the *last user message* — the
skill-generator's multi-turn dialogue (clarify → answer → generate) lost all
context between turns.

On the risk model for chat-driven import: an imported skill is a persistent
prompt-injection surface, but its blast radius in LIA is tightly bounded —
user-scoped only, script sandbox (subprocess, rlimits, privilege drop),
strict CSP on user-skill frames, a visible badge on every skill-driven
message, and one-click disable/delete in Settings. Given detection-at-use
(badge) and trivial reversibility, a heavyweight consent gate was judged
disproportionate.

## Decision

**1. One hardened import pipeline** — `SkillImportService` centralizes every
import path (user upload, admin upload, chat tool): strict agentskills.io
name validation *before any filesystem write* (closes S1 and aligns importer
with the generator's validator — closes S4), import-time rejection of user
imports that shadow a system skill or collide with another user, own-skill
re-import upserting (closes S2 without a schema migration), zip staging with
decompressed-size cap, member-count cap, per-member zip-slip check, and
extraction limited to the SKILL.md subtree into a temp directory that is
atomically swapped into the live tree (closes S3). Router endpoints become
thin delegates (service-layer rule §11).

**2. Direct chat import** — new `import_user_skill` tool (in `skills_tools`,
available to the skill runner and the main graphs) takes the generated files
as a `path → content` map (text-only extensions), runs the same pipeline, and
registers + activates the skill immediately. The skill-generator's Phase 4 is
rewritten: validate → import via tool → **announce the skill by name** with a
pointer to Settings › LIA Skills › My Skills; the code-block delivery
protocol survives only as a fallback when the tool fails twice. Feature-flag:
`SKILLS_CHAT_IMPORT_ENABLED` (default on), guards: `@rate_limit` 5/min,
per-user quota, size budgets shared with zip imports.

**3. Multi-turn skill dialogues (S5)** — two complementary mechanisms:

- *History*: the response node embeds the windowed `conversation_history` in
  the runner task inside a `<conversation_history>` block, and the runner
  prompt instructs the sub-agent to *resume* the dialogue instead of
  restarting it.
- *Routing*: the QueryAnalyzer's chat override cleared any detected
  `skill_name` on confidently conversational turns (anti-contamination for
  one-shot skills) — which structurally killed dialogue skills, since the
  user's answer to the skill's own question IS conversational. Skills now
  opt in via a `dialogue: true` frontmatter extension (loader
  `EXTENSION_FIELDS`); the override preserves their detection
  (`chat_override_kept_dialogue_skill`) while one-shot skills keep the
  anti-contamination. The skill-generator declares it; a data-level test
  pins the flag.

**4. Failure atomicity** — the previous version of a re-imported skill is
parked in the staging temp root during the disk swap and restored on any
post-swap failure (DB registration, commit): a failed import can neither
destroy an existing skill nor leave disk and DB diverging. A lost
registration race (identity guard in `create_skill_for_import`) rolls the
disk back and answers the same 409 as the up-front check. Conflict and quota
checks read both the DB (registration authority) and the cache (disk view);
re-importing one's own skill is exempt from the quota (it creates nothing).

**5. Anti-drift parity tests** — the skill-name contract exists in three
places by necessity (loader, import service, sandboxed `validate_skill.py`
which cannot import app modules); a parity test pins the three patterns,
prefixes and length limits together. The generator script's hardcoded
`VALID_AGENTS` is pinned against `DOMAIN_REGISTRY` (single source of truth):
removed/renamed agents fail CI, and a new taxonomy agent must be consciously
classified (script or explicit exclusion list).

## Alternatives considered

- **HITL confirmation gate (frontend button / draft card, stage-then-commit)**
  — rejected as disproportionate: the blast radius of a user skill is bounded
  (sandbox + CSP + badge + reversibility), the skill badge makes every
  activation visible, and the import is announced by name in the chat. The
  conversational flow already carries the user's intent ("create me a
  skill"). Revisit if skills ever gain capabilities that escape the sandbox.
- **Unique `(name, owner_id)` schema migration** — rejected for now: the
  import-time conflict rejection closes the S2 bug without touching the DB
  contract that `get_by_name` consumers rely on. May be revisited if
  cross-user name reuse becomes a product requirement.
- **LLM re-emitting files from history into a next-turn tool call** —
  rejected: verbatim reproduction of multi-KB Python scripts by the LLM
  invites silent corruption; same-turn import keeps a single transit.

## Consequences

- Generated skills are usable seconds after generation; no manual assembly.
- The manual upload path is strictly *more* validated than before (S1-S4) —
  existing valid skills are unaffected; imports with malformed names that
  previously slipped through as warnings are now rejected with a clear 400.
- User imports can no longer shadow system skills (behavior change,
  documented in the knowledge base); cache-level override semantics remain
  for pre-existing data.
- Multi-turn skill dialogues (and any future conversational skill) work
  across turns thanks to the history block — one-shot skills just gain
  context.
- Tests: `test_import_service.py` (S1-S4 pinned), `test_import_tool.py`
  (tool contract), `test_skill_runner_history.py` (S5 contract).
