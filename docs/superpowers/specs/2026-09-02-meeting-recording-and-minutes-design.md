# Meeting Recording & Structured Minutes — Design Specification

- **Date**: 2026-09-02 (revised the same day after live provider probes)
- **Status**: Design for owner validation, pre-implementation (no code written)
- **ADR**: ADR-258 (to be written in Lot 1)
- **Patterns mirrored**: `telephony` (durable entity + reapers + synthesis with token tracking), `rag_spaces` (durable ingestion pipeline, ADR-129), `document_generation` (structured LLM output → pure renderer → PDF), `attachments` (per-user disk storage, magic-byte validation), `voice/stt` (provider factory + audio-billed pricing, ADR-080), `NotificationDispatcher` (archive + push + SSE + Telegram in one call)

## 1. Goal

From the composer's paperclip, the user starts recording a meeting or a spoken exchange (phone or computer microphone). Stopping the recording hands the whole audio to LIA, which transcribes it and produces **structured minutes**: date, start and end times, location when available, participants, a relevant title, then the sections of the user's **minutes template** (summary, topics, decisions, action items with owners and deadlines, risks and points of vigilance, open questions by default). The minutes can be sent to the user by email and downloaded as a PDF, and always feed a knowledge space called « Réunions », created on demand, so later questions can be answered by RAG.

The **template is the user's**: every account can reorder, rename, add or remove sections and change the instruction each section gives the model, and can reset to the default template. The data model prepares the announced follow-up (a template library and per-meeting format choice) without shipping it.

Hard constraints from the owner: **it must work in the PWA, cleanly and fluidly**, and **the fallback when the user has no ElevenLabs key must hold up**.

## 2. Validated foundations

Every statement below was verified in the code, measured in the dev container, executed against the real provider APIs, or confirmed against the vendor's source or documentation. Nothing in this section is an assumption.

### 2.1 Measurements executed in `lia-api-dev` (2026-09-02)

| Probe | Result |
|---|---|
| Local Whisper (sherpa-onnx) on a 127.6 s synthetic French meeting, ONE call | Only the first ~30 s transcribed (1 of 7 sentinel words). The engine logs `Only waves less than 30 seconds are supported. We process only the first 30 seconds and discard the remaining data`; truncation to 2950 frames confirmed in `offline-recognizer-whisper-impl.h`. |
| Same audio, fixed 25 s windows | 5 of 7 sentinels: words cut at window boundaries are lost. |
| Same audio, Silero VAD segments as emitted (1.2–3.2 s) | 4 of 7: Whisper loses context on scraps. |
| Same audio, VAD-aligned windows cut only at silences, ≤ 15 s / ≤ 20 s | **6 of 7 fuzzy** (the 7th is a genuine misrecognition, « giraffe » for « girafe »). RTF 0.22–0.25 on the dev host (4 threads). Best local policy. |
| **ElevenLabs Scribe v2, live** (key supplied by the owner for the probe, used in memory only): two-voice 53 s Ogg/Opus dialogue, `diarize=true` | HTTP 200 in 2.1 s, `language_code=fra`, **2 speakers separated exactly** (Denise → `speaker_0`, Henri → `speaker_1`, 56 words each), `speaker_id` on every word. |
| Scribe, same audio as **raw PCM 16 kHz** (`file_format=pcm_s16le_16`) with `diarize=true` | Identical result (200, 2.3 s, 2 speakers): the format the WebSocket already uses works for long files with diarization. |
| Scribe, WebM/Opus **truncated at 60 % of its bytes** (crash case), as-is | **Accepted** (200, 30.95 s decoded, 2 speakers). After `ffmpeg -c copy` remux: same. |
| Scribe, the 127.6 s single-speaker meeting | 200 in 4.6 s, **7 of 7 sentinels**, 1 speaker. |
| **OpenAI transcription, live** (dev provider key): 53 s WebM → `gpt-4o-mini-transcribe` | 200 in 2.7 s, full text. |
| OpenAI `gpt-4o-transcribe-diarize`, `response_format=diarized_json`, `chunking_strategy=auto` | 200 in 23.8 s, `segments[{speaker, start, end, text}]`, speakers `A`/`B` correctly separated, `duration=53.1`. |
| OpenAI, Ogg/Opus input (not in the documented format list) and the 127.6 s MP3 with `chunking_strategy=auto` | Both 200; **7 of 7 sentinels** on the long audio in 4.4 s. |
| ffmpeg 7.1 in the image | Decodes WebM/Opus, Ogg/Opus, MP4/AAC; encodes libopus; 3 independent 20 s segments decode and concatenate to exactly 60.0 s of PCM for all three containers. |
| Truncated files (60 % of bytes) through ffmpeg | WebM/Opus and Ogg/Opus decode the salvageable prefix (12.0 s of 20); **non-fragmented MP4 fails** (`moov atom not found`); fragmented MP4 decodes (11.3 s). |
| `sherpa_onnx` 1.12.29 | Exposes `SileroVadModelConfig`/`VadModel`; **no VAD model shipped in `/models`**; `silero_vad.onnx` is 644 kB from the sherpa-onnx releases. |
| ElevenLabs key stored in the dev database | A key **ID**, not a key: Scribe answers `api_key_id_used_as_api_key`. Same misconfiguration logged for prod on 2026-08-15. The owner must store a real `sk_` key through the admin (DB is the sole source of truth for provider keys). |

### 2.2 Facts read in the code

