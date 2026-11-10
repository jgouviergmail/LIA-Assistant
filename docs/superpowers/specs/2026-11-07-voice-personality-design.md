# The personality governs the voice — design (2026-11-07)

Status: design, awaiting the owner's approval. Nothing of it is built.

## 1. Intent

Every spoken surface of LIA — the browser live session (delegated and direct), the
owner's phone call (direct and Live) — must speak in the personality the person
configured for LIA, on every live provider (Gemini Live, GPT-Live, ElevenLabs
Agents), and LIA must drive that itself: what a provider's portal holds must never
be what decides how LIA sounds.

« Speak in the personality » means three things, in this order of weight: the
SUBSTANCE — what the voice chooses to say of its own (how it addresses the person,
its words and figures, what it comments on, its jokes and opinions, how it
announces a lookup, how it reports a failure, how it says goodbye); the FORMULATION
of what it restitutes — the same facts, said as that personality would say them;
and the SOUND — the delivery, and the cues on an engine that performs them. The
intonation is the form; the sentences and their content are the substance, and the
substance comes first (owner, 2026-11-07).

One exception, decided by the owner: a phone call to a THIRD PARTY (a restaurant, a
garage) stays cordial whatever the personality. The personality is for the person;
a stranger on the line gets LIA's plain courtesy.

### Why now

Measured on 2026-11-07 (production, ElevenLabs direct session, 3 min): the prompt LIA
sent carried the configured « cynique » personality, and the voice was cheerful from
the first word to the last. Three causes, in order of weight:

1. The agent's **suggested audio tags on the ElevenLabs portal** prescribed the mood
   (« Avec enthousiasme — au démarrage et pendant la discussion », « Chaleureusement
   en fin », « Sérieusement — avec une entreprise »), and the vendor's model applied
   them to the letter: `[Avec enthousiasme]` opened almost every answer. No tag of
   irony existed. These tags are not overridable per conversation.
2. LIA's **voice mandates fight the personality**: « keep small talk brief and
   warm » (both live prompts), a mission line « natural, warm, efficient » (phone),
   a `PERSONALITY:` label with no authority — the chat prompt says « must govern »,
   the voice prompts say nothing — and an `<InnerVoice>` block that prescribes a
   neutral delivery right after it.
3. The **agent carried 163 tools, 101 of them unknown to LIA** (old sets of LIA's own
   tools, 60 names in double): `sync_agent` keeps every id it does not recognise as
   « the person's own », for ever. ~396 000 input tokens were billed for three
   minutes; the prompt itself is ~1 600 tokens.

Facts: `apps/api/src/domains/live/providers/elevenlabs_live.py:393-398` (the override
carries the prompt alone), `:476-478` (unknown ids kept), `live_system_prompt.txt:9`,
`live_direct_system_prompt.txt:14`, `live_lines.txt:16-17`,
`telephony_self_live_system_prompt.txt:3`, `telephony/service.py:508-523` (the
third-party agent reads `{{personality_profile}}` per call).

## 2. Goals, non-goals, anti-goals

Goals

- G1. In every voice session of the person, the personality decides what is said and
  HOW it is said, on every provider and model, from LIA's prompt alone.
- G2. Where the provider's engine can perform delivery cues (ElevenLabs audio tags),
  LIA writes the cue palette itself and tells the voice how its personality uses
  them; where the engine cannot, the mandate says the delivery in words.
- G3. The ElevenLabs agent's tool list is LIA's referential: at every session start
  the agent carries exactly LIA's set for that session, nothing else; LIA's stale
  sets are removed from the workspace.
- G4. A third-party phone call speaks LIA's fixed cordial manner, never the
  personality.
- G5. A cue is never shown as words: transcripts, captions, archived turns and the
  direct session's relayed message carry no bracketed cue.

Non-goals

- No switch « personality off for the voice »: the owner asked that every session
  follow the personality; a switch would be a second authority.
- No per-personality cue palette stored on `personalities`: the palette is LIA's one
  vocabulary; the personality's own text decides the use (see § 4.3; revisit only
  on a measured failure).
