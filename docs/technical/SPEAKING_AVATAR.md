# Speaking avatar (Simli)

The integration is experimental. [ADR-334](../architecture/ADR-334-Personal-Speaking-Avatar-And-One-Audible-Output.md)
is **Proposed** pending the owner's provider and physical Android/iOS trials;
automated media contracts do not establish vendor lip motion or device compatibility.

Simli adds a face to audio that LIA already produces. It uses the person's own
Simli connector and requires an explicit account opt-in in Settings. Radio is
outside this first integration: its different voices require a separate cast
and playback design. No additional LLM call, prompt, TTS synthesis or LangGraph
state is introduced.

## Activation and ownership

The authenticated dashboard owns one engine and one floating window per account.
With voice comments enabled, it connects once and stays connected between
responses, including silence. Live takes priority and retains the same connection
when the account, credential version and face are unchanged. Live standby closes
the connection even if comments were enabled; wake requests a fresh connection.
Stopping a response sends `SKIP`; disabling the mode, leaving the dashboard or
revoking permission closes the owned connection with `DONE` and disposes its
media. A source EOF never closes the session.

The window supports small, medium and large presets, pointer/touch dragging and
arrow keys. Like the animated companion, one compact button cycles through the
sizes, revealed on hover, keyboard focus or a tap on touch screens. The video
fills the frame without a permanent title or size-selection row.
Geometry is clamped to the visual viewport on appearance, resizing,
rotation and zoom. Only bounded window geometry is stored locally. The animated
Eyes widget is hidden while the Simli window is present, without changing Eyes
preferences. Simli is optional; a missing connector or disabled opt-in preserves
the existing voice path.

## Configuration and API

The operator ceiling is `AVATAR_ENABLED`; the user's opt-in defaults to false.
The remaining settings are declared in
[`core/config/avatars.py`](../../apps/api/src/core/config/avatars.py): finite
session and idle limits, HTTP and establishment timeouts, and token-mint rate
limits. The [guided installer](../guides/GUIDE_SELF_HOSTING.md) asks whether to
offer the feature and emits those finite bounds; its answer and the account's
permission are separate. `Settings` composes `AvatarSettings` with the other
domains. No new Compose service or runtime dependency is introduced. The normal
migration chain adds the account opt-in and connector availability before API
startup. No platform Simli key is configured and no browser environment variable
contains a long-lived key.

The authenticated `/avatars` API exposes configuration, available faces,
preferences, session creation, heartbeat and verified release. The connector key
uses the existing encrypted credential infrastructure. Session responses contain
only a temporary token and ICE credentials and are marked `no-store`.
Preferences persist the account opt-in and the face UUID; the catalogue merges
a reviewed public catalogue with the account's private faces and account agents.
Account names take precedence when an agent refers to a public face. The static
selection preview uses a reviewed public image when available; an account-only
face without a published image has a placeholder. A custom UUID can be
entered when the catalogue cannot supply a face. Listing faces never opens a
paid session. `/faces` alone does not list agents referring to public faces;
the independent read of `/auto/agents` supplies those account aliases. Failure of
either read preserves the other catalogue and the public presets.

Admission reads detached account snapshots before and after token creation.
Database transactions do not span vendor HTTP requests. Redis compare-and-set
leases are keyed by a digest of the actual personal key, so tabs, workers and
accounts sharing that key cannot open concurrent owned sessions. Redis failure
disables avatar admission while leaving text and voice available. A failed or
cancelled token POST has an unknown outcome and is quarantined until its finite
lease expires: it is never automatically retried. A matching ready lease is
released only after Simli reports zero active sessions. A browser close is not
proof that a vendor session ended. Manual retry still passes those controls.
Known refusals before mint, including the local rate limit, do not quarantine a
session that was never created. The UI distinguishes these refusals from an
unknown provider outcome.

Finite provider caps require sequential renewal. The engine closes and verifies
the previous session before minting a replacement, preserving the window and
gesture-unlocked context. An unverifiable release stops renewal instead of
overlapping paid sessions. Revocation is cooperative: the existing token cannot
be remotely revoked by this API, so the browser closes on refresh/heartbeat; an
unreachable or modified client remains bounded by the provider session cap.

## Audio contract

The frontend implements the documented Compose P2P v2 protocol with SFU enabled,
`handleSilence`, finite `maxSessionLength`/`maxIdleTime`, `audioInputFormat=pcm16`
and an initial frame. It uses the vendor's ICE servers. Unsupported controls for
emotion, gaze, FPS or facial rig parameters are not invented. Psyche has no new
avatar payload or visual halo: the existing voice expressivity remains the
source of prosody, and a halo does not improve generated facial motion.
The documented emotions belong to Simli Auto. The current Compose token schema
does not declare emotion or model-selection fields, although older SDK examples
still mention a model. Those examples are not evidence of a current Compose
control.

Input is PCM16 little-endian, mono, at the vendor's required sample rate. A
stateful anti-alias FIR resamples the actual decoded buffer or capture context
rate, averages channels and preserves weak sound and interior silence. PCM
leaves as soon as the socket accepts it, up to a bounded lead ahead of the
remote playout (`AVATAR_PCM_LEAD_MAX_SECONDS`): the provider buffers what it
receives — its own reference client forwards whole TTS chunks unpaced — and
`SKIP` empties that buffer on an interruption. Pacing packets to the sample
clock instead left the provider about 85 ms of lead (measured: first remote
sound 290 ms after the first of two 187.5 ms packets), so every decode, render
or throttled tab starved it into silence frames — a mouth closing at the packet
cadence. The packetizer holds an unpadded partial packet only until the clip
ends or the provider stream pauses (`LIVE_PCM_TAIL_HOLD_MS`); backpressure is
the socket's own, bounded in memory and in time (`AVATAR_PCM_SEND_STALL_MS`).
Encoded queues and PCM queues are bounded, and epochs discard stale work after
cancellation or account changes.