| Fact | Evidence |
|---|---|
| Local STT accepts up to 60 s per request and silently truncates at ~30 s; WebSocket buffer cap 60 s; voice mode records up to 60 s | `src/core/constants.py` `VOICE_STT_MAX_DURATION_SECONDS_DEFAULT = 60`, `STT_MAX_AUDIO_BYTES = 1920000`; `apps/web/src/lib/constants.ts` `VOICE_MODE_MAX_RECORDING_SECONDS = 60`; `docs/technical/VOICE_MODE.md` documents 60 s. **Latent defect**: a 30–60 s dictation loses its tail without a signal. |
| Remote STT client sends raw PCM only, 60 s timeout, 300 s cap enforced on the WebSocket path only | `src/domains/voice/stt/elevenlabs_stt.py`, `factory.py`, `src/core/config/voice.py` |
| Provider selection per user, audio-billed cost recording (`per_audio_hour` / `per_audio_minute` units exist), usage-limit gate before paid STT | `src/domains/voice/router.py`, `src/infrastructure/cache/pricing_cache.py::get_cached_cost_audio_usd_eur`, `src/domains/llm/models.py` (`pricing_unit`) |
| Pricing seed carries `llm_models` rows (kind `audio`) and pricing rows per model; the vendored catalogue already lists the OpenAI transcription models (`mode=audio_transcription`), but `kind` and prices are LIA-owned (ADR-244) | `infrastructure/database/seeds/llm_pricing_seed.sql`, `src/infrastructure/llm/catalogue/snapshot.json` |
| Attachments accept images + PDF only, 24 h TTL, whole body read in memory (SEC-031) | `src/core/constants.py`, `src/domains/attachments/service.py` |
| RAG ingestion is a durable pipeline reading a file on disk; `text/markdown` allowed; atomic chunk swap; reaper | `src/domains/rag_spaces/processing.py`, `reapers.py` |
| RAG limits: 10 spaces per user, 100 documents per space, unique name per user; document deletion from the space UI is free | `src/core/constants.py`, `apps/web/src/components/spaces/DocumentRow.tsx` |
| PDF rendering is a deterministic pure function over `SectionedContent` | `src/domains/document_generation/renderers.py` |
| Email protocol has no attachment parameter (three providers); client resolution helper | `connectors/clients/protocols.py`, `emails_tools.py::execute_email_draft` (`resolve_client_for_category`) |
| One-call delivery: archived message + FCM + SSE + Telegram, localized title by `task_type`; the chat page appends `proactive_*` payloads live and renders per-type blocks | `infrastructure/proactive/notification.py`, `core/i18n_proactive.py`, `apps/web/src/hooks/useNotifications.ts::routeNotification`, `chat/page.tsx::handleProactiveNotification`, `ChatMessage.tsx` (`PhoneCallDebriefBlock`) |
| LLM cost outside a chat run: `TokenCaptureHandler` + `track_proactive_tokens` | `src/domains/telephony/return_synthesis.py` |
| Structured output chokepoint (AST-guarded) | `src/infrastructure/llm/structured_output.py::get_structured_output_with_retry` |
| New LLM type = registry + defaults + `LLMType` Literal + count guard (57 → 58) + admin i18n + doc counts | `src/domains/llm_config/constants.py`, `tests/unit/domains/llm_config/test_constants.py:46` |
| Browser geolocation shape exists; reverse geocoding exists (Google key); the implicit cascade falls back to HOME | `agents/api/schemas.py::BrowserGeolocation`, `google_geocoding_helpers.py::reverse_geocode`, `location_resolution.py::resolve_implicit_location` |
| Calendar events for a window with minimized fields; provider resolution | `src/domains/telephony/availability.py` |
| Voice mode holds the microphone for wake-word detection | `apps/web/src/hooks/useVoiceMode.ts` |
| Capability machinery: enum + spec + generated setting + router dependency + map node + section pairing + i18n guards (`capabilities.nodes.*`, `capabilities.items.*`) | `domains/feature_switches/registry.py`, `domains/capabilities/service.py`, `apps/web/src/lib/capability-sections.ts`, `tests/unit/domains/capabilities/test_capability_coverage_guard.py` |
| Every table must be classified in the user data map (export policy + data class), guarded | `src/domains/users/user_data_map.py::TABLE_RULES`, `tests/unit/domains/users/test_user_data_map_guard.py`, `tests/unit/domains/account_export/test_export_completeness.py` |
| Models are registered in ONE place | `src/infrastructure/database/registry.py::import_all_models` |
| Public feature flags for the frontend | `src/api/v1/routes.py` (`features`), `apps/web/src/hooks/useAppConfig.ts` |
| Storage volumes are declared per data directory in both compose files | `docker-compose.dev.yml:179`, `docker-compose.prod.yml:185` |
| **Production runs 4 uvicorn workers** | `apps/api/Dockerfile.prod` `WEB_CONCURRENCY=4` — a shared append file is not safe across workers |
| STT model baked into the image by a download stage | `apps/api/Dockerfile.dev`, `Dockerfile.prod`, `scripts/download-whisper-model.sh` |
| Published shells cannot capture the microphone today | Android overlay manifest declares only INTERNET + POST_NOTIFICATIONS; Capacitor's `BridgeWebChromeClient.onPermissionRequest` denies `AUDIO_CAPTURE` without RECORD_AUDIO + MODIFY_AUDIO_SETTINGS (vendor source); iOS overlay `Info.plist` has no `NSMicrophoneUsageDescription`; the probe only checks API presence (`scripts/mobile-probe/page.html:43`) |
| Frontend templates read for compliance: settings section (`BaseSettingsProps`, `SettingsSection value=`, `SETTINGS_SECTIONS` + `SETTINGS_SEARCH_META` + keywords ×6), data hooks (`useApiQuery`/`useApiMutation`), energy VAD helper, slash local commands registry, storage purge registry | `components/settings/HabitsSettings.tsx`, `lib/settings-sections.ts`, `lib/settings-search.ts`, `hooks/useHabits.ts`, `lib/audio/vad.ts`, `lib/chat-local-commands.ts`, `lib/client-storage-purge.ts` |
| Backend templates read for compliance: settings module (constants-backed `Field`s, composed in the `Settings` MRO), migration docstring + revision chain, domain router under the capability guard, `.env.example` block numbering (last block `[86]`), ADR style (French, « Statut / Portée / Voisins », measured defect first), technical doc structure, `docs/INDEX.md` row format | `core/config/telephony.py`, `core/config/__init__.py`, `alembic/versions/2026_08_28_0900-a6b7c8d9e0f1_*.py`, `domains/telephony/router.py`, `.env.example`, `ADR-256`, `docs/technical/TELEPHONY.md`, `docs/INDEX.md` |

### 2.3 External facts (vendor docs and public bug trackers)

