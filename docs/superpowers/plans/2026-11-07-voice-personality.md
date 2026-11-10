# The personality governs the voice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (the owner chose
> INLINE execution, no subagent). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every voice session of the person (browser Live and Live direct, phone owner call in
both modes) speaks — substance first, then delivery — in the personality configured in LIA, on
every live provider, driven by LIA; a third-party phone call stays cordial.

**Architecture:** one shared personality block with an explicit precedence ladder in the four
owner mandates; an EXPRESSION WIRE per session (`prose` or `cues`, frozen at start) decided by
the provider from what its engine performs; on ElevenLabs agents LIA writes the cue palette,
`ignore_default_personality`, the greeting override and EXACTLY its tool set; transcripts lose
their cues at one stripping function called by every door.

**Tech Stack:** Python 3.14 / FastAPI / pytest; Next.js 16 / vitest; ElevenLabs Agents REST.

**Spec:** `docs/superpowers/specs/2026-11-07-voice-personality-design.md`

## Global Constraints

- Prompt prose only in `src/domains/agents/prompts/v1/` (ADR-284), technical English, generic,
  examples in English; every `{placeholder}` produced by the loading module.
- No model or provider named in a decision, a doc or a test (vendor IDs only as dated proof).
- Never `tool_ids` in an override; vendor PATCHes merged; vendor HTTP outside any transaction.
- JSONB metadata always a NEW dict; logs carry counts and ids, never content.
- Shrink-only ratchets (file size 600 SLOC, CC < 15, coverage, metrics on a panel).
- Six locales for every visible string; FAQ for every user-visible behaviour; a new ADR goes
  in the living maps in six languages.
- Work in the main working tree, unstaged, no commit.

## Review Focus

- An agent whose stored config has NO `realtime_model`, NO `tts` block, or `expressive_mode`
  absent: the wire must read `prose` or `cues` without raising (task 2 test).
- A wake after a portal change of the TTS model: the session keeps its start wire (task 4 test).
- A personality text containing `{` `}` or the vendor's `{{…}}` syntax: rendered literally, the
  phone neutralises it (task 1 test).
- A transcript whose words contain brackets on a `prose` session: never stripped (task 9 test).
- A refused `set_agent_tool_ids` whose cause is NOT a dead id: re-raised, nothing re-created
  (task 7 test).

---

## Lot 1 — the personality governs the voice

### Task 1: the shared personality block (four mandates)