Voice comments decode each clip once through `AudioQueue`. Raw PCM comments
are wrapped in a WAV container using their actual configured
sample rate before browser decoding. Encoded MP3 and MP4/AAC clips use the
browser decoder; neither encoded bytes nor a WAV header is sent to Simli.
Gemini and ElevenLabs WebSocket use the existing PCM player seam. OpenAI WebRTC hands its borrowed
remote stream to a receive-only AudioWorklet. ElevenLabs WebRTC installs the
exported `@elevenlabs/client/internal` audio adapter after the browser SDK import
and before session start, avoiding the SDK's analysis callback filter. It does
not open another SDK session or microphone. The installed SDK contract is
covered by transport tests; changing that dependency requires requalification.
LIA does not currently offer the SDK's output-device or volume-analysis controls;
the adapter does not claim to implement those unused interfaces.

Every production chooses one destination at its boundary. If Simli is not ready,
the whole production remains local even if readiness arrives later. A production
is one spoken answer — every clip of it joins ONE phrase, so the face never
drains and restarts between two sentences (measured: about 0.6 s of idle face
per sentence boundary before) — or one Live reply. Its boundary is the observed
drain: `voice_complete` for comments (else `VOICE_RUN_END_HOLD_MS` after the
last clip), no chunk for `LIVE_PCM_PRODUCTION_HOLD_MS` with the output drained
for Live PCM. A provider's own EOF (Gemini's `generationComplete`) or speaking
hint only shortens that wait, because ElevenLabs over WebSocket emits no audio
EOF at all — its `agent_response` precedes its audio chunks — and a route
latched until a signal that never comes held every reply local. When routed
to Simli, one native video element presents the remote video and the
gesture-resumed AudioContext renders the remote audio, through a gain that
opens for the phrase and closes after it. The element stays muted for its whole
life: unmuting it needs a `play()` with sound, which a real Chrome refused
outside a gesture (measured 2026-10-04 — a headless Chromium accepted it) while
a resumed context keeps running without one.
Failure after a potentially audible prefix cancels the avatar output without
replaying the same phrase locally; a later boundary can use local audio. Native
capture failure can continue the original borrowed stream without replaying it.
Cleanup never stops borrowed provider or microphone tracks. Readiness requires a
real video frame, the remote audio track and a RUNNING context, not `START` or
`ACK`. The context is resumed inside a human gesture (the shell's pointer and key
listeners, the window's button, a Live start or wake) and stays running; where
the browser refuses that, the « enable audio » button stays. A Live session
connects its provider only once the avatar is ready, has given up or reached a
bound (`awaitAvatarReady`, the controller's `awaitAvatar` dependency, at the
start and at every wake): a face still connecting while the first reply plays
would hand that reply to the local player (owner decision 2026-10-05). Output observation and submitted sample clocks govern drain; `SILENT`,
transcript quiet and a provider's speaking hint are not an audio EOF.
`handleSilence` keeps idle facial motion when no audio is submitted. Such motion
is not proof of speech-driven lips. Development diagnostics distinguish the
chosen output route, decoded rate/frame count, submitted PCM sample count and
observed remote audio, and record only whitelisted provider controls. They contain
no voice content, transcript, identifier, key, ICE credential or signed URL.

## Cost and privacy

An open session can consume personal Simli credits during silence. The user-facing
settings explain that persistent connection. LIA stores no personal Simli
minutes, credit balance, duration billing or cost ledger. Existing LIA LLM and
TTS accounting continues on its original path. The prior probe's balance change
is evidence of that account's consumption, not a universal tariff or rounding
rule. Limits protect admission and resource use; they do not estimate the bill.

Fixed vendor origins, bounded responses, no redirects, no implicit POST retries,
strict typed payloads and safe error codes protect the service. Tokens, ICE
credentials, keys and audio are ephemeral; diagnostics do not log their content.
Only Simli's exact WebSocket origin is added to the production CSP.

## Qualification

See the [qualification record](../superpowers/specs/2026-10-04-simli-media-qualification.md)
for the executed gates and outstanding physical checks, and the
[TDD plan](../superpowers/plans/2026-10-04-simli-speaking-avatar.md) for risk coverage.
Automated tests use simulated vendor HTTP/signalling with real PostgreSQL/Redis
where applicable. Browser journeys use a genuine loopback WebRTC peer carrying
canvas video and generated audio; they never contact Simli or a paid voice
provider. Such tests prove routing, ownership, lifecycle, CSP and UI behavior,
not vendor lip motion or mobile hardware compatibility.

The owner will perform Android and iOS trials. Record device, OS, browser or
WebView, audio output, avatar and app build, then measure startup, warm latency,
AV offset, weak phonemes, interior pauses, barge-in residue, standby/wake,
orientation/keyboard bounds, headset/Bluetooth/AEC, and OS interruptions.
Long silence and real finite-cap renewal also require provider qualification.
Do not mark those checks successful from a desktop synthetic-media test.

Primary references: [audio contract](https://docs.simli.com/api-reference/simli-webrtc),
[Compose token](https://docs.simli.com/api-reference/compose-session-token),
[P2P protocol](https://docs.simli.com/api-reference/websockets/peer_to_peer), and
[public faces](https://docs.simli.com/api-reference/preset-faces). The
[official-documentation audit](../superpowers/specs/2026-10-04-simli-media-qualification.md)
also records SDK/example discrepancies and the unresolved real lip-motion report.