- The voice, the language, the model, the turn-taking and the audio formats of an
  ElevenLabs agent stay the portal's (owner rule 2026-09-16, narrowed today to
  those). LIA writes the prompt, the expression palette, `ignore_default_personality`
  and the tools.

Anti-goals (a failure even if it « works »)

- The voice becomes a caricature: tags on every sentence, laughter at bad news. The
  cue budget and the ADR-345 rule « a cue colours the news, never the outcome of
  LIA's own act » apply to the live voice too.
- A tag read aloud: a cue sent to an engine that does not perform it, or a cue in
  the engine's syntax written for a model that produces audio natively.
- A third-party callee hearing sarcasm.
- Deleting a workspace tool another agent (another LIA instance on the same key)
  still references.

## 3. Constraints (measured or documented, dated)

- ElevenLabs Agents, conversation override: the per-conversation
  `conversation_config_override` carries `agent.prompt.{prompt, llm, tool_ids,
  tool_ids_strict, native_mcp_server_ids, knowledge_base}` and
  `tts.{model_id, voice_id, supported_voices, stability, speed, similarity_boost,
  pronunciation_dictionary_locators}` — NOT `suggested_audio_tags`, NOT
  `expressive_mode`, NOT `ignore_default_personality` (SDK `elevenlabs-js` `main`,
  read 2026-11-07). Those three are AGENT settings: a PATCH of the agent, merged with
  the stored config (measured 2026-09-16).
- `tool_ids` inside an override is refused on a live call (« Tool IDs not attached
  to this agent », measured 2026-09-16): tools are attached to the agent.
- Realtime voice mode (`conversation_config.realtime_model` =
  `eleven_realtime_v1_mini` | `eleven_realtime_v1_max`): the vendor manages and
  IGNORES the stored `agent.prompt.llm`, reasoning settings, `tts.model_id`,
  `tts.expressive_mode`, `asr.provider`; the system prompt, the voice, the tools and
  the temperature apply (vendor docs, read 2026-11-07). Measured the same day on
  the owner's agent (Realtime max): the suggested audio tags WERE applied and the
  bill names `eleven_realtime_v1_max`.
- Audio tags are « bracketed, natural-language cues »; the vendor's documented
  examples (blog last updated 2026-10-15) include `[sarcastically]`,
  `[dismissive]`, `[cheeky]`, `[annoyed]`, `[tired]`, `[softly]`, `[slowly]`,
  `[whispers]`, `[laughs]`, `[chuckles]`, `[sighs]`, `[excited]`, `[surprised]`.
  Each tag colours roughly the next 4-5 words. Eleven v4 reads no SSML.
- `suggested_audio_tags` = `[{tag, description}]`; the vendor injects an
  « expressive audio tags prompt » from it; measured 2026-11-07: the model follows
  the DESCRIPTION as a trigger rule.
