# ADR-373 — The personality governs the voice

**Status**: Accepted, 2026-11-07.
**Date**: 2026-11-07

**Amends**:
[ADR-299](ADR-299-Live-Voice-Mode-Two-Intelligences-One-Seam.md) and
[ADR-301](ADR-301-Voice-Sessions-One-Policy-Per-Mode.md) — the voice mandates carry one personality
block with an order of precedence, and no tone of their own.
[ADR-300](ADR-300-A-Second-Live-Provider-One-Seam-Two-Wires.md) — on an ElevenLabs agent, LIA writes
its expression palette, drops the vendor's default persona, empties the portal's greeting and holds
the agent's tool list; « what the agent sounds like is the portal's » narrows to the voice, the
language and the turn-taking.
[ADR-290](ADR-290-Phone-As-A-Channel-Owner-Calls.md) — a call to a third party hears LIA's cordial
manner, never the person's personality.
[ADR-345](ADR-345-Fish-Audio-Served-Whole-One-Door-One-Allowance-Cues-Each-Engine-Reads.md) — the
cue vocabulary gains persona cues, offered to a live voice and, on the engines measured to perform
them, to the spoken comment's writer, whose frame takes the same order of precedence (§ 8).

## Context

On 2026-11-07 the owner ran a production Live direct session on an ElevenLabs agent with the
« cynique » personality configured, and heard a cheerful helpful assistant. Read on the vendor's
own record of that conversation:

- the prompt LIA sent carried the personality (`PERSONALITY: Tu es un esprit rebelle…`), and the
  vendor's default persona was already off on that agent;
- the agent ran a **realtime** model, which manages the speech model and the expressive mode
  itself and ignores the stored LLM;
- the agent's **suggested audio tags**, written on the portal in French, prescribed a mood:
  « Avec enthousiasme — au démarrage de la discussion et pendant la discussion », « Chaleureusement —
  en fin de conversation », « Sérieusement — avec une entreprise ». The model applied them to the
  letter: `[Avec enthousiasme]` opened nearly every answer, `[Sérieusement]` fell before every
  business name. No tag could carry irony. These tags cannot be overridden per conversation;
- LIA's own mandates fought the personality too: « keep small talk brief and **warm** » in both
  browser prompts, a phone mission « natural, **warm**, efficient », « acknowledge **kindly** », a
  bare `PERSONALITY:` label while the chat prompt says the personality « must govern phrasing and
  conversational demeanor »;
- the agent carried 163 tools, 101 of them unknown to LIA (earlier copies of its own sets, 60 names
  twice): `sync_agent` kept every id it did not recognise as « the person's own ». About 396 000
  input tokens were billed for three minutes, where LIA's prompt weighs about 1 600.

The owner's decisions the same day: every voice of the person — Live, Live direct, the phone, on
every provider — speaks in the personality configured in LIA, driven by LIA; LIA writes the
expression tags itself, compatible with each provider; the agent's tools come from LIA at every
session, the portal is never a referential; the one exception is a call to a third party, which
stays cordial. And the substance before the form: the personality is first in what is said — the
sentences, their wording, their content — then in how it sounds.

## Decision

### 1. One personality block, with an order of precedence

`voice_sessions/mandate.personality_block(personality, user_name=…)` renders ONE block
(`voice_personality_block.txt`) for the four mandates a person hears LIA through — the browser's
delegated and direct, the phone's direct and Live. It holds the configured text verbatim and the
order it applies in: facts and acts stay exactly as they are; the personality governs everything
else the voice says (the address, the words, the comments, the jokes, how a lookup is announced and
reported, how each fact is read back, the goodbye); it governs the delivery too; an inner state only
shades it; nothing else suggesting a tone outranks it; the frame's length rules are bounds, never a
style. Without a configured text, LIA's default manner stands in. The frames lose every tone of
their own, and their examples say they show what to do, never how to sound. A delegated answer is
restituted in LIA's own turns of phrase where they carry the personality: the chat wrote it in that
personality.

### 2. An expression wire per session, decided at its start