| Fact | Source |
|---|---|
| Scribe: files up to 5 GB, all major formats, `diarize` + `num_speakers` (≤ 32), `speaker_id` per word, async `webhook` mode, `language_code` optional | ElevenLabs speech-to-text convert API reference |
| OpenAI transcriptions: **25 MB per request**; formats mp3, mp4, mpeg, mpga, m4a, wav, webm (Ogg accepted in practice, measured); models `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe-diarize` (`diarized_json`, `known_speaker_names`); `chunking_strategy=auto` for the gpt-4o family; prices ≈ 0.006 $/min (transcribe, diarize, whisper-1) and 0.003 $/min (mini) | OpenAI speech-to-text guide, `createTranscription` reference, pricing page |
| WKWebView mutes the microphone when the app is backgrounded, even with background modes declared | WebKit bug 226620; Apple forums 689182, 727009 |
| Android ≥ 9 blocks microphone access for backgrounded apps unless a foreground service of type `microphone` runs | Android 9 behaviour changes; foreground service types |
| Screen Wake Lock: Safari/iOS since 16.4, broken in installed PWAs until iOS 18.4 | web-platform-dx, caniuse |
| MediaRecorder on Safari: `audio/mp4` only before 18.4; WebM/Opus and fragmented MP4 from 18.4 | WebKit blog |
| MediaRecorder in an iOS home-screen PWA: works on first launch, fails on later launches until a phone restart; no Apple fix | Apple forums 797987 |
| WebCodecs `AudioEncoder` absent from Safari 16.4–18.7, available from Safari 26 | MDN |

## 3. Arbitrations

| # | Decision | Rationale |
|---|---|---|
| A1 | **Bounded context `domains/meetings/`**, entity-as-job durability (ADR-129), processing in the API process after the recording stops | A recording lasts an hour, survives reloads and must survive a crash; attachments (24 h TTL, in-memory reads) and chat runs (timeouts, no persistence) were rejected. |
| A2 | **Capture: one pipeline, two audio sources.** `PcmWorkletSource` (the existing 16 kHz int16 AudioWorklet, proven in the PWA by push-to-talk) and `OpusStreamSource` (`MediaRecorder`, `audio/webm;codecs=opus` or `audio/ogg;codecs=opus`, `timeslice`). **iOS always PCM**; elsewhere Opus when `isTypeSupported` says so, PCM otherwise or on any MediaRecorder start error. **Each segment is its own file on the server** (`{seq:06d}`), written atomically (temp + rename), so four uvicorn workers can receive segments of one meeting without an append race and a duplicate upload is a no-op. At finalize, under the job lease, segments are assembled and **normalized once to WebM/Opus** with ffmpeg (PCM encoded; Opus chunks concatenated and remuxed, which drops a truncated tail) | Codec-free capture where the platform is fragile, eight times less upload where it is not; both salvage paths validated; both providers accept WebM (measured). |
| A3 | **Transcription engine chain, user preference `auto` / `remote` / `local`, default `auto`**: ElevenLabs Scribe when a valid key exists → **OpenAI transcription** when an OpenAI provider key exists (`gpt-4o-transcribe-diarize` for speakers, `gpt-4o-mini-transcribe` otherwise) → local VAD-windowed Whisper. The admin `voice_transcription` slot keeps naming the preferred remote model; per-provider default models live in constants. **Never a silent engine switch after the start**: the engine is resolved and shown to the user before recording | Most self-hosters have an OpenAI key even without ElevenLabs; live probes show both remote engines transcribe 7 of 7 sentinels in seconds, while local stays free but slow. The fallback "holds up" because it is a real provider, not a degraded mode. |
| A4 | **Audio deleted after successful processing** unless the user opts to keep it (bounded by an admin ceiling). **Transcript kept, encrypted at rest** (`encrypt_data`), deletable on its own. Only the minutes are indexed | The transcript enables regeneration with a new template; it is third parties' speech, hence Fernet like `callee_phone`. |
| A5 | **Email v1 = HTML body rendered from the minutes + link**; PDF downloaded from the app | The email protocol has no attachment parameter for any of the three providers. |
| A6 | **The « Réunions » space is found by role**: nullable `rag_spaces.kind` ('meetings'), created on demand with a localized default name, renamable, exempt from the 10-spaces and 100-documents caps. Minutes are `rag_documents` with `source_type='meeting'`; `meetings.rag_document_id` is a `SET NULL` FK | Name lookup breaks on rename and localization; the caps were sized for uploads. |
| A7 | **Surfaces**: paperclip menu; recording chip in the composer and a slim banner elsewhere; `/dashboard/meetings` and `/dashboard/meetings/[id]`; « Réunions » settings section with template editor; chat card `proactive_meeting`; `/meetings` local slash command; read tool on `document_agent` | The minutes are long-lived and editable: a page, not a chat draft; the chat still announces it. |
| A8 | **Mobile v1 = foreground recording with Screen Wake Lock** and explicit notice; native background capture is a later lot. Shell microphone permissions fixed in Lot 0 | Measured platform limits. |
| A9 | **The 30 s truncation is fixed in this programme** by one shared helper used by the WebSocket path (buffers over 25 s) and by the local meeting pipeline; Silero VAD shipped in the image | One implementation, two consumers. |
| A10 | **Template = `meeting_templates` rows** (one per user in v1), sections validated by Pydantic, default in code with localized labels, snapshot stored per meeting | Deterministic reset; old minutes keep rendering; the library is one migration away. |
| A11 | **No new agent or taxonomy domain**: the read tool joins `document_agent` | Minutes are user documents; a new domain costs catalogue slots. |
| A12 | **Demonstrator**: `MEETINGS_ENABLED=false`; no Caddy prefix | Recording costs money for anonymous visitors. |
| A13 | **A forgotten recording ends itself honestly**: a client-side silence watchdog (AnalyserNode RMS on the captured stream, same threshold family as `lib/audio/vad.ts`) asks « Toujours en réunion ? » after `MEETING_SILENCE_PROMPT_MINUTES` (10) and stops with a countdown when unanswered; the server enforces `meetings_max_duration_minutes`; a dead client is caught by the stale-recording reaper | Three independent guards for three failure shapes: user distracted, user gone, client gone. |
| A14 | **Chat and recording are independent**: the composer keeps sending messages while recording (attachments through the same menu), push-to-talk is not offered, wake word is suspended, spoken answers are muted so the microphone never captures LIA | The user records a meeting; LIA stays usable and never pollutes the capture. |

## 4. Architecture

