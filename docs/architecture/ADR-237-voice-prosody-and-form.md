# ADR-237 — Parametric voice prosody, and the form-modulation inventory

**Date**: 2026-08-19
**Status**: Accepted (D4 shipped; channel-form and stable-leanings scoped)
**Context**: Lot 4 of the evolution program ("naturel"). The psyche
engine computed a live PAD mood consumed by every TEXT surface, but the
voice spoke with static parameters: the words could be warm while the
prosody stayed flat.

## Decision

- **D4 — PAD → ElevenLabs voice_settings** (`domains/voice/prosody.py`,
  pure): arousal raises `style` and lowers `stability` (gentle gains,
  hard [0,1] clamps, ±0.1 dead-band so a flat mood costs nothing — the
  dead-band returns the base object itself, which downstream reads as
  "no override"). The admin-configured settings stay the BASE; the mood
  bends them, never replaces them. Resolved ONCE per stream
  (best-effort: a psyche failure never costs the user their audio),
  passed per-call through the TTS protocol's kwargs. Flag
  `VOICE_PSYCHE_PROSODY_ENABLED` (default on). Provider parity: OpenAI
  TTS has no equivalent parametric surface — the kwarg is ignored there
  by construction, a documented asymmetry rather than a silent drift.
  `pleasure` is accepted but unused: warmth cues need per-voice
  calibration before they earn a gain.
- **D2 — verified already satisfied, no change**: the four
  `RELATIONSHIP_STAGE_DIRECTIVES` explicitly modulate FORM (formality,
  humor, preamble, candor). Inventing a second mechanism would create
  two authorities on familiarity.
- **D3 (PAD half) — verified already satisfied, no change**: the base
  response prompt's `<InnerVoice>` clause already modulates length,
  warmth and suggestion count by mood ("shapes the FORM, never the
  facts").
- **D3 (channel half) — scoped, not shipped here**: the response LLM
  does not know it writes for Telegram vs web vs voice
  (`stream_chat_response` carries no output-surface parameter; the
  Telegram formatter reshapes AFTER generation). A proper fix threads
  one explicit parameter to the prompt and must first reconcile with
  the existing display-mode mechanism — its own change, not a rider.
- **D5 (stable leanings) — scoped, not shipped here**: deterministic
  tastes derived from Big Five traits are a product-voice decision
  (which leanings, how strong) that deserves the owner's eye on the
  actual registry content before it ships.

- **A2 — the briefing speaks**: `POST /briefing/synthesis/audio` reads
  the displayed synthesis aloud. The full readout unit (tracking context,
  voice-service lifecycle, sanitation, decoding) lives in the VOICE
  domain (`voice/text_readout.py`): a first draft in the briefing router
  closed a `briefing<->chat` runtime cycle (F009 guard caught it — chat
  already imports briefing for suggestions, and the tracker lives in
  chat). Bounded by `BRIEFING_AUDIO_MAX_CHARS` / `_MAX_SENTENCES` (cost
  bounds), buffered on purpose (a synthesis is a short paragraph, and a
  buffered response fails as a real HTTP error, never a broken stream).
  Frontend: a ghost icon control on the synthesis badge line
  (`useBriefingAudio`: one toggle, object-URL revoked on stop/unmount).

## Consequences

- The voice now breathes with the mood on ElevenLabs, within bounds an
  operator can audit (`VOICE_PROSODY_*` constants) and disable in one
  flag.
- Two verified-as-satisfied items are recorded here precisely so future
  audits do not re-propose them (the ADR-232 requalification doctrine).