A session's engine either says its delivery in words alone (`prose`: Gemini Live, GPT-Live, an agent
whose engine performs no tag) or performs cues written inside its words (`cues`). The provider says
which through one door, `expression_dialect(api_key, model)`: native-audio providers answer without
the network; an ElevenLabs agent is read (`voice_sessions/expression.agent_dialect`: a realtime model,
or a v3/v4 voice whose expressive mode is on, performs tags). The answer is frozen on the session
record (`LiveSetupInputs.cue_dialect`) and a wake re-renders with it, never with a fresh read. A door
that fails degrades the session to words alone: a cue LIA cannot prove the engine performs is never
offered, and it never refuses a start.

### 3. The cue vocabulary has persona cues

`expressive_cues.Cue` gains ten persona cues — sarcastic, dismissive, cheeky, mischievous, annoyed,
weary, soft, slow, rushed, booming — chosen to cover the registers of the fourteen seeded
personalities, not one of them. `ELEVENLABS_AGENT_TAGS` spells them as the vendor documents them
(`[sarcastically]`, `[tired]`, `[softly]`…), from one table its v3/v4 speech engines share; the
speech engines measured to perform them spell them too, and the comment writer is offered them there
(§ 8); the radio writes none. A `cues` session's mandate carries a
block listing the offered cues in the ENGINE's spelling, each with what it sounds like
(`sound.<cue>`) — never when to use it, which is the personality's business. It publishes no count:
nothing between the voice and its engine could enforce one.

### 4. On an ElevenLabs agent, LIA writes what makes the voice its own

At every session (start and wake) `sync_agent` reads the agent once and writes, only where it
drifted: the override permission for the frame's two fields (the prompt and the greeting), merged
with the person's own permissions — refused, the start is refused; `ignore_default_personality` and,
on a `cues` session, the palette (`tts.suggested_audio_tags`, each tag described by its sound) — two
best-effort writes, a refusal costing its part, never the session. The palette travels inside the
agent's WHOLE `tts` block, sent back as stored (`voice_sessions.expression.palette_block`): the vendor
replaced the omitted booleans of a PATCHed overrides block (2026-09-16) and nobody measured its merge
of `tts`, so a partial block could have reset the person's voice. The frame empties the greeting
(`first_message: ""`): the portal's canned first sentence is the one a personality could never reach.
Activation probes the real frame, so the probe grants the same permission first. The voice, the
language, the model and the turn-taking stay the portal's.

### 5. The phone: the person's personality, a stranger's cordial manner

The owner's call carries the personality block and, on a `cues` agent, the cue block. The agent the
phone provisions drops the vendor's default persona (in its body and its fingerprint, so provisioned
agents re-sync once). Before every dial the agent receives the palette of the call it is about to
make: the person's whole vocabulary, or the cordial one (no persona cue, nothing familiar) for a
third party and a verification — in the same whole `tts` block. The baked third-party agent's `<personality_profile>` slot always
receives `third_party_manner` — the personality never travels as a dynamic variable.

### 6. The agent's tools are LIA's

`sync_agent` attaches EXACTLY the session's set. Anything else the agent carried is detached — the
person's own tools and LIA's other set are never deleted. What LIA left on this agent is then
released without force (`client.release_tool`): the set a new fingerprint retired, and every client
tool bearing one of LIA's live tool names (an earlier copy of its own sets, or a sibling instance's).
The vendor answers 409 for a tool another agent still holds, and that one is kept; every outcome is
counted (`live_agent_tools_swept_total{outcome}`: freed, in_use, refused). No workspace-wide scan:
another LIA instance on the same key keeps one kind's set detached, and deleting by name would break
it. The listing is read only when something was left (`client.list_tools`, client tools, paginated
and bounded by `ELEVENLABS_TOOLS_LIST_MAX_PAGES`), and an unreadable workspace skips the sweep, never
the session. An attach refused because the workspace lost a tool of the set re-creates the lost tools
in their place and retries once; a refusal no lost tool explains still refuses the start, and a set
the call just created is never « healed ».

### 7. No cue reaches the conversation