```mermaid
flowchart LR
  subgraph Browser["PWA / browser / shells"]
    Menu[Paperclip menu] --> Rec[MeetingRecorder store + provider]
    Rec --> Src{{AudioSegmentSource<br/>PCM worklet | Opus MediaRecorder}}
    Src --> Q[Segment queue<br/>sequence, retry, offline hold]
    Q -->|PUT segments| API
    Rec -->|wake lock, visibility, track events,<br/>silence watchdog| Rec
    Rec -->|POST stop| API
  end
  subgraph API["FastAPI domains/meetings — 4 workers"]
    API[Router] --> Svc[MeetingService]
    Svc --> Seg[(segments/000001.bin …<br/>atomic per-file writes)]
    Svc --> DB[(meetings, meeting_templates,<br/>meeting_preferences)]
    Job[processing job — lease, heartbeat,<br/>attempts, single worker] --> Norm[normalize → audio.webm]
    Norm --> STT{{Scribe | OpenAI | local VAD+Whisper}}
    Job --> LLM[meeting_synthesis<br/>structured output]
    Job --> RAG[rag_documents source_type=meeting<br/>existing process_document]
    Job --> Notif[NotificationDispatcher]
    Reaper[reapers: stale recording,<br/>stuck job, audio retention] --> DB
  end
  subgraph Outputs
    Page[/dashboard/meetings/[id]/]
    PDF[GET …/pdf on demand]
    Mail[POST …/email HTML body]
    Chat[proactive_meeting card]
  end
  Notif --> Chat
  DB --> Page
  Page --> PDF
  Page --> Mail
```

### 4.1 State machine

```
recording ──stop──▶ stopped ──claim──▶ processing ──▶ ready
    │                  ▲                   │
    │ (no segment for  │ retry             ├─▶ failed (dead-letter after attempts, or permanent cause)
    ▼  N minutes)      │                   │
interrupted ──finalize─┘         stages: normalizing → transcribing → synthesizing → indexing
    │
    └─discard──▶ deleted
```

- `recording`: segments arrive; each upload is the heartbeat. A segment arriving while `interrupted` flips the row back to `recording` (a long outage is a gap, not a failure).
- `stopped`: all segments known; the job claims it atomically. Refused claims (usage limit, no engine available) leave the row `stopped` with a `last_error` code the UI explains; the user retries later.
- `processing`: lease + heartbeat before each slow step; `stage` for the UI. Transient failures return to `stopped` up to `meetings_job_max_attempts`; permanent causes (no speech, undecodable audio, transcript over the model window) go to `failed`.
- `ready`: minutes present; `index_state` ∈ {`indexed`, `pending`, `error`, `disabled`}.
- `interrupted`: no segment for `meetings_recording_stale_minutes` (5). Finalize (→ `stopped`) or discard.
- Exactly one `recording` meeting per user: partial unique index on `(user_id) WHERE status = 'RECORDING'` (uppercase member names, `native_enum=False`).

### 4.2 Data model (one Alembic migration, replay-checked)

`meetings`
- `user_id` FK CASCADE, `status` Enum(native_enum=False), `stage`, `audio_format` (`pcm_s16le_16` | `webm_opus` | `ogg_opus`), `segment_count`, `audio_bytes`, `audio_duration_seconds`, `audio_path` (nullable, relative to the meetings storage root), `audio_purged_at`
- `started_at`, `stopped_at`, `client_timezone`, `location_lat`, `location_lon`, `location_accuracy_m`, `location_label`
- `stt_provider` (`elevenlabs` | `openai` | `local`), `stt_model`, `stt_language_hint`, `stt_detected_language`, `stt_cost_eur`, `stt_audio_seconds`, `stt_diarized` (bool)
- `transcript_encrypted` (Text, Fernet of JSON turns `[{speaker, start, end, text}]`), `transcript_deleted_at`
- `calendar_event_id`, `calendar_provider`
- `template_snapshot` JSONB, `report_generated` JSONB (immutable), `report_current` JSONB, `report_edited_at`
- `rag_document_id` FK `rag_documents.id` ON DELETE SET NULL, `index_state`, `indexed_at`
- `email_sent_at`, `last_error` (code + safe message), durable-job columns `lease_expires_at`, `heartbeat_at`, `attempts`, `worker_id`
- Indexes: `(user_id, started_at desc)`, `(status, lease_expires_at)`, partial unique active-recording index.

`meeting_templates`: `user_id` FK CASCADE, `name`, `sections` JSONB (`[{key, label, instruction, kind}]`), `is_default` (one per user, partial unique), `source` (`user`), timestamps.

`meeting_preferences` (1:1): `user_id` unique FK CASCADE, `stt_engine` (`auto` | `remote` | `local`), `language` (`auto` | ISO), `auto_email` (bool), `keep_audio` (bool), timestamps.

`rag_spaces.kind` (String(30), nullable) + partial unique `(user_id, kind) WHERE kind IS NOT NULL`. `RAGDocumentSourceType.MEETING = "meeting"` (string column, no DDL).

All three tables are declared in `user_data_map.py::TABLE_RULES` (`USER_PURGED`, FULL export) with `transcript_encrypted` in `_DECRYPTED_COLUMNS`; models imported in `registry.py::import_all_models`.

Report JSON (Pydantic, validated on write and read):

```
MeetingReport
  title: str
  participants: [ {label: "S1", name: str|None, role: str|None} ]
  sections: [ {key, label, kind, paragraph: str|None, bullets: [str], topics: [{title, summary}],
               action_items: [{description, owner: str|None, due_date: str|None}]} ]
```

Section kinds v1: `paragraph`, `bullets`, `topics`, `action_items`, with a renderer registry keyed by kind and a boot-time completeness assert (ADR-085). Header fields (date, times, duration, location, participants, title) are not template-driven. Default template (labels from `core/i18n_meetings.py`, six languages): `summary`, `topics`, `decisions`, `action_items`, `risks`, `open_questions`.

### 4.3 Backend modules (planned)

`src/domains/meetings/` — `models.py`, `schemas.py`, `repository.py` (`MeetingRepository(BaseRepository[Meeting])` + atomic claim/heartbeat/complete/fail), `service.py`, `audio_store.py` (path containment, per-segment atomic writes, assembly + normalization via `asyncio.create_subprocess_exec("ffmpeg", …)`, retention purge — never pydub in memory), `transcription.py` (engine chain resolution, provider dispatch, transcript turns from words or segments), `synthesis.py`, `render.py` (report → Markdown → `SectionedContent` → HTML: ONE serializer), `indexing.py`, `templates.py`, `reapers.py`, `router.py`, `prompts.py` (path loader, no `agents` import).

