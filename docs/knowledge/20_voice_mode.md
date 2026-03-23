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
- Uses Whisper model running on LIA's server (99+ languages, fully offline)
- Transcription language matches the user's preferred language from Settings
- No audio data is sent to any third-party service

## Voice Output (TTS)

| Mode | Provider | Cost |
|------|----------|------|
| Standard | Edge TTS (Microsoft Neural) | Free |
| HD | OpenAI TTS / Gemini TTS | Premium |

- Voice comments can be added to any LIA response
- Multiple audio formats supported (MP3, Opus, AAC, FLAC, WAV, PCM)

## Configuration

- **Enable Voice Mode**: Settings > Voice Mode
- **TTS Mode**: System Settings (admin) — Standard or HD
- **Language**: Settings > Language (affects STT transcription)

## Privacy

- Wake word detection: browser-only (WASM), no external transmission
- Speech-to-text: LIA server only (Whisper), no third-party API
- Voice output: depends on TTS provider (Edge TTS = Microsoft, OpenAI TTS = OpenAI)
