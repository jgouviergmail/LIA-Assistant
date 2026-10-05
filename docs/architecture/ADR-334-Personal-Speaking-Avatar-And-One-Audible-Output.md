# ADR-334 — Personal speaking avatar and one audible output

**Status:** Proposed — 2026-10-05. The implementation and automated contracts are
available; final acceptance awaits the owner's provider and physical Android/iOS
media trials. This record does not certify lip motion or device compatibility.

**References:** [Speaking avatar](../technical/SPEAKING_AVATAR.md),
[voice](../technical/VOICE.md), [Live](../technical/LIVE_MODE.md),
[qualification record](../superpowers/specs/2026-10-04-simli-media-qualification.md).

## Context

A visual face can accompany LIA's existing voice comments and Live conversations.
Adding another conversational model or synthesizer would duplicate work, introduce
a second source of speech and make cancellation and costs harder to understand.
The integration must also distinguish an account's explicit spending permission
from a local preference for window position or appearance.

## Proposed design implemented for qualification

1. **Personal connector and explicit permission.** Simli uses the account's own
   encrypted connector credential. The deployment ceiling is `AVATAR_ENABLED`,
   disabled by default, and the account separately opts in and selects a face.
   Temporary session tokens and ICE credentials are returned with `no-store`;
   the long-lived key never reaches browser storage or a public environment value.
2. **One owner and one audible output.** The authenticated dashboard owns the
   engine and floating window. A shared voice-output port accepts already produced
   audio from comments or Live, converts actual decoded/captured audio to the
   provider's PCM contract, and selects either local or avatar playback. The
   video stays muted; a gesture-resumed Web Audio context renders remote sound.
   A potentially heard prefix is never replayed locally after an avatar failure.
3. **A connection follows an active mode.** Voice comments keep the connection
   between answers. Live takes priority; standby closes it and wake requests a
   fresh connection. Disabling the mode, leaving the dashboard or revoking the
   permission closes owned resources. Provider caps are finite, and renewal
   closes and verifies the previous session before admitting another one.
4. **Unknown creation is not permission to retry.** Shared Redis leases are
   scoped to a digest of the actual personal key. Failed or cancelled token
   creation can have an unknown remote outcome and quarantines admission until
   the finite lease expires. Release requires provider evidence of no active
   session. Redis failure disables avatar admission while retaining text/voice.
5. **Separate cost and media boundaries.** An open Simli session may consume the
   person's credits during silence. Settings state this consequence. Existing
   LIA model and TTS accounting continues; LIA does not invent a Simli tariff,
   credit balance or usage ledger. Radio remains outside this integration.
6. **Accessible geometry, bounded diagnostics.** The window has three sizes,
   pointer/touch dragging and keyboard movement, clamped to the visual viewport.
   Only bounded geometry persists locally. Diagnostics contain route selection,
   sample counts and lifecycle codes, never voice, transcript, keys or signed URLs.

## Consequences and acceptance boundary

No new agent, tool manifest, LangGraph state, conversation prompt or TTS request
is introduced. The animated companion yields while the speaking window is present
without losing its settings. Public copy calls the integration experimental.

Automated HTTP/signalling tests and a browser loopback WebRTC peer can establish
ownership, cancellation, one audible destination, standby, CSP and window behavior.
They cannot establish Simli's real lip motion, provider silence behavior, finite-cap
renewal or physical device audio output. Those checks remain pending and must be
recorded in the qualification document before this ADR becomes Accepted.