`src/domains/voice/stt/`:
- `long_audio.py` — Silero VAD + VAD-aligned windows ≤ `voice_stt_window_seconds` (20); used by `SherpaSttService.transcribe_pcm_int16_async` above `voice_stt_single_pass_max_seconds` (25) and by the local meeting engine.
- `protocol.py` — new `transcribe_file_async(path, mime_type, *, diarize, language, timeout) -> STTFileResult(text, turns, language_code, duration)`.
- `elevenlabs_stt.py` — file method (`diarize`, `num_speakers`, word `speaker_id` → turns).
- `openai_stt.py` (new) — file method against `/v1/audio/transcriptions`; `gpt-4o-transcribe-diarize` + `diarized_json` when speakers are wanted, `gpt-4o-mini-transcribe` otherwise; `chunking_strategy=auto`; PCM method for parity with the WebSocket path (WAV header wrap). **Single-file guarantee**: the normalizer picks the Opus bitrate so the whole meeting stays under 25 MB (32 kbps down to a 16 kbps floor), which holds up to ~210 min; `meetings_max_duration_minutes` is bounded `le=210` with that reason written next to it.
- `factory.py` — provider registry `{elevenlabs, openai}` with `STT_PROVIDER_DEFAULT_MODELS` in constants; the `voice_transcription` slot names the preferred remote model; the WebSocket path gains OpenAI as a possible remote provider for free.

Seeds and catalogue: `llm_models` rows for `gpt-4o-transcribe-diarize` and `gpt-4o-mini-transcribe` (kind `audio`, all chat capabilities false, provenance as the seed convention requires) and `llm_model_pricing` rows `per_audio_minute` (0.006 / 0.003 USD); `get_cached_cost_audio_usd_eur` already handles the unit.

`src/domains/agents/tools/meetings_tools.py` — `get_meeting_reports_tool` (`@read_tool`, agent `document_agent`): optional `meeting_id`, `date_from`/`date_to`, `limit` with a published bound; exact totals (ADR-185); registered through `program_manifests.py` when `meetings_enabled`; `document` domain description extended to minutes.

Config: `src/core/config/meetings.py` in the `Settings` MRO; constants in `core/constants.py`; `.env.example` + `.env.prod.example` block `[87] MEETINGS`. Settings: `meetings_enabled=true`, `meetings_storage_path=/app/data/meetings`, `meetings_max_duration_minutes=180 (le=210)`, `meetings_segment_seconds=30`, `meetings_segment_max_bytes` (derived from the cap and format), `meetings_recording_stale_minutes=5`, `meetings_silence_prompt_minutes=10`, `meetings_job_lease_ttl_seconds`, `meetings_job_heartbeat_interval_seconds` (validator heartbeat < lease), `meetings_job_max_attempts=3`, `meetings_reaper_interval_seconds`, `meetings_audio_retention_hours_max=168`, `meetings_stt_timeout_seconds=900`, `meetings_local_rtf_estimate=1.5`, `meetings_rate_limit_*`. Volume `meetings_data:/app/data/meetings` in both compose files.

LLM: type `meeting_synthesis` (structured_output, power tier high, default `openai/gpt-4.1`, `max_tokens` 8000, timeout 180 s); prompt `prompts/v1/meeting_synthesis_prompt.txt` (static system) + f-string HumanMessage context (transcript braces).

Capability: `PlatformCapability.MEETINGS` (`env_flag="meetings_enabled"`, `SystemSettingKey.CAPABILITY_MEETINGS_ENABLED`, `route_enforced=True`), counted map node `meetings`, section pairing `meetings → 'meetings'`, i18n `capabilities.items.meetings(_description)` + `capabilities.nodes.meetings` ×6.

Observability: `meetings_total{status}`, `meeting_recording_duration_seconds`, `meeting_segments_received_total{format}`, `meeting_processing_stage_duration_seconds{stage}`, `meeting_failures_total{reason}`, `meeting_reaper_transitions_total{outcome}`, `meeting_stt_audio_seconds_total{provider}` — all wired in `27-meetings.json` with `or vector(0)` on rare-failure panels. Logs: counts, ids, durations and codes at INFO; never a title, a participant or transcript text.

### 4.4 API (planned, `/api/v1/meetings`, session cookie, capability-guarded)

| Method | Path | Purpose |
|---|---|---|
| POST | `/meetings` | Start: `{audio_format, language, timezone, geolocation?}` → 201 `{id, segment_seconds, max_duration_minutes, engine: {provider, model, diarized, cost_per_hour_eur|null, local_eta_factor|null}}`; 409 `meeting_already_recording`; 429 when usage limits block (synthesis is paid whatever the engine); 409 `no_engine_available` only when even local is disabled |
| GET | `/meetings/active` | The recording or interrupted meeting of this user, or 204 |
| PUT | `/meetings/{id}/segments/{sequence}` | Raw body (`application/octet-stream`), `Content-Length` required and bounded, streaming counter, atomic file write; idempotent; 413 beyond the duration cap (client auto-stops); 409 unless recording/interrupted; 507 on storage failure (client backs off) |
| POST | `/meetings/{id}/stop` | `{segment_count, allow_gaps=false}` → 202; 409 `segments_missing` with the list |
| POST | `/meetings/{id}/resume` | interrupted → recording |
| POST | `/meetings/{id}/retry` | stopped/failed with audio present → requeue |
| POST | `/meetings/{id}/regenerate` | with transcript present → re-synthesize with the current template |
| GET | `/meetings` | Paginated list with exact total |
| GET | `/meetings/{id}` | Detail; `?include_transcript=1` decrypts on demand |
| PATCH | `/meetings/{id}` | Title, participants, sections, location label → re-render + re-index |
| POST | `/meetings/{id}/report/reset` | `report_current ← report_generated` |
| DELETE | `/meetings/{id}/transcript` | Purge the transcript only |
| DELETE | `/meetings/{id}` | Everything (RAG document + chunks + files) |
| GET | `/meetings/{id}/pdf` | Streamed inline A4 built on demand |
| POST | `/meetings/{id}/email` | To `user.email` via the active email connector; 409 `email_connector_missing` |
| GET/PUT/DELETE | `/meetings/template` | Read (default when no row), replace (validated), reset |
| GET/PUT | `/meetings/preferences` | Engine, language, auto-email, keep-audio |

`NEXT_PUBLIC_API_URL` already carries multipart uploads to the API directly (attachments); segments use the same transport.

### 4.5 Processing pipeline (single worker, under the lease)