**Files:** create `prompts/v1/voice_personality_block.txt`; modify
`voice_sessions/mandate.py` (`personality_block`), `live/mandate.py`, `live/direct_mandate.py`,
`telephony/mandates.py`, `prompts/v1/live_lines.txt` (drop `personality`/`no_personality`, add
`default_personality`), `telephony_self_call_lines.txt` (drop the two, add `third_party_manner`),
`live_system_prompt.txt` / `live_direct_system_prompt.txt` (« brief and warm » → « brief »),
`telephony_self_call_system_prompt.txt` / `telephony_self_live_system_prompt.txt` (mission line
without « warm »; the « Modulate … » line removed: the block states the authority),
`voice_delegation_block.txt` (restitution keeps LIA's phrasing). Tests:
`tests/unit/domains/voice_sessions/test_mandate.py`, `live/test_mandate.py`,
`telephony/test_mandates.py`.

**Interfaces:** Produces `personality_block(personality: str, *, user_name: str) -> str`
(rendered block; the configured text, else `voice_lines()["default_personality"]`).

- [ ] Tests first: the block holds the configured text verbatim and the ladder (facts/acts above
  the personality; the personality governs words AND delivery; length rules are bounds); the
  default manner when empty; the four rendered mandates contain the SAME block and no « warm »;
  the phone neutralises `{{x}}` inside it; no French, no `{{` in the new file.
- [ ] Implement; run the four test files; green.

### Task 2: the vocabulary — persona cues, sound rows, agent dialects, palettes

**Files:** modify `voice/expressive_cues.py`, `voice/cue_prompt.py`,
`prompts/v1/voice_expressive_cues_lines.txt`; create `voice_sessions/expression.py`. Tests:
`voice/test_expressive_cues.py`, `voice/test_cue_prompt.py`, new
`voice_sessions/test_expression.py`.

**Interfaces:** Produces
- `Cue` + 10 persona members (`sarcastic`, `dismissive`, `cheeky`, `mischievous`, `annoyed`,
  `weary`, `soft`, `slow`, `rushed`, `booming`), `PERSONA_CUES`;
- `ELEVENLABS_AGENT_TAGS: CueDialect` (every cue, vendor spellings `[sarcastically]`,
  `[mischievously]`, `[tired]`, `[softly]`, `[slowly]`, `[whispers]`, pause `…`);
  `dialect_named(name: str) -> CueDialect`;
- `cue_prompt.live_cues_block(dialect: CueDialect, cues: frozenset[Cue]) -> str` and
  `cue_prompt.palette(dialect: CueDialect, cues: frozenset[Cue]) -> list[dict[str, str]]`
  (`{"tag", "description"}`, description = `sound.<cue>`);
- `expression.PERSON_CUES`, `expression.STRANGER_CUES`,
  `expression.agent_dialect(agent: Mapping[str, Any]) -> CueDialect` (realtime model → agent
  tags; v3/v4 TTS with `expressive_mode` not false → agent tags; else `NO_CUES`).

- [ ] Tests first: TTS dialects unchanged (comment path never performs a persona cue); every
  cue has a `sound.*` row with no bracket and no « when »; `meaning/example` complete over the
  comment cues; the live block lists exactly the given cues in the engine's spelling, says the
  personality chooses, carries no numeric budget; the palette mirrors the block; the agent
  dialect for each stored shape (realtime set, v4 turbo, v4 + expressive off, v2, empty config).
- [ ] Implement; run; green.

### Task 3: the provider door and the mandates' expression block

**Files:** `live/providers/protocol.py` (`LiveSetupInputs.cue_dialect: str = "none"`, the
round-trip pair, door `async def expression_dialect(api_key: str, model: str) -> CueDialect` on
`LiveProvider`), `gemini.py` / `openai_live.py` (return `NO_CUES`), `elevenlabs_live.py` (GET
agent → `agent_dialect`), `live/mandate.py` + `direct_mandate.py` + the two live prompt files
(`{expression_block}`), `live/setup_render.py` / `connector_service.setup_inputs` (pass the
dialect). Tests: `live/test_mandate.py`, `live/test_direct_mode.py`, provider tests,
`live/test_service.py` round-trip.

- [ ] Tests first: `prose` renders no block, `cues` renders `live_cues_block(PERSON_CUES)`;
  round-trip keeps `cue_dialect`; each provider's door.
- [ ] Implement; green.

### Task 4: the session start and wake carry the wire

**Files:** `live/service.py` (`start`: ask the door before the render), `live/standby.py`
(`wake`: keep the record's dialect), `live/schemas.py` (`expression: Literal["prose","cues"]` on
the start response), `apps/web/src/lib/live/types.ts`. Tests: `live/test_service.py`,
`live/test_standby.py`.

- [ ] Tests first: a start asks the door once and records the dialect; a wake re-renders with the
  RECORD's dialect even when the door would answer otherwise; the start response states the wire.
- [ ] Implement; green.

### Task 5: ElevenLabs — LIA writes the agent's expression settings and the greeting

**Files:** `live/providers/elevenlabs_live.py` (`sync_agent`: read the stored permissions, grant
`prompt` + `first_message` merged; PATCH `ignore_default_personality: true` and, on a `cues`
session, `tts.suggested_audio_tags = palette(dialect, PERSON_CUES)` — one PATCH, only on
difference; `build_setup`: `first_message: ""`), `core/constants.py` (retire the metadata key
reader). Tests: `live/test_elevenlabs_live_provider.py`.

- [ ] Tests first: nothing patched on a quiet start; the merged permission keeps the person's
  own; the palette written on `cues`, untouched on `prose`; the setup carries the empty greeting.
- [ ] Implement; green.

### Task 6: the phone — personality block, per-dial palette, cordial third party

**Files:** `telephony/service.py` (`_arm_agent_expression(active, kind) -> CueDialect`: GET the
agent, PATCH the palette for the kind when it differs; THIRD_PARTY and VERIFICATION get
`dynamic_variables["personality_profile"] = third_party_manner`), `telephony/mandates.py`
(`MandateInputs.cue_dialect`, `{expression_block}` in both owner prompts), `telephony/client.py`
(`agent_prompt_settings()` → `ignore_default_personality: true`, in the body AND the
fingerprint), `telephony/agent_prompt.py`. Tests: `telephony/test_initiate_call.py`,
`test_mandates.py`, `test_agent_prompt.py`, `test_client.py`.

- [ ] Tests first: a third-party dial never carries the account's personality; SELF gets the
  person palette, others the stranger palette, PATCH only on difference, a refused PATCH never
  blocks a call; the fingerprint drifts once for provisioned agents.
- [ ] Implement; green.

### Task 7 (closes lot 1): surfaces, ADR, maps, FAQ, runtime

- settings `voice_portal` (6 locales); FAQ `voice_mode.q15` + `telephony.q20` (6 locales) and
  the stale `voice_mode.q9` sentence; ADR-373 + ADR_INDEX + maps (history + 6 texts,
  `task docs:maps`); `LIVE_MODE.md`, `TELEPHONY.md`, pointers in ADR-290/300/345.
- Gates: `task lint`, `task test:backend:unit:fast`, `task test:frontend`, Docker dev boot.
- Cold adversarial review of every file of the lot.

## Lot 2 — the agent's tools are LIA's

### Task 8: exact tool ids, scoped sweep, self-heal

**Files:** `live/providers/elevenlabs_live.py`, `telephony/client.py`
(`list_tools() -> list[dict]` paginated, `delete_tool(..., force: bool)`), metrics
`live_agent_tools_swept_total{outcome}` + panel. Tests: provider tests.

- [ ] Tests first: the agent carries exactly the session's set (the person's own detached, never
  deleted); stale LIA copies the agent carried deleted non-forced, 409 kept and counted; the
  other kind's set and a foreign tool never deleted; a refused attach with a dead held id
  re-creates the set and retries once; with no dead id it re-raises.
