# Meeting Recording & Structured Minutes — Implementation Plan

- **Spec**: `docs/superpowers/specs/2026-09-02-meeting-recording-and-minutes-design.md`
- **Method**: inline, TDD (red → green per unit), every lot closed by the gates listed under it; no git action by the assistant.
- **Status legend**: `[ ]` todo · `[x]` done · `[~]` partial (say what is missing)

## Lot 0 — Prerequisites

- [x] 0.1 Shell microphone permissions: `apps/mobile/native/android/app/src/main/AndroidManifest.xml` (+ `RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS` with the Capacitor rationale), `apps/mobile/native/ios/App/App/Info.plist` (+ `NSMicrophoneUsageDescription`); `docs/guides/GUIDE_MOBILE_ANDROID.md` / `GUIDE_MOBILE_IOS.md` note that the probe measures API presence only.
- [x] 0.2 Silero VAD in the image: `scripts/download-whisper-model.sh` (+ `silero_vad.onnx`), `apps/api/Dockerfile.dev` + `Dockerfile.prod` model stage; constants `VOICE_STT_VAD_MODEL_PATH_DEFAULT`, `VOICE_STT_SINGLE_PASS_MAX_SECONDS_DEFAULT = 25`, `VOICE_STT_WINDOW_SECONDS_DEFAULT = 20`, VAD thresholds; settings in `core/config/voice.py`; `.env.example` / `.env.prod.example` voice block.
- [x] 0.3 `src/domains/voice/stt/long_audio.py`: pure `build_windows(segments, sample_rate, max_window_seconds)`; `SileroSegmenter` (lazy model, `segment(samples)`); `SherpaSttService.transcribe` routes buffers above the single-pass cap through windows (one decode per window, texts joined). Tests: `tests/unit/domains/voice/test_long_audio.py` (pure window merging, cap never exceeded, cut only on silences, empty input), `test_sherpa_long_audio_routing.py` (45 s buffer → N decodes, tail preserved; ≤ 25 s → one decode).
- [x] 0.4 `docs/technical/VOICE_MODE.md`: the 60 s cap is honoured end to end; explain the windowing.
- [x] Gates: `task lint:backend`, targeted pytest, `task lint:docs:preview`.

## Lot 1 — Backend foundation (`domains/meetings`)

- [x] 1.1 Constants + `core/config/meetings.py` (+ MRO, `__all__`) + env blocks `[87]`; compose volume `meetings_data`.
- [x] 1.2 `models.py` (Meeting, MeetingTemplate, MeetingPreference, enums with `native_enum=False`), `registry.py` import, `user_data_map.py` rules, migration (replay-checked), `rag_spaces.kind` column + partial unique index (same migration), `RAGDocumentSourceType.MEETING`.
- [x] 1.3 `schemas.py` (requests/responses, `MeetingReport`, template sections, preferences), `templates.py` (default template, validation), `core/i18n_meetings.py` ×6.
- [x] 1.4 `repository.py` (list with exact total, active lookup, atomic claim/heartbeat/complete/fail/requeue, stale scan), `audio_store.py` (containment, per-segment atomic write, assembly, purge), `service.py` (start/segment/stop/resume/discard/retry; ownership `hide_existence=True`; usage-limit preflight; engine preflight).
- [x] 1.5 `router.py` under `capability_dependencies(PlatformCapability.MEETINGS)`; `routes.py` inclusion + `features.meetings_enabled`; capability enum/spec/setting key/map node/section pairing/i18n labels ×6.
- [x] 1.6 `reapers.py` (stale recording, stuck job, audio retention) + scheduler registration with jitter + job id constants; `metrics_meetings.py` + `27-meetings.json`.
- [x] 1.7 ADR-258 + `docs/technical/MEETINGS.md` + `docs/INDEX.md` + `ADR_INDEX.md`.
- [x] Tests: models/enums, schemas round trip, template default/validation, service transitions (refused starts, idempotent segments, RETURNING ack, stop with gaps, fresh re-read), reaper transitions, capability guards, metric coverage. Repository SQL and router auth remain covered by the runtime proof (8.1), not by a real-PostgreSQL integration suite.

## Lot 2 — Transcription and synthesis

