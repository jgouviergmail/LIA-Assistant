# Voice Mode

LIA offers voice interaction through two input methods and configurable speech output — and, since v1.47, a real-time Live mode on the person's own key.

## Voice Input

### Push-to-Talk
- When voice mode is off and the text field is empty, hold the send button to record
- Release to stop — LIA transcribes speech and places text in the input field
- Works on desktop and mobile (optimized for touch devices)

### Wake Word Detection (French, beta)
- With a French interface, say "Dis LIA" to activate hands-free recording; the other interface languages have no phrase yet and keep tap-to-speak and the long press
- The wake word is in beta: its recognition is still improving, so it may ask you to repeat yourself or trigger by mistake
- Detection runs entirely in the browser: a small trained model run by ONNX Runtime (WebAssembly) in a worker, every file checked against its fingerprint — no audio leaves the device before LIA hears it, iPhone included
- While LIA reads an answer aloud, say "Stop" to cut her voice (nothing is recorded or sent), or "Dis LIA" to cut it and speak at once
- An audible chime confirms the app is ready to listen
- Requires hands-free mode: tap the greyed microphone badge in the chat header (or use Settings > Voice Mode); hold the badge, or hold Space, to turn it off

### Speech-to-Text (STT)
- **Local mode** (default): Sherpa-onnx Whisper running on LIA's server (99+ languages, fully offline). No audio leaves the server.
- **Remote mode** (opt-in): ElevenLabs Scribe ($0.22/h, billed per audio duration). Higher accuracy on conversational speech, especially in noisy environments.
- Transcription language matches the user's preferred language from Settings.
- For paid (remote) STT, a discreet 🎤 badge on each user message bubble shows the duration and EUR cost. The cost is included in the dashboard's **Cost** tile and in the user's usage limits — no separate quota.

### Is my voice data sent to external services?

Wake-word detection runs in your browser; the detection model does not upload the audio it listens to. **Local speech-to-text** uses Sherpa-onnx Whisper on the LIA server. Optional **remote STT** sends your recording to ElevenLabs Scribe; it is off by default and requires your choice in Settings → Voice mode.

Other voice paths have their own boundaries: spoken responses can use your configured TTS provider, **Live and Live direct** send the session audio and useful context to the selected voice provider, and an enabled **Simli avatar** receives LIA’s output audio for lip synchronisation. Those services’ processing and retention policies apply. Disabling remote STT does not disable these separate paths.

## Voice Output (TTS)

| Provider | Models | Cost |
|----------|--------|------|
| Edge TTS | Microsoft neural voices | Free (default) |
| OpenAI TTS | `tts-1`, `tts-1-hd` | Premium |
| ElevenLabs | `eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5` | Premium |

- Voice comments can be added to any LIA response
- Multiple audio formats supported (MP3, Opus, AAC, FLAC, WAV, PCM)
- Progressive sentence streaming: the first sentence plays while the rest of the response is still being generated (~1 s perceived latency for the first audio chunk)
- For paid TTS, a 🔊 badge on each assistant message shows the character count and EUR cost; Edge stays free with no badge
- ElevenLabs synthesis shares the instance's configured concurrency allowance across API workers and voice features. If a segment waits for capacity, the player still plays the finished segments in their spoken order; the administrator sets the allowance to match the ElevenLabs account.

### What the voice actually reads
The spoken text is stripped of markup before synthesis: formatting HTML, and the decorative icons of data cards whose names ("event", "mail") would otherwise be read aloud before the sentence. Prose is left untouched — a comparison such as "x<a and b>c" is not markup and is read as written.

### Where a spoken sentence ends
A full stop closes a sentence only when a space follows it, so a decimal number, a price, a version number or a web address stays inside one spoken sentence: "it's 3.5 degrees" is read as a single phrase rather than "it's three" followed by "point five degrees" in a separate audio chunk. The same rule governs both the one-shot and the progressive path, so the sentence you hear does not depend on how fast the response was generated.