A `cues` session's assistant text is the vendor's transcript of what its model wrote, cues included.
ONE function, `expressive_cues.strip_transcript_cues`, removes every bounded bracketed span of it —
and a tag the text was cut inside at its end — and returns the tags it removed; its browser twin,
`lib/live/cue-strip.ts`, is pinned to it by a shared corpus
(`tests/unit/domains/voice/cue_strip_corpus.json`). The doors: the live turn archive
(`LiveService.archive_turn`, both modes, so the direct relay is clean), which also measures
(`live_voice_cues_per_turn`, and `live_voice_cues_invented_total` for the tags outside the person's
palette, case and blanks aside); the phone's transcript ingestion (`VoiceTranscript.from_vendor_payload`,
the agent's turns: the archive, the relay, the learning) and its third-party synthesis
(`payload.extract_transcript_text`); and the browser, on a session whose start answered
`expression: "cues"`: a caption line is re-shown from everything it heard, so a tag split across
fragments never shows, and the row the chat shows at once is the archived one — the archive request
carries the turn as transcribed, for the server's door to count. The person's own words are never
touched, and a `prose` session's are kept as transcribed: a bracket there is words.

### 8. The spoken comment, in the same order (lot 5, measured 2026-11-07)

A tool turn's spoken comment is written by a model of its own (the `voice_comment` slot) from the
records the answer kept, in the personality passed to it; an answer read aloud, a conversation's
included, is the written answer itself and needs nothing. The comment's frame
(`voice_comment_prompt.txt`) had a tone of its own: an « informal, peer-to-peer » posture, the
familiar « tu » imposed whatever the personality, cheerful examples, the personality halved on a
failure; its cues were described by WHEN (« cheerful — good news »), never offered a persona cue,
and a personality that failed to load reached it as an empty profile.

The frame now takes the live block's order: facts, acts, THE TARGET LANGUAGE and the frame's rules
first; the personality governs the words, the address, the comments and how a result is reported,
then the sound; an example shows a shape, never a tone or an address (the examples no longer say
« tu » nor « ! »); a failure is said exactly, in the personality's manner. A personality written in
another language shapes the manner, never the language — told only that the personality governs its
words, one family answered English contexts in French twice as often, so the same clause went into
the live block too. The cue block keeps the 2026-10-17 meanings for deliveries and sounds, lists the
persona cues by their sound, and lets the personality choose « within the rules below »: told it
above them, two families cued more of LIA's own acts than under the frame shipped before; within
them, the rate stayed inside the run's noise. A personality that failed to load reaches the
comment as the default one, as it reaches the written answer.