- [x] 2.1 `voice/stt/protocol.py` file method + `STTFileResult`/`TranscriptTurn`; `elevenlabs_stt.py` file method (diarize, words → turns); `openai_stt.py` (file + PCM parity); provider registry + `STT_PROVIDER_DEFAULT_MODELS`; `factory.py` dispatch by slot provider.
- [x] 2.2 Seeds: `llm_models` rows (`gpt-4o-transcribe-diarize`, `gpt-4o-mini-transcribe`, kind `audio`) + `llm_model_pricing` rows `per_audio_minute`.
- [x] 2.3 `meetings/transcription.py` (engine chain, normalization via ffmpeg subprocess, bitrate under 25 MB, local windows through the STT executor with heartbeats).
- [x] 2.4 LLM type `meeting_synthesis` (registry, defaults, `LLMType` Literal, count guard 58, admin i18n ×6, doc counts); `prompts/v1/meeting_synthesis_prompt.txt` + `PromptName`; `meetings/prompts.py`; `synthesis.py` (context, structured output, repair, token tracking).
- [x] 2.5 Enrichment (calendar overlap, reverse geocoding), processing job (`processing.py`), retry/regenerate endpoints.
- [x] Tests: provider clients with httpx mocks (shapes measured live), chain matrix (+ exclusion walk), bitrate selection, turns building, repair matrix, condensation, prompt hygiene, job classification and regeneration with fakes (`test_processing_flow.py`), `transcribe_with_fallback` matrix. Integration claim/lease/requeue on real PostgreSQL: NOT written (the proof exercised one worker only).

## Lot 3 — Outputs

- [x] 3.1 `indexing.py` (space get-or-create by kind, caps exemption in `rag_spaces/service.py`, `.md` write, `rag_documents` create/requeue, `process_document`), frontend `source_type` union + badge.
- [x] 3.2 `render.py` single serializer → Markdown / `SectionedContent` / HTML; `GET …/pdf`; `POST …/email` (`resolve_client_for_category`).
- [x] 3.3 Dispatcher `task_type="meeting"` + `ProactiveMessages._TITLES["meeting"]` ×6; `auto_email`.
- [x] 3.4 `agents/tools/meetings_tools.py` + manifest + `program_manifests.py` + `document` domain description + registry smoke.
- [x] 3.5 GDPR export: `_DECRYPTED_COLUMNS`, files directory.
- [x] Tests: serializer round trip, PDF header, HTML escaping, email refusal codes, indexing path containment and space creation race, enrichment; dispatcher payload and tool totals covered by the runtime proof.

## Lot 4 — Frontend

- [x] 4.1 `lib/audio/pcm-worklet.ts` (shared with `useVoiceInput`), `lib/meetings/{sources,segment-uploader,silence-watchdog}.ts`, `lib/wake-lock.ts`, `stores/meetingRecorderStore.ts` (+ storage purge key).
- [x] 4.2 `hooks/useMeetingRecorder.ts`, `hooks/useMeetings.ts`, `hooks/useMeetingTemplate.ts`, `hooks/useMeetingPreferences.ts`; `components/meetings/MeetingRecorderProvider.tsx` in `dashboard/layout.tsx`.
- [x] 4.3 `ChatInput`: paperclip `DropdownMenu`, recording chip, `isPttOffered`; `voiceModeStore.isSuspended` + `useVoiceMode` gate; TTS mute while recording; `MeetingRecordingBanner`; start dialog.
- [x] 4.4 Pages `dashboard/meetings` + `[id]`; `MeetingReportCard` in `ChatMessage`; `MeetingsSettings` + registry + search meta + keywords ×6; slash command `meetings`; `useAppConfig.features.meetings_enabled`; `api-config` endpoints; i18n ×6.
- [x] Gates: `task lint:frontend`, `pnpm exec tsc --noEmit --incremental false`, `task test:frontend:coverage`, ratchets, `task lint:i18n`.

## Lot 5 — Governance and proof

- [x] 5.1 Docker runtime proof through the HTTP contract (spec §8.1): PCM + Opus, OpenAI (by fallback) + local, RAG READY, PDF, email refusal code, edit/reset/regenerate/delete. NOT done: Scribe with a real key, a real browser/device run, the chat card seen in a browser.
- [ ] 5.2 Device protocol in the mobile guides; `task meetings:probe:stt` (dev-only Pi RTF probe).
- [ ] 5.3 `task ci:fast`; coverage ratchets raised when ≥ 2 pts margin (gates run at the end of the review pass — see the final report).
- [ ] 5.4 Release surfaces at release time (CHANGELOG, FAQ ×6, knowledge, README, landing, guides) — separate release lot.