1. **Claim** (`stopped → processing`). Usage-limit check; engine chain resolution; refusal releases with a code.
2. **Normalizing**: assemble segments in sequence order; PCM → WebM/Opus at a bitrate keeping the file under 25 MB; Opus chunks → concatenation + `-c copy` remux; `audio.webm` becomes the stored artifact; duration measured; segments removed.
3. **Transcribing**: Scribe or OpenAI file call (turns from `speaker_id` words or `diarized_json` segments); local → decode to PCM, VAD windows through the STT executor, one heartbeat per window, no speakers. Empty transcript → `failed(no_speech)`.
4. **Enrichment** (best-effort, own session and failure boundary each): calendar event with the largest overlap on `[started_at − 15 min, stopped_at + 15 min]` (title suggestion, attendee names as candidates, location if none); reverse geocoding of the captured position.
5. **Synthesizing**: token estimate vs the model window → `failed(transcript_too_long)` rather than truncation; structured output; repair against the template (missing → empty, unknown → dropped, kind mismatch → converted); usage tracked with `track_proactive_tokens(task_type="meeting")`.
6. **Indexing**: get-or-create the `meetings` space; write `YYYY-MM-DD — <title>.md` (the filename is what retrieval cites); create or requeue the `rag_documents` row; fire `process_document`; `index_state=disabled` when RAG spaces are off.
7. **Complete**: atomic conditional UPDATE to `ready`; audio purged unless kept; `NotificationDispatcher.dispatch(task_type="meeting", …)`; `auto_email` if set.
8. **Failure**: transient → `stopped` with attempts+1; dead-letter → `failed` with a reason code; audio stays for retry until retention.

### 4.6 Frontend (planned)

- `stores/meetingRecorderStore.ts` (zustand): `{status, meetingId, startedAt, elapsed, format, pendingSegments, pendingStop, lastError}`; only `meetingId`/`startedAt` persisted (key in `client-storage-purge`).
- `lib/audio/pcm-worklet.ts`: worklet source extracted from `useVoiceInput` and shared.
- `lib/meetings/sources.ts`: `AudioSegmentSource`, `PcmWorkletSource`, `OpusStreamSource`, `selectSource()`.
- `lib/meetings/segment-uploader.ts` (allowlisted binary transport like `attachment-blob`): ordered queue, retries with backoff, offline hold (30 min cap with warning), `413` → stop, `409` → refresh, `507` → back off.
- `lib/meetings/silence-watchdog.ts`: AnalyserNode RMS on the stream, prompt after 10 min of silence, countdown stop.
- `lib/wake-lock.ts`: request on start, re-request on `visibilitychange`, release on stop, hint when unsupported.
- `hooks/useMeetingRecorder.ts`: start (usage/engine preflight → permission → source → wake lock → suspend voice mode → mute TTS), stop (flush → `stop` → poll; `pendingStop` kept offline), resume after reload (`GET /meetings/active`), `track.onended`/`onmute` re-acquire once then interrupted UI, `AudioContext` `interrupted` → auto-resume with a gap, `pagehide`.
- `components/meetings/MeetingRecorderProvider.tsx` mounted in `dashboard/layout.tsx`.
- `ChatInput`: paperclip → `DropdownMenu` (attach a file / start a meeting recording); the slot shows the chip while recording (pulsing dot, elapsed time, stop; `aria-live` only on state changes, never per second). `isPttOffered` gains `!recording`; `voiceModeStore.isSuspended` honoured by `useVoiceMode`; spoken answers muted while recording.
- `MeetingRecordingBanner` (slim, sticky) on other dashboard pages.
- Pages: `dashboard/meetings` (list, `lifecycleTone` badges, exact total, `EmptyState variant="page"` with the start action), `dashboard/meetings/[id]` (header, participant chips with rename, sections in template order with per-field editing and explicit save, actions: email, PDF, regenerate, reset to generated, delete transcript, delete).
- Settings `MeetingsSettings` (token `meetings`, tab features, search meta + keywords ×6): engine with cost and speed honesty, language, keep-audio, auto-email, template editor (label, instruction, kind, up/down, add, remove, reset with confirm).
- Chat `MeetingReportCard` for `proactive_meeting`; slash local command `meetings`; `features.meetings_enabled`.
- Start dialog: engine and cost per hour (or the local ETA factor), language, « inform participants », « keep the screen on », data volume line (PCM ≈ 115 MB/h, Opus ≈ 15–30 MB/h).

## 5. Edge cases and their handling