Persona cues reach the comment only on an engine measured to perform them, none read aloud (STT of
every clip): ElevenLabs v4, v4 Turbo and v3 Conversational (from the agent's one table), Fish Audio's
S2 models (the vendor's own word where its emotions page lists one — `[frustrated]`, `[soft tone]`,
`[in a hurry tone]` — LIA's plain word otherwise), Gemini 3.8 as the sentence's style (every persona
style accepted; « slow » 6.4 s against 3.4 s, « rushed » 2.2 s against 3.4 s). Not `drama-3` (its
directions undocumented, refused by ADR-345), not `s1`, not the earlier ElevenLabs models, OpenAI or
Edge: there the personality is heard in the words alone.

Measured on the dev instance, four model families × six personalities (normal, friend, cynic,
depressed, jarvis, teenager) × twelve contexts, one sample each, against the shipped frame:
contrary cues 4.2 % → 1.7 % (the cynic's cheerful ones 22.9 % → 8.3 %), an expected cue on news
48.6 % → 58.6 %, invented cues 2.8 % → 0.3 %, the familiar « tu » to a personality that says
« Monsieur » 8 of 24 → 0, key facts 93.1 % → 92.7 %, English contexts answered in French 11/144 →
11/144, a cue on LIA's own act 30.0 % → 33.3 % (z ≈ 0.55 at n = 120: within the run's noise, which
moved the same rate by 4 points between two variants differing in their language clause alone).
The strength of the manner stays the family's: the cynic is plainly sarcastic with two families and
stays sober with two others, before and after. Spend: 1.71 €.

## Consequences

- Every voice LIA speaks to the person is the configured personality's, in its words first —
  the spoken comment of a tool turn included (§ 8), an answer read aloud being the written answer
  itself; a stranger hears LIA's courtesy. How strongly a comment carries it depends on the model
  family writing it (§ 8).
- An agent used by LIA is LIA's for what LIA owns on it: the prompt, the greeting, the expression
  palette, the default persona and the tool list. The settings say so.
- The real-session oracle is relative to the personality under test, on four contrasting ones
  (cynic, enthusiastic, depressed, normal): no forbidden cue opening a turn, the expected cues
  present, the SUBSTANCE of every turn the personality's, the FACTS identical across the four, a
  third party cordial, no bracket in the chat. A personality failing the substance alone gets an
  allowed-cue list declared per personality — measured first, never assumed.
- Measurements still owed on the vendor: a PATCH of the palette on a realtime agent, the empty
  greeting on a real conversation, a non-forced delete answering 409 — on a throwaway agent.

## Amendment 2026-11-11 — every conversation opens on tools verified against the workspace

**Owner decision (2026-11-11).** An agent the person reaches through LIA — the phone (the person or
a third party) or a live session (delegated or direct) — never opens a conversation with tools out of
date or incomplete: LIA renames, changes and removes its tools, and anyone may edit or delete one on
the portal. § 6 already set the list at every start and wake; it did not look at what the workspace
held, and a reconnection did not look at all.

**Measured the same day** (throwaway agent and tools, dev workspace): the workspace serves back every
field LIA sent, unchanged — enums in their order, a webhook's header in clear — and adds its own
defaults; `PATCH /tools/{id}` replaces a tool's config under the same id, a setting changed by hand
falling back to its default; a tool deleted with force is taken off every agent silently, and naming
it in an agent PATCH answers 404; a delete without force of an attached tool answers 409 (the last of
the tool measurements the Consequences owed).

**Decision.**

- ONE door for both surfaces, `telephony/workspace_tools.py`: `holds` (a tool holds LIA's body when
  everything LIA sent is served as sent), `repair_set` (a drifted tool rewritten in place, a lost one
  re-created in its position, all or nothing), `create_tools` (concurrent under the bound, rolled back
  on any failure, a lost connection raised as itself), `agent_tool_ids` (what the agent carries).
- Live: a recorded set is held against the workspace's client tools BEFORE it is attached, at every
  opening — the start, the wake and now each reconnection (`LiveService._remint`, with the session's
  own setup). The set's fingerprint covers the bodies the workspace is sent (`set_bodies`), so a raised
  timeout re-provisions, as on the phone. The listing read to verify serves the sweep. A workspace
  that cannot be read, or a repair the vendor refuses, refuses the opening. This verification replaces
  the heal-after-a-refused-attach § 6 described.
- Phone: `ensure_vendor_live_tools` and `ensure_vendor_delegation_tool` hold the recorded tools
  against the workspace's webhook tools before every owner call and answer None when they cannot. The
  dial reads the agent ONCE (`TelephonyService._read_agent`, the palette's read too) and puts it in the
  call's exact tool state: a call to a third party or a verification clears whatever the agent
  carries, whatever the connector's note says. Tools that cannot be made exact, or an agent that cannot
  be put in the call's state, refuse the call (`agent_sync_failed`) — ADR-290 amendment 2026-11-11.
- Every repair is counted, `live_agent_tools_repaired_total{surface, reason}` (live or phone; drifted
  or lost), on panel 25 of dashboard 30.

**Not covered.** A conversation already open keeps the tools it opened with. A field the vendor adds
and LIA does not send (interruptions, sounds) stays as the portal set it until a repair rewrites the
tool. The agent's system tools (end call, transfers, language detection) stay the portal's. Removing
the Live connector, or no longer choosing an agent, leaves LIA's set in the workspace: taking it back
needs a vendor call outside the removal's transaction (ADR-304).
