# Voice Mode

LIA offers voice interaction through two input methods and configurable speech output.

## Voice Input

### Push-to-Talk
- When voice mode is off and the text field is empty, hold the send button to record
- Release to stop — LIA transcribes speech and places text in the input field
- Works on desktop and mobile (optimized for touch devices)

### Wake Word Detection
- Say "OK Guy" to activate hands-free recording
- Detection runs entirely in the browser using Sherpa-onnx WASM (no audio sent externally)
- An audible chime confirms the app is ready to listen
- Requires Voice Mode to be enabled in Settings

### Speech-to-Text (STT)
- **Local mode** (default): Sherpa-onnx Whisper running on LIA's server (99+ languages, fully offline). No audio leaves the server.
- **Remote mode** (opt-in): ElevenLabs Scribe ($0.22/h, billed per audio duration). Higher accuracy on conversational speech, especially in noisy environments.
- Transcription language matches the user's preferred language from Settings.
- For paid (remote) STT, a discreet 🎤 badge on each user message bubble shows the duration and EUR cost. The cost is included in the dashboard's **Cost** tile and in the user's usage limits — no separate quota.

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

### What the voice actually reads
The spoken text is stripped of markup before synthesis: formatting HTML, and the decorative icons of data cards whose names ("event", "mail") would otherwise be read aloud before the sentence. Prose is left untouched — a comparison such as "x<a and b>c" is not markup and is read as written.

## Configuration

- **Enable Voice Mode**: Settings > Voice Mode
- **TTS provider/model/voice**: Configuration LLM (admin) — `voice_tts` type, with per-provider tuning (Edge SSML rate/pitch/volume; OpenAI speed + format; ElevenLabs stability/similarity_boost/style/use_speaker_boost)
- **STT mode**: Settings > Voice Mode (local or remote, per-user opt-in)
- **Language**: Settings > Language (affects STT transcription)

## Admin Safety Levers (Cost Defence)

Two server-side safety mechanisms protect against ElevenLabs cost spikes when the remote STT mode is enabled:

- **Global kill switch** (`ELEVENLABS_STT_ENABLED`): when set to `false`, the WebSocket handler instantly forces every user back to the local Sherpa pipeline — the remote provider is never called. Useful for incident response or emergency quota management.
- **Per-clip duration cap** (`ELEVENLABS_STT_MAX_AUDIO_DURATION_SECONDS`, default 300): each clip is checked before any provider call. Oversized clips are rejected with a clear error code, no provider charge incurred.

## Privacy

- Wake word detection: browser-only (WASM), no external transmission
- Speech-to-text (local): LIA server only (Sherpa-onnx Whisper), no third-party API
- Speech-to-text (remote): your audio is transmitted to ElevenLabs (opt-in only, off by default; admin can disable globally)
- Voice output: depends on the active TTS provider (Edge = Microsoft, OpenAI = OpenAI, ElevenLabs = ElevenLabs)