| Case | Handling |
|---|---|
| Two devices or tabs start recording | Second start → 409 (partial unique index); a page that finds a live meeting it did not start adopts it as `interrupted` (finalize or discard from there); resuming it is allowed only when this browser produces the SAME container (`format_unavailable` otherwise — an Opus meeting cannot continue with PCM segments); the recording tab gets 409 on its next segment and stops locally. |
| **User forgets to stop** | Silence watchdog prompt after `MEETINGS_SILENCE_PROMPT_MINUTES` of silence; the client finalizes at `MEETINGS_MAX_DURATION_MINUTES`; a throttled tab that misses it gets 413 `duration_cap_reached` on the extra segment and the uploader turns it into a STOP declaring the sequences the server holds (no invented gap — tested); if the client died, the reaper marks `interrupted` after 5 min and the user finalizes what exists. |
| **User chats with LIA while recording** | Allowed: text messages, attachments through the menu, follow-up chips; push-to-talk not offered; wake word suspended; spoken answers muted so the microphone never hears LIA; the report card later lands in the same conversation. |
| **Proactive notifications during recording** | They arrive as usual (toast + archived message); none plays audio while recording; no interference with capture. |
| Page reload or crash while recording | Segments already uploaded are safe; the store remembers the id; on load, `GET /meetings/active` offers Resume / Finalize / Discard. Loss bounded to one segment (≤ 30 s). |
| **Network loss** | Segments queue and retry (never dropped while the page lives); the server marks `interrupted` after 5 min; the next upload flips it back; a stop while offline closes the capture and leaves the meeting `interrupted` with its queue draining (Finalize once online); the banner warns past 30 min of unsent audio. |
| Screen lock or app background on a phone | Wake lock prevents the nominal case; if capture stops anyway, events mark a gap and the UI asks to resume. |
| Incoming phone call, Bluetooth headset change | `AudioContext` interruption / `track.onended`: one automatic re-acquire, gap recorded; otherwise `interrupted` UI. |
| Microphone permission denied or revoked | Start refused with a localized reason; revocation → `interrupted` with a gap. |
| Very short recording or silence | Stop offers Discard; processing on silence → `failed(no_speech)`. |
| Duration cap reached | Client-side at the published cap; server-side 413 → stop with the settled count (see « forgets to stop »); the cap travels in `limits`. |
| Missing segments at stop | 409 with the list → retries; if blobs are gone, « finalize with gaps ». |
| **No ElevenLabs key** | Chain falls to OpenAI (measured: 7 of 7 sentinels, diarization available), then local; the engine is shown before recording. |
| Key ID stored instead of a key, kill switch, 429/5xx | Explicit codes (`invalid_api_key`, `provider_rate_limited`…); a PERMANENT fault of one provider walks the chain to the next engine at processing time (`transcribe_with_fallback`, logged `meeting_engine_fallback`, the actual `stt_provider` is stored); transient faults use the bounded retry; measured 2026-09-03 on the dev key ID. |
| **Server disk full** | Segment write fails → 507; client backs off and keeps its queue; storage metric; recording continues client-side up to the queue cap. |
| **Four API workers** | Per-segment files and a single lease-holding worker at finalize; no shared append. |
| Local engine on a slow server | ETA from `meetings_local_rtf_estimate`, progress by window; live push-to-talk keeps three executor workers. |
| Model without an administered price | The pricing cache answers (0, 0) for a model it does not know: the outcome stores `null`, never `0.0` — an unknown price is not a free one (measured 2026-09-03 on the dev instance before its pricing seed was applied). The local engine stores an exact `0.0`. |
| Notification or indexing fails after `ready` | `_after_ready_guarded`: logged and counted (`meeting_failures_total{reason="after_ready"}`), the READY row is never re-classified as failed. |
| Transcript over the model window | Condensed part by part (`meeting_condense_prompt`) before the structured call — a 128k model still produces minutes for a three-hour meeting (implemented, tested). |
| Meeting in another language | Remote auto-detects unless chosen; local uses the user language unless chosen; minutes in the user's language; detected language stored. |
| Location denied | No location; never the home address. |
| Overlapping calendar events | Largest overlap as a suggestion; attendees are candidates, never asserted. |
| Template edited later | Old minutes render from their snapshot; regenerate applies the new template. |
| Meeting deleted | Its RAG document goes first (chunks, row, file through `RAGSpaceService.delete_document`), then the row and the audio: no projection outlives the minutes (the proof found three orphans before this rule). |
| RAG space renamed / deactivated / deleted; document deleted from the space | Found by `kind`; deactivated → not retrieved; deleted → recreated on next index; document deleted → `SET NULL`, page shows « not indexed » with re-index. |
| RAG spaces disabled | `index_state=disabled`, stated. |
| **Admin disables the capability mid-recording** | 403 on the next segment → client stops with an explanation; reaper marks `interrupted`; finalize once re-enabled. |
| Admin changes the STT model or key while a job waits | Resolution happens at claim time; retries use the current configuration. |
| Usage limits reached | Start refused; a stopped meeting waits with `usage_limit`. |
| Costs and re-billing | Two paid units, both booked like any exchange: audio via the remote-STT statistics, tokens via `track_proactive_tokens` under the archived message's `run_id` (regenerations included); the row keeps the minutes' spend, the page states the exact total with its breakdown, the chat card states both units and their sum when the user displays costs; an unpriced model yields `null`, never zero. |
| Header and composer | « Meetings » is a dashboard destination (between Relations and Alerts, gated on the instance flag); the composer's control is a « + » (actions, of which a file is one), 44 px wide on a phone, 40 px beyond; the language control shows its flag alone and the personality title waits for `2xl` so seven labels fit. |
| Email connector absent | Action disabled with the reason; auto-email skipped with a stated state. |
| Time zone travel, DST | UTC stored; header rendered in the timezone captured at start. |
| Account deletion / GDPR export | FK cascade; files removed; export covers the three tables (transcript decrypted) and kept audio. |
| API crash mid-processing | Lease expiry → reaper requeue; atomic updates; no partial `ready`. |
| Demonstrator | Feature off; the menu shows only « attach a file ». |

## 6. Template compliance checklist (CLAUDE.md runtime integration points)

| Point | Where it lands |
|---|---|
| Config composition | `core/config/meetings.py` in the `Settings` MRO; `MEETINGS_ENABLED`; `.env.example` + `.env.prod.example` block `[87]` (no inline comment on empty values) |
| Constants | `core/constants.py` (defaults, job names, provider default models, bitrate floor) |
| Model registration | `registry.py::import_all_models` (single point) |
| Migration | one file, docstring in the house style, revision chain, `task db:migrate:replay-check` |
| Router wiring | `api/v1/routes.py` under `if getattr(settings, "meetings_enabled", False)`; router carries `capability_dependencies(PlatformCapability.MEETINGS)` |
| Startup | nothing beyond schedulers; reapers with `jitter_seconds_for` and job ids from constants |
| Prompt files | `prompts/v1/meeting_synthesis_prompt.txt`, `PromptName` Literal, domain path loader |
| LangGraph wiring | read tool manifest registered through `program_manifests.py`; registry smoke test entry |
| Frontend API | `hooks/useMeetings.ts`, `useMeetingTemplate.ts`, `useMeetingPreferences.ts` on `useApiQuery`/`useApiMutation`; pages under `app/[lng]/dashboard/meetings` |
| i18n | `meetings.*` keys ×6 (zh `_one` duplicated), backend `core/i18n_meetings.py` ×6, `ProactiveMessages._TITLES["meeting"]`, admin LLM type label, capability labels |
| Observability | structlog events, metrics + dashboard, ratchet baseline untouched |
| Exceptions | `raise_*` helpers in the domain (`BaseAPIException`), error codes in the API contract |
| Dependencies | none new (ffmpeg, sherpa-onnx, PyMuPDF, httpx already present) |
| Middleware and security | ownership checks on every meeting access (`hide_existence=True`), rate limit on start, bounded bodies, path containment, PII encryption |
| Documentation | ADR-258, `docs/technical/MEETINGS.md`, `docs/INDEX.md` row, `ADR_INDEX.md`, `VOICE_MODE.md` correction, mobile guides, release surfaces at release time |
| Data map | `TABLE_RULES` entries + decrypted column; export files directory |

## 7. Action plan

**Lot 0 — Prerequisites**: shell microphone permissions (Android manifest overlay, iOS `Info.plist`), probe page real capture check; Silero VAD shipped (script + both Dockerfiles), `long_audio.py`, WebSocket path fixed, `VOICE_MODE.md` corrected, regression test on a synthetic 45 s buffer. Owner action: store a real `sk_` ElevenLabs key through the admin in dev and prod.

**Lot 1 — Backend foundation**: settings, constants, env blocks, volume; models + migration + data-map rules; repository; service (start/segment/stop/resume/discard); audio store; router; capability; features flag; reapers; metrics + dashboard; ADR-258; `MEETINGS.md`.

