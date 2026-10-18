# Expressive TTS cues — radio and voice comments — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every TTS engine LIA offers receives, automatically and where pertinent, the expressive
directions its vendor documents — in the voice comment and on the radio — and the catalogue states
the shutdown dates Google announces.

**Architecture:** ADR-345 already holds ONE canonical cue vocabulary (`voice/expressive_cues.py`)
spelled per engine by a `CueDialect`. This plan completes the dialect table from the vendors' pages
re-read on 2026-10-17, lets a dialect perform a delivery cue as a per-request control (Gemini 3.8
`style`), gives every cue a meaning the voice-comment writer reads, and lets the radio writer ask
for a vocal reaction opening a line, bounded and repaired by the deterministic verifier.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, pytest, Alembic, structlog, Prometheus, Grafana.

**Spec:** the proposal approved in conversation on 2026-10-17 (owner: « tu peux même prendre un
budget jusqu'à 2 euros, je veux vraiment un travail approfondi et abouti »), summarised in memory
`project_tts_expressive_cues_audit_2026_10_17`.

## Global Constraints

- Work in the `main` working tree `D:\Developpement\LIA`; never stage, commit or branch.
- No call to the Anthropic API; every paid call is counted and the total stays under 2 €.
- A radio session is started only on the proof account, never on the owner's.
- Model-facing text is technical English and generic; examples in English only (ADR-256, ADR-284).
- A bound a prompt publishes is the one the code enforces, read from ONE constant or setting.
- MyPy strict, Ruff, Black 100, file-size ratchet, cyclomatic complexity < 15 per function.
- New setting → `core/constants.py` default, `core/config/radio.py` field, `.env.example`,
  `.env.prod.example`, the four demo `.env` files.

## Review Focus

1. A spelling meant for one engine reaching another — a `<break>` on Eleven v3/v4, a `style` on a
   Gemini model that answers 400 to any annotation (the 2.5 and 3.1 previews): test per dialect and
   a guard that a dialect with styles is only mapped to models whose family declares `STYLE_PROMPT`.
2. A third party's text performing a direction — `<break time="9s"/>` in an answer read aloud on an
   Eleven v2 engine, `[laughs]` in a headline: `neutralize_literal` tests for the new dialect.
3. A radio reaction surviving where forbidden — a fact line, a news format, the announce line copied
   from the first story line, a script past the bound: verifier tests, including after
   `drop_unsupported`.
4. A style cue that is not counted, or a sentence reduced to nothing: the budget holds across style
   and inline cues; a sentence whose only content was its cue is never sent empty.
5. A style sent where nothing asked for one: no cue → no `style` kwarg at all (Gemini then keeps its
   default delivery).

---

### Task 0: Baseline measurement of the voice-comment cues (BEFORE any code change)

**Files:** scratchpad only (`…/scratchpad/measure/voice_cues.py`, results JSON).

- [ ] Build the REAL prompt through `VoiceCommentService._build_prompt` with
  `expressive_cues_block(ELEVENLABS_AUDIO_TAGS, settings.voice_expressive_cues_max)`, on a fixed
  synthetic corpus (12 contexts: routine success, failure, empty, awaited good news, funny result,
  bad news for the person, deadline warning, surprising finding, long search ended, late night,
  multi-option result, French and English), two personalities (`normal`, `friend`), the real
  `psyche_embodied_proactive` template for three inner moods.
- [ ] Generate through `get_llm("voice_comment", config_override=...)` on three non-Anthropic
  families configured on dev (DeepSeek, OpenAI, Google), 2 samples each.
- [ ] Score deterministically: cues per comment, invented/unknown cues, cue on a context that
  expects none, cue outside the context's allowed set, budget overruns. Save tokens and cost.

### Task 1: Dialects completed from the vendors' pages

**Files:**
- Modify: `apps/api/src/domains/voice/expressive_cues.py`
- Test: `apps/api/tests/unit/domains/voice/test_expressive_cues.py`

**Interfaces — Produces:**
- `Cue.CONCERNED = "concerned"` in `DELIVERY_CUES`.
- `CueDialect.styles: Mapping[Cue, str]` (default empty); `performs()` = spellings ∪ styles;
  `style(cue) -> str | None`.
- `ELEVENLABS_SSML_BREAK: CueDialect` — `{Cue.SHORT_PAUSE: '<break time="0.5s" />'}`; mapped to
  `eleven_multilingual_v2`, `eleven_flash_v2`, `eleven_turbo_v2` prefixes (after the v3/v4 rules).
- Fish S2 `concerned="[worried]"`, S1 `Cue.CONCERNED: "(worried)"`; Gemini 3.8 `styles` = every
  delivery cue → its English word.
- `AuthoredSentence(text: str, style: str | None)` with `controls() -> dict[str, str]`;
  `AuthoredCues.render(sentence) -> AuthoredSentence`: the FIRST delivery cue a style dialect
  performs becomes `style` (later ones dropped), every cue counts against the budget.

- [ ] Tests first: new dialect performs only the pause and spells `<break time="0.5s" />`; Eleven
  v3/v4 never get a `<break>`; an angle tag in literal text is markup to the v2 engines; Gemini 3.8
  performs every cue (events inline, delivery as style) and `render` returns
  `AuthoredSentence("Bon.", "warm")` for `"[warm] Bon."`; a second delivery cue in the sentence is
  dropped; budget counts styles; no cue → `style is None`; `[concerned]` per dialect; guard: a dialect
  with styles maps only to models whose `controls_for` holds `STYLE_PROMPT`.
- [ ] Implement; run `pytest tests/unit/domains/voice/test_expressive_cues.py -q` → pass.

### Task 2: The voice comment speaks its cues and knows what each one means

**Files:**
- Modify: `apps/api/src/domains/voice/service.py` (`stream_voice_comment._synth`)
- Modify: `apps/api/src/domains/voice/cue_prompt.py`
- Modify: `apps/api/src/domains/agents/prompts/v1/voice_expressive_cues_lines.txt`
- Test: `apps/api/tests/unit/domains/voice/test_cue_prompt.py`, `test_service.py`

**Interfaces — Consumes:** Task 1 `AuthoredSentence`, `CueDialect.performs()`.

- [ ] Lines file: one `meaning.<cue>` row and one `example.<cue>` row per `Cue` (generic English);
  `cue|` row renders `[cue] — meaning`; `rules` says most comments need none, a cue only when its
  meaning fits the result, the personality and the `<InnerVoice>` state; none on a plain
  confirmation, a failure or a sober status (Heuristic 9).
- [ ] Renderer lists ONLY performed cues, each with its meaning; example = the example row of
  `WARM` (delivery) else the first performed delivery cue, else `SIGHS`, else the first event.
- [ ] Guard tests: every `Cue` has a meaning and an example row; the block lists exactly the
  performed cues; the example is a performed cue; published budget = enforced budget.
- [ ] `_synth` passes `**authored.controls()` to `speak`; test: a Gemini 3.8 sentence opened by
  `[warm]` is synthesized with `style="warm"` and without the cue in the text.

### Task 3: Radio — a vocal reaction where it belongs, and `concerned` played as such

**Files:**
- Modify: `apps/api/src/domains/radio/script.py` (`Reaction`, `RadioDelivery.reaction`)
- Modify: `apps/api/src/domains/radio/formats.py` (`FormatSpec.reactions_allowed`, `_spec(reactions=)`)
- Modify: `apps/api/src/domains/radio/verification.py` (`REACTION_KINDS`, repair after ordering;
  `verify_script(..., reactions_max: int)` keyword-only)
- Modify: `apps/api/src/domains/radio/delivery.py` (`_TONE_CUES[CONCERNED] = Cue.CONCERNED`,
  `_REACTION_CUES`, `performed_reactions(dialect) -> tuple[Reaction, ...]`, reaction appended to the
  opening cue, `reaction` reported when unrendered)
- Modify: `apps/api/src/domains/radio/production.py` (`ProductionLimits.reactions_max`, pass to verifier)
- Modify: `apps/api/src/domains/radio/prompting.py` + `writing.py` + `adapters.py` + `settings_view.py`
- Create: `apps/api/src/domains/agents/prompts/v1/radio_reaction_lines.txt` (+ `PromptName`)
- Modify: `radio_writer_prompt.txt` (`{reaction_rule}` under DELIVERY)
- Modify: `core/constants.py` (`RADIO_REACTIONS_MAX_DEFAULT = 2`), `core/config/radio.py`
  (`radio_reactions_max`, 0–5), `.env.example`, `.env.prod.example`, demo `.env` ×4
- Test: `tests/unit/domains/radio/test_delivery.py`, `test_verification.py`, `test_prompting.py`,
  `test_formats.py` (or the file holding the spec guards)

**Interfaces — Produces:** `Reaction(StrEnum)`: `none | laughs | chuckles | sighs`;
`FormatSpec.reactions_allowed: bool` (true: opening, sign_off, column, debate, discussion);
reactions kept only on `opinion` and `transition` lines, at most `reactions_max` per script in air
order; `render_writer_prompt(..., reactions: Sequence[Reaction], reactions_max: int)`.

- [ ] Tests first (verifier): a reaction on a fact line → none; in a news bulletin → none; the third
  reaction with max 2 → none; max 0 → none everywhere; the announce line never carries one; after
  `drop_unsupported` the bound still holds.
- [ ] Tests first (delivery): Fish S2 `concerned` → `[worried]`; reaction appended after the tone cue
  (`[warm] [chuckling]`); Gemini 3.8 reaction inline `<chuckle>` beside its style; Edge/OpenAI/Eleven
  v2 report `reaction` unrendered; `performed_reactions` per dialect.
- [ ] Tests first (prompt): the rule lists only performed reactions and the published max; a format
  without reactions or a zero max renders the `off` row; every placeholder is produced.
- [ ] Implement; run the radio unit suite → pass.

### Task 4: What the radio could not render is counted

**Files:** `infrastructure/observability/metrics_radio.py` (counter
`radio_delivery_unrendered_total{dimension}`), `domains/radio/production.py` (count per line),
`domains/radio/delivery.py` (docstring now true), Grafana dashboard 31 (one panel), metric docs.

- [ ] Test: producing a segment on an engine without cues counts each unrendered dimension per line;
  metric coverage ratchet passes (panel expression references the metric).

### Task 5: The catalogue states Google's shutdown dates (page updated 2026-10-12, read 2026-10-17)

**Files:** `infrastructure/llm/catalogue/vendor_announcements.py` (6 entries, `READ_ON`), new migration
after `1ed6c591761a` (absolute dates, `IS DISTINCT FROM`, downgrade restores nothing — rule of
`70fd39bf9e8d`), `infrastructure/database/seeds/llm_pricing_seed.sql`, guard
`tests/unit/test_gemini_catalogue_alignment_guard.py` (vendor table = 70fd dates overlaid by the new
migration's).

- Values: `gemini-3.1-flash-tts-preview`, `gemini-2.5-flash-preview-tts`,
  `gemini-2.5-pro-preview-tts`, `gemini-3.1-flash-live-preview`,
  `gemini-2.5-flash-native-audio-preview-12-2025` → 2026-11-17; `gemini-2.5-flash-image` → 2027-03-15.

### Task 6: Documentation

ADR-345 amendment (decision 7: Eleven v2 pause, Gemini 3.8 style, `concerned`, meanings, previews
excluded with reason), ADR-324 decision 45 (reactions), `docs/technical/VOICE.md`,
`docs/technical/RADIO.md`, `CHANGELOG.md` [Unreleased], `.env` comments; `task docs:sync-agents` only
if CLAUDE.md changes; `task lint:docs:preview`.

### Task V: Verification and review

- [ ] Gates: ruff, black, mypy on touched files; `task test:backend:unit:fast`; prompt and metric
  guards; `task lint` (or each sub-task) — results quoted.
- [ ] Vendor checks through LIA's own clients, transcribed with ElevenLabs Scribe v2
  (`tag_audio_events`): Eleven v4 / v4 Turbo / v3 Conversational every spelling; Eleven v2 family
  `<break>` (duration delta, not spoken); Eleven v4 `voice_settings.style` accepted or refused;
  Gemini 3.8 Flash and Flash-Lite style per sentence and events; Fish s2.1-pro-free every spelling.
- [ ] Task 0 corpus re-run on the new block; radio writer measured on discussion, debate and
  bulletin; one segment produced with the Fish free voice on the proof account.
- [ ] Exhaustive cold review: every file of the diff, line by line; spend total reported.