- Gemini Live (`gemini-3.8-live`, Extended Thinking): native audio; no tag or SSML
  documented for the output; `enable_affective_dialog` is removed on 3.8 and was
  measured as a false positive on LIA's path (2026-09-19). The system instruction is
  the lever (the vendor's own quickstart steers tone there).
- GPT-Live (`gpt-realtime` family): native audio; the vendor's prompting guide
  structures the prompt with a « Personality & Tone » section; no output tag syntax.
- LIA's existing expression system (ADR-345): ONE canonical vocabulary
  (`domains/voice/expressive_cues.py::Cue`, 14 cues), a dialect per engine
  (`cue_dialect(provider, model)`: ElevenLabs v3/v4 → bracketed tags, v2 → SSML
  pause only, Fish, Gemini TTS), a prompt block (`domains/voice/cue_prompt.py`,
  `voice_expressive_cues_lines.txt`) rendered only when the engine performs a cue
  and the budget is above zero, and the rule « a cue colours the news, never the
  outcome of LIA's own act » (measured on four model families, 2026-10-17).
- One personality text per account (`PersonalityService.get_prompt_instruction_for_user`),
  read by the chat, the live session, the phone, the briefing, the reminders. The
  text is written for the chat (« Tes réponses sont concises », « Tu tutoies »): it
  applies to the voice as it is; the mandate frames it for speech.
- FOURTEEN personalities are seeded (`infrastructure/database/seeds/personalities_seed.sql`):
  cynic, normal, depressed, enthusiastic, friend, philosopher, influencer,
  professor, rasta, teenager, jarvis, haipai, trump, antagonist — and an
  administrator may add others. The « cynique » of the measured session is ONE of
  them: nothing in the design, the palette or the proof is written for it. The
  registers the catalogue asks a voice for: irony and contempt (cynic,
  antagonist), weariness and reluctance (depressed, teenager), an unhurried calm
  (rasta, philosopher), exuberance (enthusiastic, influencer), grandiloquence
  (trump), haste (haipai), flegm and courtesy (jarvis), warmth (friend, professor),
  and a plain register that must not turn theatrical (normal).
- The four voice mandates render their personality line from ONE helper
  (`voice_sessions/mandate.py::personality_block`) and two lines files
  (`live_lines.txt`, `telephony_self_call_lines.txt`). The phone neutralises the
  vendor's `{{…}}` syntax inside the text.
- The ElevenLabs phone agent is CREATED by LIA (`telephony/agent_prompt.py`,
  `client._agent_config_body`), fingerprinted, lazily re-synced before a dial; its
  third-party prompt is baked and reads `{{personality_profile}}` as a dynamic
  variable; the phone's `attach_live_tools` already sets EXACTLY the ids LIA
  wants (the live provider is the one that keeps strangers).
- The direct session's assistant turns are KEPT (`append_turns`) and become the
  person's relayed message at the end (ADR-301); the browser archives delegated
  turns one by one; captions are pushed per transcript fragment
  (`session-controller.ts::onTranscript`).
- Guards that will read the change: `test_prompt_placeholders_are_produced.py`
  (every placeholder produced), the setup-inputs round-trip equality test, the
  lines-file completeness guards of ADR-345, `test_live_tools.py`,
  `test_elevenlabs_live_provider.py`, `test_mandates.py` (phone), `test_mandate.py`
  (live and voice_sessions). New prose goes in versioned prompt files only (ADR-284).

## 4. The design

### 4.1 The personality has authority, in every voice mandate

One shared block replaces the two `personality` / `no_personality` lines: a
`voice_personality_block.txt` rendered by `voice_sessions/mandate.py::personality_block`
for the four mandates (browser delegated, browser direct, phone direct, phone Live),
with ONE wording, in technical English:

- the configured instruction, framed as WHO the voice is — a text written for the
  chat, so the block says how it reads in speech: its manner governs what is said
  and how it is said; its length rules (« concise ») mean short turns, never a flat
  delivery;
- it governs every sentence AND the delivery, in one explicit ladder the block
  states: (1) the FRAME holds the facts and the acts — what a result says, a date,
  what was done or not, what the voice may not do (act, invent, read an
  identifier), and the safety rules; a personality never changes a fact nor claims
  an act, whatever its text says (a persona that « never apologises » or « decides
  what is true » reports a failure as a failure, in its manner); (2) the
  PERSONALITY governs everything else that is said: the address (tutoiement,
  « Monsieur », a nickname), the vocabulary and the figures (slang, jargon, the
  words its text names), what it comments on and how, its jokes, its opinions and
  digressions, how it announces a lookup and reports its outcome, the formulation
  of every fact it reads back, the goodbye; (3) the personality decides the
  DELIVERY (tone, rhythm, what is said first, what is left unsaid); (4) the inner
  state nuances it; (5) the cues, where an engine performs them, are the form of
  (3). The frame's length rules (short turns, one question at a time) are BOUNDS on
  a turn so the person can speak, never a style: a personality that speaks slowly
  or at length does so inside the bound;
- the inner state block (`<InnerVoice>`) only nuances it — the psyche block's own
  wording stays, the personality block says the order of precedence;
- restitution of a delegated answer keeps LIA's own phrasing where it already
  carries the personality (the answer was written by the chat, in the personality),
  and shortens without flattening; the delivery note a result may carry (ADR-253,
  `tone_note_*`) is NOT a competing authority — the chat wrote that answer in this
  same personality, so the note says how the personality said it: the voice keeps
  following it, as a nuance of the restitution;
- the precedence is over the FIXED indications of tone of the frame (the mandate's
  own rules), which the frames no longer carry once § 4.1 is applied;
- without a configured personality: LIA's default manner (the current line).

Removed from the frames: « keep small talk brief and warm » (both live prompts),
« natural, warm, efficient » (both phone owner prompts); « brief » stays where it was
a length rule. The phone's « Modulate warmth, humour and expressiveness according to
`<personality_profile>` » line is replaced by the shared block's authority sentence
(one wording, four frames).

### 4.2 Expression wire: declared per provider and per session

A voice session declares HOW expression travels — `expression: "cues" | "prose"` —
on `LiveSetupInputs` (persisted on the record, read by the wake, covered by the
round-trip test):

- `prose`: Gemini Live, GPT-Live, and an ElevenLabs agent whose engine performs no
  delivery cue. The mandate says the delivery in words (the personality block
  alone); no bracket is ever asked for.
- `cues`: an ElevenLabs agent whose speaking engine performs audio tags. The mandate
  adds a cue block (§ 4.3) and the agent receives LIA's palette (§ 4.4).

How ElevenLabs decides it, from the agent read at session start (`get_agent`, already
called by `sync_agent`; the read moves before the render so start and wake render
from the same agent): the speaking model is `conversation_config.realtime_model`
when set, else `tts.model_id`; `cue_dialect("elevenlabs", speaking_model)` names the
dialect — a new rule `("elevenlabs", "eleven_realtime_v1", ELEVENLABS_AUDIO_TAGS)`
is added with its measurement date; `tts.expressive_mode == false` on a non-Realtime
agent forces `prose` (the person switched it off; LIA never writes a cue the engine
is told to ignore). The provider protocol gains one async door for this
(`session_wire(api_key, model) -> LiveSessionWire`), with a static default for the
providers that need no read; nothing branches on a provider's name.

The phone (ElevenLabs agent LIA created) applies the same reading at dial time, from
the same helper.

The wire is decided at the START and frozen on the record for the session's life,
exactly as `audio_transport` is: the wake re-reads the agent for the tools and the
palette (§ 4.4, § 4.5) but keeps the start's wire, so the cue spellings the browser
received at start stay true until the session ends; a TTS model changed on the
portal mid-session is picked up by the next session.

### 4.3 The cue block of the live voice

The live voice writes its cues ITSELF, directly in the words the engine performs
(there is no renderer between a conversational model and its TTS, unlike the comment
path where `AuthoredCues` spells LIA's words per engine). So the block lists the
cues in the ENGINE's spelling (`dialect.render(cue)`), each with what it SOUNDS
like — a new `sound.<cue>` row per cue in `voice_expressive_cues_lines.txt`, beside
the comment writer's `meaning.<cue>` row (sound AND when), which stays as measured
on 2026-10-17. The live voice is told the sound alone because the WHEN is the
personality's business; the same `sound.*` rows are the vendor palette's
descriptions (§ 4.4), so a description can never read as a trigger again. A guard
holds `sound.*` complete over the vocabulary, as the existing guards hold
`meaning.*` and `example.*`.

The vocabulary is extended with PERSONA cues, a third kind beside the delivery and
event cues, offered to the live voice and NOT to the spoken-comment writer (whose
measured behaviour of 2026-10-17 stays untouched). They are chosen to cover every
register of the catalogue (§ 3), not one personality: `sarcastic`
(→ `[sarcastically]`), `dismissive`, `cheeky`, `mischievous` (→ `[mischievously]`),
`annoyed`, `weary` (→ `[tired]`), `soft` (→ `[softly]`), `slow` (→ `[slowly]`),
`rushed`, `booming`. With the delivery cues already there (calm, warm, cheerful,
excited, serious, concerned, curious, surprised, empathetic, whispering) and the
sounds (laughs, chuckles, sighs), every register of § 3 has its words: irony and
contempt (sarcastically, dismissive, cheeky, mischievously), weariness (tired,
slowly, sighs, annoyed), the unhurried calm (calm, slowly, softly), exuberance
(excited, cheerful, laughs), grandiloquence (booming, excited, dismissive), haste
(rushed), flegm (calm, serious, cheeky), warmth (warm, empathetic, chuckles). Every
spelling is a tag the vendor documents (blog « v3 audio tags », last updated
2026-10-15; help centre); Fish S2 and Fish drama spell them by the existing
`_bracketed()` rule, Fish S1 (fixed set) drops them, Gemini TTS gets no style for
them (its writer never sees them). Each new cue gets its `sound.*`, `meaning.*` and
`example.*` rows (the file's guards hold the set complete). A personality the
catalogue gains later is served by the same palette; a register it would need and
the palette lacks is a new cue, added with its documented spelling.

The block's rules, from the existing ones: at most one delivery or persona cue per
sentence, at its start, and most sentences none; a sound where it happens; « a cue
colours the news, never the outcome of your own act » (an error, nothing found, a
confirmation are said plainly); never invent a cue, never translate one; the
personality decides WHICH cues it uses and which it never does — the block says so
explicitly, so a personality never picks a cue it would not use because the list
offers it (a cynic no `[excited]`, an enthusiast no `[tired]`, a plain assistant
almost none). No
numeric budget is published: nothing in LIA can enforce one on a model that speaks
straight to its engine, and a prompt states only what the code enforces (ADR-284).
What the code CAN do is measure: the stripping door (§ 4.7) counts the cues of each
assistant turn (`live_voice_cues_per_turn`, a histogram with a Grafana panel), so an
abuse is visible rather than guessed.

### 4.4 ElevenLabs: LIA writes the agent's palette and its default-persona switch

In `sync_agent` (session start and wake), idempotent by comparison with the agent
read:

- `conversation_config.tts.suggested_audio_tags` := LIA's palette for the dialect:
  one `{tag, description}` per cue the engine performs among delivery, persona and
  event cues, `tag` = the engine's spelling without brackets, `description` =
  `sound.<cue>` — what the tag SOUNDS like, never when to use it (the measured
  defect: a description written as a trigger is obeyed as one). The person's own
  palette on the agent is replaced; the settings screen says so (§ 4.7).
- `conversation_config_override.agent.first_message` := `""` on every start and
  wake, under the `first_message` override permission granted with the prompt's:
  the portal's canned greeting is the one sentence the personality could never
  reach, and the other providers let the person speak first. To be MEASURED on a
  throwaway agent (an empty override may be read as « not provided » and fall back
  to the stored greeting): if it is, LIA overrides it with its own short greeting
  from the phone's six-language rows (`get_self_greeting`) and the ADR says that
  one sentence is LIA's, not the personality's.
- `conversation_config.agent.prompt.ignore_default_personality` := `true`: the
  vendor's « helpful » default lines would fight the personality LIA sends.

Both are PATCHed only when the agent's stored value differs (one GET already paid,
no write on a quiet start). On a Realtime agent the vendor ignores
`tts.expressive_mode`; the palette was measured applied — LIA writes it the same way.

The phone agent LIA creates serves TWO audiences on one agent-level palette: the
person (SELF calls) and strangers (THIRD_PARTY calls), and the vendor injects the
palette on every conversation of the agent. So the phone writes its palette PER
DIAL, by kind, in the same pass that attaches the tools (`_arm_agent_tools`, one
PATCH when the agent's stored value differs; one active call per account, so no
flip-flop): the full palette of the speaking engine before a SELF call; the CORDIAL
palette — delivery and event cues without the persona cues, without `excited`,
`whispering` and `laughs` — before a THIRD_PARTY or VERIFICATION call. A stranger is
therefore never OFFERED `[sarcastically]`, whatever the prompt says.
`ignore_default_personality := true` goes in `_agent_config_body` (covered by the
config fingerprint, so provisioned agents re-sync lazily before the next dial).

### 4.5 ElevenLabs: the agent's tools are LIA's referential

`sync_agent` sets `agent.prompt.tool_ids` to EXACTLY LIA's set for the session's
kind (direct or delegation), as the phone already does. Consequences, stated:

- A tool the person attached to that agent on the portal is DETACHED at LIA's next
  session start (never deleted: a switch removes the capability, never the record).
  The settings screen says the agent's tools are LIA's.
- LIA's stale sets are removed from the workspace — scoped to what THIS AGENT
  carried, never a workspace-wide scan: every id the agent carried outside LIA's
  current sets whose workspace tool is a CLIENT tool named as one of LIA's live
  tools is, once detached, deleted WITHOUT force — the vendor answers 409 « still in
  use » for a tool another agent still references, and that one is kept and
  counted; 204 frees an orphan. A workspace scan by name was considered and
  refused: another LIA instance on the same key always holds one kind's set
  DETACHED, and a non-forced delete would free it (204) and break that instance's
  next start.
- `sync_agent` heals a set the workspace lost (a portal deletion, a sibling's
  cleanup, a hand cleanup): on a refused `set_agent_tool_ids`, it lists the
  workspace tools once, forgets from `held` every id that no longer exists,
  re-creates the missing set and retries once — then raises. Today a dead id is a
  session refused for ever.
- One-time, measured cleanup of the 101 orphans of the owner's agent is the first
  run of that very sweep (they are attached to that agent), read in the logs
  (counts only).

### 4.6 Third-party calls stay cordial

`dynamic_variables.personality_profile` of a THIRD_PARTY dial becomes LIA's fixed
cordial manner — a `third_party_manner` row of the phone's lines file (technical
English, the vendor's model reads it) — never the account's personality. SELF calls
(direct and Live) keep the personality through the override; VERIFICATION carries
none. A guard test holds the three kinds to that table. The baked prompt's
`<personality_profile>` slot and its heuristic stay (no agent re-sync for this).

### 4.7 Surfaces

- Transcripts: ONE stripping function (`expressive_cues.strip_transcript_cues`).
  On a `cues` session the assistant's text is the vendor's transcript of what its
  model wrote, and the vendor documents that audio tags stay in it unspoken — and
  that the model may use tags beyond the suggested ones. So the function removes
  EVERY bounded bracketed span of the assistant's text (ADR-326 bound), not only
  LIA's spellings, and counts the ones outside LIA's palette
  (`live_voice_cues_invented_total`): the count says whether the model keeps to the
  palette. On a `prose` session nothing is removed: a bracket there is words. Three
  doors call it: the live `archive_turn` (both modes, so the archive AND the direct
  session's relayed message are clean); the phone's transcript ingestion where the
  vendor transcript becomes a `VoiceTranscript` (`voice_sessions/transcript.py`,
  always ElevenLabs, always `cues`), which serves the Live owner call's archive, the
  direct owner call's relay and the third-party debrief; and the browser's
  `onTranscript`, before captions, the turn buffer and the archive request, told by
  the session start response whether the session is `cues` and which spellings are
  LIA's. The live door observes `live_voice_cues_per_turn`.
- Settings (`LiveConnectorForm`, `settings.live_mode.voice_portal` and its
  neighbours, six languages): « the voice, the language and the turn-taking are the
  agent's, on the portal; LIA writes its prompt, its expression palette and its
  tools on the agent ». The FAQ entry of the live mode and of the phone says the
  personality applies to the voice, and that a call to a third party stays cordial.
- Docs: a new ADR-373 « The personality governs the voice » (decision, measurements,
  the narrowed portal rule, the tool referential), its entry in the living maps in
  six languages (`task docs:maps`), `LIVE_MODE.md`, `TELEPHONY.md`, ADR-300 and
  ADR-290 amended by pointer, ADR-345 amended (persona cues, the live voice writes
  in the engine's spelling, the Realtime rule).
- Observability: `live_cue_palette_synced_total{provider}` and
  `live_agent_tools_swept_total{outcome}` (freed / in_use / refused), each on a
  Grafana panel (the metric ratchet refuses an orphan metric).

### 4.8 Proof

- Unit: the four mandates render the authority block and no « warm »; the cue block
  appears only on a `cues` session and lists only performed cues in the engine's
  spelling; `prose` on Gemini, GPT-Live, a v2 agent, an `expressive_mode=false`
  agent; `cues` on a v4 and on a Realtime agent; the palette body; the
  `ignore_default_personality` PATCH only on difference; `tool_ids` exactly LIA's
  set; the sweep's three outcomes on a fake client (409 kept); the third-party
  dynamic variable; stripping on both sides (pytest + vitest on one corpus, as the
  voice projection already does); the round-trip of the new setup field.
- Integration (vendor, throwaway agent on the owner's key, read-write — asked
  first): a PATCH of `suggested_audio_tags` + `ignore_default_personality` on a
  Realtime agent answers 200 and reads back; a non-forced DELETE of a tool in use
  answers 409 and of a detached one 204; an empty `first_message` override on a real
  conversation either silences the stored greeting or falls back to it (the fork of
  § 4.4).
- Real sessions (the only oracle for the voice itself): the six-turn script under
  the four personalities on ElevenLabs direct (four short sessions, ~2 min each),
  one ElevenLabs delegated session, one Gemini session, one GPT-Live session if a
  key exists, one phone owner call, one third-party call — read afterwards with
  the 2026-11-07 method (the prompt the vendor received, the transcript's tags, the
  bill). ≈ 3 300 ElevenLabs credits per 3-minute session on the owner's account:
  about eight short sessions in all.
- The acceptance oracle, stated before the sessions run and RELATIVE to the
  personality under test: ONE script of six turns (a greeting, « what is on my
  agenda today », the weather, a request for a joke, a request that fails, a
  goodbye) replayed under four contrasting personalities — cynic, enthusiastic,
  depressed, normal — each with an EXPECTED register and a FORBIDDEN register
  declared in the script from the vocabulary (cynic: sarcastically, dismissive,
  cheeky, mischievously, chuckles expected; excited, cheerful forbidden at a turn's
  opening — enthusiastic: excited, cheerful, laughs expected; tired, slowly,
  dismissive, sarcastically forbidden — depressed: tired, slowly, softly, sighs
  expected; excited, cheerful, laughs forbidden — normal: no persona cue, at most
  one cue in the six turns). Criteria: (1) no turn opens with a forbidden cue;
  (2) an expected cue appears at least once where the personality has any, and
  none on the failed request's report; (3) the SUBSTANCE carries the personality
  on every one of the six turns, as its text describes it — the address, the
  vocabulary, the comments, the way the agenda and the weather are read back, the
  way the failure is reported, the joke, the goodbye — judged on the transcript by
  the owner, the final judge; (4) the FACTS are the same under the four
  personalities (the agenda item and its hour, the weather figures, « it failed »)
  while the sentences differ — the one criterion that separates a personality from
  an invention; (5) the third-party call carries no persona cue and no register of
  the account's personality; (6) no bracket reaches the chat. A personality that
  passes everything but (3) means the prompt authority is not enough for it: the
  fallback is C16, for the whole catalogue; one that fails (4) is a frame defect
  (the facts yielded to the persona), fixed in the ladder's wording before any
  other step.
- The honest limit: `prose` on Gemini Live and GPT-Live rests on the vendors'
  documentation (a system instruction steers tone), never on a measurement of
  LIA's; the Gemini session above is that measurement, and GPT-Live stays
  unmeasured without a key.

## 5. Left to the builder

- The exact wording of the shared personality block, the cue block frame rows and
  the third-party manner line (technical English, ADR-284 files).
- The shape of `LiveSessionWire` and where the ElevenLabs agent read is shared
  between the render and `sync_agent` without a second GET.
- The sweep's trigger condition detail and its logging (counts, never names).
- The vitest/pytest corpus for cue stripping.
- The Grafana panels' placement.

## 6. Calls made here (the owner may overturn any)

- C1. One universal palette + the personality's text decides the use, rather than
  a palette column per personality (less to declare, no admin UI; revisited on a
  measured failure).
- C2. Persona cues are a third kind, hidden from the spoken-comment writer.
- C2 (revised, lot 5). The spoken-comment writer is offered the persona cues on the engines
  measured to perform them (none read aloud): ElevenLabs v3/v4, Fish Audio S2, Gemini 3.8 as a
  style; the radio writes none.
- C3. The live voice writes cues in the engine's spelling (no renderer in between).
- C4. `expressive_mode=false` on a non-Realtime agent means `prose`.
- C5. Another person's agent is treated like the owner's: palette,
  `ignore_default_personality` and tools are LIA's at every session; the screen says so.
- C6. Workspace orphans are deleted non-forced by NAME ∈ LIA's live tool names;
  a 409 keeps the tool.
- C7. The third-party manner is one fixed English line, not a translated text (the
  model reads it; the callee hears the call's language).
- C8. A new ADR-373 rather than amendments alone, because the rule crosses three
  surfaces and three providers.
- C9. The phone writes its palette per dial by kind (full for the person, cordial
  for a stranger) on its one agent, rather than a second agent for the owner's
  calls (two provisionings, two webhooks' `agent_id`, for one palette).
- C10. The sweep is scoped to the ids the agent carried; no workspace scan by name
  (it would delete a sibling instance's detached set). `sync_agent` heals a lost set.
- C11. `sound.<cue>` rows beside `meaning.<cue>`: the live voice and the vendor
  palette read the sound alone; the comment writer keeps its measured rows.
- C12. No numeric cue budget in the live block (nothing enforces it); cues per turn
  are measured at the stripping door instead.
- C13. One stripping function on the ElevenLabs spellings of the whole vocabulary,
  three doors (live archive, phone transcript ingestion, browser); no dialect column
  on `phone_calls`.
- C14. The browser agent's canned greeting is silenced by an empty `first_message`
  override (the person speaks first, as on the other providers), measured; the
  fallback is LIA's own six-language greeting, named as outside the personality.
- C15. The delivery note of a delegated result stays, as a nuance: it was produced
  in the same personality. The wire is frozen at start.
- C16. The fallback if the universal palette fails the oracle for any personality:
  an allowed-cue list DECLARED per personality (a column on `personalities`, seeded
  for the fourteen, required of any personality an administrator adds, editable in
  the admin form, held complete by a boot assert), read by the palette and the
  block — declared, never inferred from the OCEAN traits.
- C17. Nothing is written for one personality: the palette covers the catalogue's
  registers (§ 4.3), the oracle is relative to the personality under test and runs
  on four contrasting ones (§ 4.8), the mandate names no personality.
- C18. The substance before the form: the block's ladder puts the facts and the
  acts above the personality, the personality above the delivery, the delivery
  above the cues; the oracle judges the sentences of every turn and holds the facts
  equal across personalities (§ 4.8).
- C13 (revised). Stripping removes every bounded bracket of a `cues` session's
  assistant text, not only LIA's spellings: the vendor's model may write tags
  beyond the palette, and a tag left visible is the defect G5 names. The ones
  outside the palette are counted.

## 7. Order of delivery

Four lots, each shipped with its tests and its documentation; the first one alone
changes what the owner heard on 2026-11-07.

1. **The personality governs the voice**: the shared authority block in the four
   mandates (§ 4.1), the expression wire (§ 4.2), the cue block and the persona
   cues (§ 4.3), the ElevenLabs palette, `ignore_default_personality` and the empty
   greeting (§ 4.4), the phone's per-dial palette and the third-party cordial line
   (§ 4.6), ADR-373 and the maps, the settings text and the FAQ (§ 4.7), the
   throwaway-agent measurements. Then the real sessions against the oracle.
2. **The agent's tools are LIA's**: exact `tool_ids`, the scoped sweep, the
   self-heal, the one-time cleanup read in the logs (§ 4.5).
3. **No bracket reaches the chat**: the stripping function and its three doors, the
   browser's share, the two metrics and their panels (§ 4.7).
4. **Revisit on the oracle**: C16 only if lot 1's sessions fail criterion (3).
5. **The spoken comment too** (owner's question and go, 2026-11-07, after lots 1-3; budget 1-2 €):
   the chat's spoken comment of a tool turn takes the same order (facts, acts and the target
   language first, then the personality, then the sound), loses its frame's own tone, receives the
   default personality when the person's fails to load, and is offered the persona cues where an
   engine performs them — every choice measured first (three prompts, four model families, six
   personalities, twelve contexts; the persona tags transcribed on every engine). ADR-373 § 8.