**Lot 2 — Transcription and synthesis**: protocol file method; ElevenLabs and OpenAI file clients (+ PCM parity); provider registry and chain; seeds (models + pricing); local engine on `long_audio`; normalization; LLM type (+ count guard 58, admin i18n, doc counts); prompt; report models + repair; token tracking; enrichment; processing job; retry/regenerate.

**Lot 3 — Outputs**: `rag_spaces.kind` + get-or-create + exemptions + `source_type=meeting` (backend + frontend badge); single serializer; PDF; email; dispatcher `task_type="meeting"` + title i18n; read tool + manifest + smoke; GDPR export.

**Lot 4 — Frontend**: shared PCM worklet; sources, uploader, silence watchdog, wake lock, recorder hook, store, provider; paperclip menu, chip, banner, start dialog; voice-mode suspension and TTS mute; list and editor pages; settings section with template editor; chat card; slash command; i18n ×6; tests.

**Lot 5 — Governance and proof**: Docker runtime proof from a real browser (both sources, both remote engines with the dev keys, local engine); device protocol (Android Chrome PWA, iOS Safari PWA, both shells after Lot 0) recorded in the guides; `task meetings:probe:stt` for the Pi RTF; release surfaces at release time; optional timeline kind `meeting_report`.

Dependencies: 2 needs 1; 3 needs 2; 4 starts once the API contract of 1 is frozen; 0 is independent and ships first.

## 8. Test plan (enriched during implementation, executed again at review)

**Unit (backend)** — state machine transitions including refused claims, idempotent segments and gap handling; path containment; segment atomic write and assembly order; bitrate selection under the 25 MB bound; normalization subprocess arguments; engine chain matrix (preference × keys × kill switch × local availability); Scribe words → turns and OpenAI segments → turns; `long_audio` windows (never over the cap, cut on silences); report validation and repair; template validation, default and reset; single serializer round trip; cost recording calls (audio unit per provider); dispatcher payload; PDF bytes start with `%PDF`; email HTML escaping; read tool bounds and exact totals; capability spec/node/pairing/i18n guards; LLM count guard; prompt hygiene; metrics coverage ratchet; env example guards; data-map guards; file-size and complexity ratchets.

**Integration (real PostgreSQL)** — exclusive claim under two workers; heartbeat keeps the lease; crash mid-processing → reaper requeue → `ready` once; bounded retries → `failed`; stale recording → `interrupted` → resume; partial unique active index; `SET NULL` on RAG document deletion; user-deletion cascade; `rag_spaces.kind` uniqueness.

**Agents** — routing of minutes questions to the `document` domain; the read tool through the registry smoke test.

**Frontend** — sources with `MediaRecorder` and worklet doubles honouring public signatures; uploader ordering, retry, offline hold, 413/409/507 behaviours; recorder hook transitions incl. reload recovery, permission denial, interruption re-acquire, silence prompt and countdown; wake-lock helper; `ChatInput` menu and chip accessible names in en and fr, PTT not offered while recording; voice-mode suspension and TTS mute; pages (skeleton vs `aria-busy`, `EmptyState` action, per-field save, reset, participant rename); template editor; `MeetingReportCard` incl. malformed metadata; i18n parity ×6; source ratchets; coverage thresholds.

**Runtime and device proof** — API boot with the flag on and off; complete dev run from a browser for PCM and Opus sources and for each engine (Scribe, OpenAI, local) producing `ready` minutes, a READY RAG document, a PDF, an email through a mocked provider and a chat card; Android Chrome PWA and iOS Safari PWA on real devices; shells after Lot 0; Pi RTF measurement.

### 8.1 Executed 2026-09-03 (dev containers, HTTP contract driven by `meetings_e2e_proof.py`)

| Run | Source → engine | Result |
|---|---|---|
| 1 | PCM 53 s (two synthetic voices, French) → `auto` | ElevenLabs refused the stored key ID → **fallback to OpenAI `gpt-4o-transcribe-diarize`** (diarized, `fr`, 6 turns) → `ready` in 37 s; minutes with title, 2 named participants, summary, topics, decisions, 3 dated actions, risks, open questions; RAG document indexed; audio purged (retention 0); PDF 132 kB (`%PDF-`); email 409 `email_connector_missing` (no connector on the proof account); patch/reset round trip; regenerate 202 → new minutes; transcript delete → regenerate 409 `transcript_unavailable`; delete 204 → 404. |
| 2 | WebM/Opus 53 s → `local` | Sherpa Whisper (no speaker separation, 1 turn) → `ready` in 24 s; same downstream steps green; the « Réunions » space holds one document per meeting. |
| 3 | Same as 1 after the fixes below | Confirmed the RETURNING ack and the fresh re-read; the cost stayed `null` because the API's pricing snapshot predated the seed. |
| 4 | Same as 1, pricing snapshot rebuilt | Confirmed the priced cost and that deleting the meeting deletes its projection; the proof user's leftovers were then removed through the API. |

Defects the proofs found (none was visible to the unit suites): the segment ack and the stop answer read the identity map after a bulk UPDATE (stale `status: recording`) → `RETURNING` + `expire_all()`; a permanent fault of the first provider dead-lettered the meeting → `transcribe_with_fallback`; an unpriced model stored `0.0` → `null`; a deleted meeting left its RAG projection (three orphaned `ready` documents behind three deleted meetings) → `MeetingService._delete_projection`; the proof script itself crashed on a bytes payload (its own bug). Not executed: Scribe with a real key (the owner must store a `sk_` key), the browser device protocol (Android Chrome PWA, iOS Safari PWA), the Pi RTF probe.

Suites at the end of the review pass: backend `tests/unit/domains/meetings` + `tests/unit/domains/voice` **252 passed**; frontend recorder suites (controller, uploader, store, banner, composer, provider) plus the detail page (fifteen journeys: skeleton, not found, processing, failure with retry, facts, edit/save, cancel, restore, declined confirmation, disabled rebuild, email refusal code, transcript show/delete, delete) and the read-only view (a blank bullet is skipped, as in every other renderer — found by the test) green; full gates recorded in the final report.

## 9. Deliberately not in v1 (documented follow-ups)

Native background capture in the shells; template library and per-meeting format choice; PDF as email attachment; client-side Opus via WebCodecs `AudioEncoder`; live transcription; map-reduce synthesis beyond the model window; speaker identification against contacts (OpenAI `known_speaker_references` is a candidate); timeline entry (optional in Lot 5); Scribe async webhook mode if synchronous calls ever time out on long files.