## Configuration

- **Enable Voice Mode**: Settings > Voice Mode
- **TTS provider/model/voice**: Configuration LLM (admin) — `voice_tts` type, with per-provider tuning (Edge SSML rate/pitch/volume; OpenAI speed + format; ElevenLabs stability/similarity_boost/style/use_speaker_boost)
- **STT mode**: Settings > Voice Mode (local or remote, per-user opt-in)
- **Language**: Settings > Language (affects STT transcription)

## Admin Safety Levers (Cost Defence)

Two server-side safety mechanisms protect against ElevenLabs cost spikes when the remote STT mode is enabled:

- **Global kill switch** (`ELEVENLABS_STT_ENABLED`): when set to `false`, the WebSocket handler instantly forces every user back to the local Sherpa pipeline — the remote provider is never called. Useful for incident response or emergency quota management.
- **Per-clip duration cap** (`ELEVENLABS_STT_MAX_AUDIO_DURATION_SECONDS`, default 300): each clip is checked before any provider call. Oversized clips are rejected with a clear error code, no provider charge incurred.

## Live mode

### What is the Live mode, and how do I start a session?
A conversation with LIA **voice to voice, in real time**: you speak, it answers as it listens, you can interrupt it. It runs on a live model you connect with **your own key** — Gemini Live, GPT-Live or an ElevenLabs agent — from **Settings → Connectors** (the « Live » family, additive: you may hold several). Once a connector is active, the voice icon in the chat header becomes a menu: **Live session (brand)** opens one. A band above the thread shows the captions, the time left and an indicative meter; the extension dialog asks before the cap, and after a silence the session goes on standby instead of ending — nothing is billed until it wakes.

**🧠 Two intelligences, one seam:** the voice holds the conversation; every request for data or action is handed to LIA, which runs it as an ordinary chat turn — the same confirmations, the same registers, the same quotas — drawn in the thread while you speak. A question LIA needs to ask you is what the voice says next.

### « Live session » or « Direct live session » — what is the difference?
**🎧 Live session** — the voice delegates: each thing you ask becomes a chat turn of yours, run by LIA while you speak, with confirmations for anything that acts and every answer drawn in the thread. This is the mode that can DO things.

**🎯 Direct live session** — the voice reads your data itself, without going through the chat: your agenda, mails, contacts, tasks, places, the weather, what LIA remembers — the domains you allow in **Settings → Telephony · My identity**, the same switches as the phone. It acts on nothing: a request is noted, and at the end everything you said is relayed to the conversation as a message from you, which LIA answers. It buys latency, not economy: the tools' declarations are re-billed on every turn by the provider, about nine times the text prompt of a delegated session in our measurement. Offered only where the model's wire carries a tool schema (an ElevenLabs agent does not).

### What does a Live session cost, and who pays?
Two bills, one of which is yours alone.

**🔑 What the provider charges — on your key:** the live model's audio, in and out, is billed by the provider on your own account. The band shows an **indicative** meter folded from the provider's own usage reports and the tariff your administrator declared, with the context size; a cost that would need an undeclared rate is shown as unavailable, never as a partial figure. On an ElevenLabs agent the platform prices nothing: the clock alone runs, and the provider's own bill is shown once at the end. Nothing of this is recorded anywhere — it is your key. Settings › Live mode lets you set an optional spend ceiling per session.

**💶 What LIA counts:** what LIA herself spends inside a session — each request you delegated, and in a direct session the lookups and the relayed turn — is counted like any chat message, under your usage limits, and added up on the closing card.

### What does LIA keep of a Live session?
**🎧 In a Live session:** each request you delegated is a chat turn, kept like any other, and the exchanges that stayed voice-only — small talk, an aside — are archived as two visible lines at the end of each turn, so the conversation reads as it happened; memories and interests learn from them as they would from a typed message. The session closes on one card: how it ended, the duration, the requests, the voice exchanges, LIA's own cost.