- [ ] Implement; green; review.

## Lot 3 — no bracket reaches the chat

### Task 9: one stripping function, its doors, its measures

**Files:** `voice/expressive_cues.py` (`strip_cue_brackets(text) -> tuple[str, tuple[str, ...]]`),
shared corpus `tests/unit/domains/voice/cue_strip_corpus.json`, web twin
`apps/web/src/lib/live/cue-strip.ts`; doors `live/service.archive_turn` (count
`live_voice_cues_per_turn`, `live_voice_cues_invented_total`), `voice_sessions/transcript.py`
(`from_vendor_payload`, agent turns), `telephony/payload.extract_transcript_text`;
`session-controller.ts` (captions on a `cues` session); Grafana panels.

- [ ] Tests first (pytest + vitest on the one corpus); doors strip only on `cues` (live) / agent
  turns (phone); counts.
- [ ] Implement; green; review.

## Lot 4 — on the oracle

C16 only if the real sessions (post-deployment, owner's account, budget asked) fail criterion (3).

## Lot 5 — the spoken comment too (owner's go, 2026-11-07, measurement budget 1-2 €)

The chat's spoken comment (`voice_comment` slot, a tool turn's retained records) was left out
of lots 1-3 (ADR-373 §3) while ADR-373's consequences claim « every voice LIA speaks to the
person ». Its frame imposes a tone of its own (informal peer posture and register, cheerful
examples, « −50 % persona » on a failure) and describes its cues by WHEN; persona cues are never
offered to it, though three engine families document them. The answer read aloud and the
briefing's readout are already written in the personality: untouched. The radio: untouched.

### Task 10: measure first (decides the variant and the engines)

**Files:** scratchpad only (`…/scratchpad/lot5/`): the variant texts, the harness run inside
`lia-api-dev`, the raw results.

- [ ] The oracle, declared before any run (ledger): six personalities (normal, friend — the two
  of 2026-10-17 —, cynic, depressed, jarvis, teenager), twelve contexts (four acts of LIA's own,
  one failure, seven news; French and English; one at night), each with its key facts; per
  personality a FORBIDDEN and an EXPECTED cue set (spec § 4.8's, plus friend, jarvis and
  teenager). Metrics: a cue on an own-act or failure context, a forbidden cue, an expected cue
  where one exists, an invented cue, the key facts present; the address (jarvis in French:
  « Monsieur », the familiar « tu »), the teenager's markers, the depressed's exclamations.
- [ ] Three prompts × four model families × the six personalities × the twelve contexts:
  BASELINE (as shipped), A (the frame's tone removed, the precedence ladder, cue meanings kept,
  the personality decides the cues, persona cues listed by their sound), B (A with every cue
  described by its sound alone). Decision rule, written before the run: B if it is not worse
  than A on forbidden and on own-act cues (within 2 points), else A; a variant worse than the
  baseline on own-act cues or on the facts is rejected.
- [ ] The engines: each persona tag synthesised on ElevenLabs v4, v4 Turbo, v3 Conversational
  and Fish s2.1-pro-free, transcribed (a tag read aloud shows in the transcript); Gemini 3.8 Flash
  TTS with each persona STYLE (accepted, and slow/rushed move the duration). An engine joins the
  persona vocabulary only on that evidence.

### Task 11: the comment frame and its cues (TDD)

**Files:** `prompts/v1/voice_comment_prompt.txt`, `prompts/v1/voice_expressive_cues_lines.txt`,
`voice/cue_prompt.py` (`expressive_cues_block`: the persona kind, the personality line, the
measured descriptions), `voice/expressive_cues.py` (persona spellings on the engines Task 10
admitted; `_bracketed` stays delivery and sounds, so drama-3 is untouched),
`agents/services/streaming/voice_coordinator.py` (a personality that failed to load reaches the
comment as the default one, as it reaches the written answer); tests `test_cue_prompt.py`,
`test_expressive_cues.py`, the coordinator's.

- [ ] Tests first: the block lists the persona cues an engine performs, described as Task 10
  decided, under a personality line; an engine Task 10 refused performs none; `AuthoredCues`
  spells a persona cue the engine's way; the radio's renderings are unchanged; the default
  personality reaches the comment.
- [ ] Implement; green; the real `stream_voice_comment` on the dev slot end to end (Fish free).

### Task 12 (closes lot 5): documents and gates

ADR-373 amendment (the comment writer; the consequences sentence made true), ADR-345 amendment
pointer, `docs/technical/VOICE_MODE.md`, the FAQ entry in six languages, the ADR-373 map entry,
CLAUDE.md line (budget) + `task docs:sync-agents`; `task lint`, unit fast, the voice suites, a
cold adversarial review, the ledger.