**🎯 In a direct session:** nothing is archived while you speak — the captions live in the band. At the end, what you said is written up and relayed to the conversation as a message from you; the card says « relaying », then is rewritten once LIA answered, with its cost re-read. What the audio was is the provider's and yours: the platform never receives it.

**🧾 In every case:** the registers record that a session took place and which capability LIA read for you — never a word of what was said.

### What happens when a Live session goes on standby?
After the model's silence timeout, when the page stays hidden, or when you tap the standby button, the session falls asleep instead of ending: the connection to the provider closes, so **nothing is billed** during the standby, but the session stays open — its requests, its meter and its closing card wait for you.

**⏰ Waking it:** tap **Wake up** in the band or, with a French interface, say "Dis LIA" (beta) while the page is visible. LIA opens a new connection with its own context of the moment — the time, its state, your settings: the memory is the application's, not the provider's. On an iPhone, keep the screen on so that it can hear you.

**🛑 Ending it:** a session only ends on your gesture; an unbroken standby past the length your instance sets (8 hours by default) closes it by itself. The session's cap, its duration and the meter count awake time only, and the closing card says how many times it slept. In a direct session, what you said is relayed into the conversation at each standby.

### Settings › Live mode
The model (choosing it is choosing its provider), the voice with a sample on every change, the thinking level where the model offers one, how the conversation behaves (interruptions, end of speech, when LIA delivers an answer), the silence and the duration cap per model (`0` = no limit, under a billing warning), an optional spend ceiling per session. Every model you connect keeps its own settings. The header's voice menu follows these settings at once.

**On iPhone and iPad**, an ElevenLabs agent goes through its provider's native audio link (WebRTC), which plays more steadily than the raw audio stream on those devices. At the end of a session the browser reports aggregate playback counts (chunks, gaps, sample rates) — never any audio or transcript — so an audio problem can be diagnosed.

**A Gemini key restricted by IP address** is refused by Google when the connection comes from your browser. LIA names that cause instead of failing silently: use a separate Gemini key without an IP restriction for the Live connector.

## Privacy

- Wake word detection: browser-only (ONNX Runtime, WebAssembly in a worker), no external transmission
- Speech-to-text (local): LIA server only (Sherpa-onnx Whisper), no third-party API
- Speech-to-text (remote): your audio is transmitted to ElevenLabs (opt-in only, off by default; admin can disable globally)
- Voice output: depends on the active TTS provider (Edge = Microsoft, OpenAI = OpenAI, ElevenLabs = ElevenLabs)
- Live mode: your voice and LIA's answers transit directly between your browser and the live provider you connected with your own key — the audio never passes through the LIA server; the provider's usage and bill are yours, shown once, recorded nowhere

## Can LIA speak through an avatar, and what does it cost?

Yes, as an **experimental beta**, when your instance enables it. Connect **Simli** in Settings › Connectors using your own account key, stored encrypted, then explicitly enable the speaking avatar and choose a face. Connecting the service alone does not switch it on.

The avatar uses the audio LIA already produces for **voice comments, Live and Live direct**. Its floating window moves by dragging or arrow keys and offers three sizes. Radio keeps its own player. You may need to tap **Enable audio** when your browser asks for a gesture.

**💶 Personal cost:** the active connection consumes your Simli plan even during silence between answers. Live standby closes it; waking starts a new connection. Disable the avatar to close it. This charge belongs to your Simli account, outside the platform's usage limits.

If the avatar is unavailable, the existing text and voice paths remain usable. Speech-driven facial realism and physical Android/iOS behaviour are still being qualified; this beta does not promise identical results on every device.

**Privacy:** enabling it sends LIA's spoken output to Simli to generate the face. It does not send your microphone audio to Simli; the voice provider's own processing still applies.
