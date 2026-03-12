# Voice Mode - Architecture Complète

> Système de saisie vocale avec Wake Word Detection, Push-to-Talk, VAD et STT
>
> **Version**: 1.0
> **Date**: 2026-02-02

## Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Composants Frontend](#composants-frontend)
- [Composants Backend](#composants-backend)
- [Wake Word Detection](#wake-word-detection)
- [Voice Activity Detection](#voice-activity-detection)
- [Speech-to-Text (STT)](#speech-to-text-stt)
- [Configuration](#configuration)
- [Sécurité](#sécurité)
- [Métriques](#métriques)
- [Dépannage](#dépannage)

---

## Vue d'Ensemble

Le Voice Mode de LIA est un système complet de saisie vocale avec :

| Fonctionnalité | Description | Technologie |
|----------------|-------------|-------------|
| **Wake Word** | Activation par "OK" / "OK Guy" | Sherpa-onnx WASM (Whisper tiny) |
| **Push-to-Talk** | Activation manuelle par clic/tap | Web Audio API |
| **VAD** | Détection fin de parole automatique | Energy-based detection |
| **STT** | Transcription multilingue | Sherpa-onnx Whisper Small (backend) |
| **TTS** | Synthèse vocale des réponses | Edge TTS / OpenAI HD |

### Machine d'États

```
idle → listening → recording → processing → speaking → listening
  │        │           │            │            │
  │        │           │            └────────────┘
  │        │           └────(VAD silence 1s)─────┘
  │        └────(wake word "OK")──────┘
  └────(enable voice mode)────┘
```

---

## Architecture

### Stack Complète

```
┌─────────────────────────────────────────────────────────────────┐
│                       FRONTEND (Next.js)                         │
├─────────────────────────────────────────────────────────────────┤
│  UI Layer                                                        │
│  ├── VoiceOverlay.tsx      Overlay fullscreen, états visuels    │
│  └── VoiceModeBadge.tsx    Badge compact, long-press activation │
│                                                                  │
│  Hooks Layer                                                     │
│  ├── useVoiceMode.ts       Orchestration principale (830 lines) │
│  ├── useSherpaKws.ts       Hook React pour KWS WASM             │
│  └── useVAD.ts             Hook React pour VAD                  │
│                                                                  │
│  Audio Layer                                                     │
│  ├── sherpaKws.ts          WASM KWS (Sherpa-onnx, 1030 lines)  │
│  ├── vad.ts                Energy-based speech detection        │
│  └── AudioWorklet          Buffering + streaming                │
│                                                                  │
│  Service Layer                                                   │
│  ├── VoiceInputService     WebSocket client (BFF pattern)       │
│  └── voiceModeStore.ts     Zustand state (persisted)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket (audio PCM int16)
                              │
┌─────────────────────────────────────────────────────────────────┐
│                       BACKEND (FastAPI)                          │
├─────────────────────────────────────────────────────────────────┤
│  Router                                                          │
│  ├── POST /voice/ticket    BFF ticket auth (60s TTL)            │
│  └── WS /voice/ws/audio    Audio streaming + transcription      │
│                                                                  │
│  Services                                                        │
│  ├── WebSocketTicketStore  Single-use tickets (Redis)           │
│  └── SherpaSttService      Whisper Small INT8 (offline)         │
└─────────────────────────────────────────────────────────────────┘
```

### Flux Complet (User dit "OK quelque chose")

```
1. VoiceModeBadge (long-press 500ms)
   └─→ store.enable() → state='listening'

2. KWS listening active (microphone ouvert)
   └─→ Sherpa WASM traite audio en continu
   └─→ VAD WASM détecte segments de parole
   └─→ Whisper WASM transcrit segments

3. User dit "OK"
   └─→ KWS détecte wake word
   └─→ handleKeywordDetected('ok')
   └─→ cleanupKwsAudio() (ferme mic KWS)
   └─→ startRecording()

4. Recording context initialisé
   └─→ getUserMedia() (nouveau mic)
   └─→ VoiceInputService.connect()
        └─→ POST /voice/ticket → ticket
        └─→ WebSocket /ws/audio?ticket=xxx
   └─→ AudioWorklet 'voice-mode-processor'
   └─→ VAD instance créée
   └─→ state='recording'

5. User parle "quelque chose"
   └─→ Audio chunks → WebSocket (int16)
   └─→ VAD.process() → isSpeaking=true

6. User arrête de parler (silence 1s)
   └─→ VAD détecte silence → onSpeechEnd()
   └─→ state='processing'
   └─→ service.endAudio() → envoie "END"

7. Backend transcrit
   └─→ Convertit int16 → float32
   └─→ SherpaSttService.transcribe_async()
   └─→ WebSocket envoie {"type":"transcription","text":"quelque chose"}

8. Frontend reçoit transcription
   └─→ handleTranscription('quelque chose')
   └─→ onTranscription callback (parent)
   └─→ state='speaking' (si TTS)

9. TTS terminé
   └─→ onTtsComplete()
   └─→ state='listening' (retour à étape 2)
```

---

## Composants Frontend

### 1. VoiceOverlay.tsx

**Fichier** : `apps/web/src/components/voice/VoiceOverlay.tsx`

Interface overlay fullscreen remplaçant l'input texte.

**États visuels** :
| État | Visuel | Action |
|------|--------|--------|
| `idle` | Non rendu | - |
| `listening` | Microphone fixe | "Dites OK ou appuyez" |
| `recording` | Waves animées (pulse) | "J'écoute..." |
| `processing` | Spinner | "Traitement..." |
| `speaking` | Speaker pulsant | "LIA parle..." |

**Interactions** :
- Click sur conteneur = `onTap()` (listening) ou `onStop()` (recording)
- Bouton X = `onDisable()` (quitter voice mode)
- Clavier : Enter/Espace = click

### 2. VoiceModeBadge.tsx

**Fichier** : `apps/web/src/components/voice/VoiceModeBadge.tsx`

Badge compact avec activation long-press (500ms).

```typescript
// Long-press mechanism
onMouseDown → setTimeout(500ms) → toggle voice mode
onMouseUp (before 500ms) → cancel timer
```

**Couleurs par état** :
| État | Couleur | Animation |
|------|---------|-----------|
| Inactive | Gray | - |
| Initializing | Amber | Spinner |
| Listening | Green | - |
| Recording | Green | Pulse |
| Processing | Green/80 | Spinner |
| Speaking | Dark green | - |

### 3. useVoiceMode.ts

**Fichier** : `apps/web/src/hooks/useVoiceMode.ts` (830 lignes)

Hook principal d'orchestration du Voice Mode.

**Trois contextes audio séparés** :

| Contexte | Usage | Cleanup |
|----------|-------|---------|
| **KWS** | Wake word detection (continu) | `cleanupKwsAudio()` |
| **Recording** | Capture vocale post-wake word | `cleanupAudio()` |
| **VAD** | Détection fin de parole | Avec recording |

**API** :
```typescript
const {
  // State
  isEnabled, state, error,
  isKwsReady, isKwsLoading, isKwsListening,

  // Actions
  enable, disable, toggle,
  startRecording, stopRecording,

  // Handlers
  handleTap, handleStop,
} = useVoiceMode({
  onTranscription: (text) => { /* use transcribed text */ },
  onStartSpeaking: () => { /* TTS starting */ },
  onStopSpeaking: () => { /* TTS ended */ },
  onWakeWordDetected: () => { /* wake word detected */ },
  onError: (error) => { /* handle error */ },
});
```

### 4. voiceModeStore.ts (Zustand)

**Fichier** : `apps/web/src/stores/voiceModeStore.ts`

```typescript
interface VoiceModeState {
  isEnabled: boolean;           // Persisted (localStorage)
  state: VoiceModeState;        // idle|listening|recording|processing|speaking
  isKwsReady: boolean;
  isKwsLoading: boolean;
  isKwsListening: boolean;
  error: Error | null;
  lastWakeWordTime: number | null;
}
```

**Persistence** : `localStorage` key `voice_mode_enabled` (uniquement `isEnabled`).

### 5. VoiceInputService

**Fichier** : `apps/web/src/lib/voice-input-service.ts`

Client WebSocket avec pattern BFF (Backend-for-Frontend).

```typescript
class VoiceInputService {
  async connect(): Promise<void> {
    // 1. POST /api/v1/voice/ticket → ticket (60s TTL)
    // 2. WebSocket /api/v1/voice/ws/audio?ticket=xxx
  }

  sendAudio(samples: Float32Array): void {
    // Convert float32 → int16, send binary
  }

  endAudio(): void {
    // Send "END" text message → triggers transcription
  }
}
```

**Protocole WebSocket** :

| Direction | Type | Contenu |
|-----------|------|---------|
| → Backend | Binary | PCM int16, 16kHz |
| → Backend | Text | "END" (fin audio) |
| → Backend | Text | "PING" (heartbeat 30s) |
| ← Frontend | JSON | `{"type":"transcription","text":"..."}` |
| ← Frontend | JSON | `{"type":"pong"}` |

**Close Codes** :
- `4001` : Invalid/expired ticket
- `4008` : Idle timeout (120s)
- `4013` : Audio buffer overflow
- `4029` : Rate limited (10/min)

---

## Composants Backend

### 1. Voice Router

**Fichier** : `apps/api/src/domains/voice/router.py`

```python
@router.post("/ticket")
async def create_websocket_ticket(user: User):
    """Crée un ticket single-use pour WebSocket auth."""
    ticket = await ticket_store.create_ticket(str(user.id))
    return {"ticket": ticket, "ttl_seconds": 60}

@router.websocket("/ws/audio")
async def websocket_audio(ws: WebSocket, ticket: str):
    """WebSocket streaming audio + transcription."""
    # 1. Validate & consume ticket (single-use)
    # 2. Rate limit check (10/min per user)
    # 3. Accept connection
    # 4. Message loop (binary audio, "END" trigger)
    # 5. On "END": transcribe + send result
```

### 2. WebSocketTicketStore

**Fichier** : `apps/api/src/domains/voice/ticket_store.py`

```python
class WebSocketTicketStore:
    """Tickets single-use pour WebSocket auth (BFF pattern)."""

    async def create_ticket(self, user_id: str) -> str:
        ticket = str(uuid4())
        await self.redis.setex(
            f"ws:ticket:{ticket}",
            VOICE_WS_TICKET_TTL_SECONDS,  # 60s
            json.dumps({"user_id": user_id})
        )
        return ticket

    async def validate_and_consume_ticket(self, ticket: str) -> str | None:
        """Valide et supprime le ticket (single-use)."""
        key = f"ws:ticket:{ticket}"
        data = await self.redis.get(key)
        if data:
            await self.redis.delete(key)  # Single-use!
            return json.loads(data)["user_id"]
        return None
```

### 3. SherpaSttService

**Fichier** : `apps/api/src/domains/voice/stt/sherpa_stt.py`

```python
class SherpaSttService:
    """STT offline avec Sherpa-onnx Whisper Small INT8."""

    def __init__(self, settings):
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=str(settings.voice_stt_model_path / "encoder.onnx"),
            decoder=str(settings.voice_stt_model_path / "decoder.onnx"),
            tokens=str(settings.voice_stt_model_path / "tokens.txt"),
            num_threads=4,
            language="",  # Auto-detect
            task="transcribe",
        )

    def transcribe(self, audio_samples: list[float]) -> str:
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16000, audio_samples)
        self._recognizer.decode_stream(stream)
        return stream.result.text.strip()

    async def transcribe_async(self, audio_samples: list[float]) -> str:
        return await asyncio.get_event_loop().run_in_executor(
            _stt_executor,  # ThreadPoolExecutor(max_workers=4)
            self.transcribe,
            audio_samples,
        )
```

**Modèle** : `csukuangfj/sherpa-onnx-whisper-small` INT8
- **Taille** : ~375 MB
- **Langues** : 99+ (FR, EN, DE, ES, IT, ZH, ...)
- **Offline** : Complètement local
- **Coût** : Gratuit

---

## Wake Word Detection

### Architecture KWS (Keyword Spotting)

**Fichier** : `apps/web/src/lib/audio/sherpaKws.ts` (1030 lignes)

Le système de détection du wake word utilise Sherpa-onnx compilé en WASM :

```
Audio Input (microphone)
    ↓
AudioWorklet (chunks 100ms = 1600 samples)
    ↓
Circular Buffer
    ↓
VAD (Voice Activity Detection WASM)
    ↓ (segments de parole détectés)
Whisper Tiny WASM (transcription)
    ↓
Wake Word Matching ("ok guy", "ok guys", "okay guy", "okay guys")
    ↓
Callback onKeywordDetected()
```

### Wake Words Supportés

| Wake Word | Variations |
|-----------|------------|
| **OK Guy** | "ok guy", "okay guy" |
| **OK Guys** | "ok guys", "okay guys" |

**Pour l'utilisateur** : Le wake word est **"OK Guy"** ou **"OK Guys"** (prononcé en anglais).

> **Note technique** : Le fichier keywords.txt contient aussi les mots simples ("ok", "okay", "guy", "guys") comme fallback pour une détection plus robuste.

### Configuration KWS

**Fichier** : `apps/web/public/models/keywords.txt`

```
ok
okay
guy
guys
ok guy
okay guy
ok guys
okay guys
```

**Seuil de détection** : `VOICE_MODE_KWS_THRESHOLD = 0.25`

### Modèles WASM

```
apps/web/public/models/sherpa-wasm/
├── app-vad-asr.js
├── sherpa-onnx-asr.js
├── sherpa-onnx-vad.js
└── sherpa-onnx-wasm-main-vad-asr.js
```

**Prérequis navigateur** : `SharedArrayBuffer` (requires COOP/COEP headers).

---

## Voice Activity Detection

### VoiceActivityDetector

**Fichier** : `apps/web/src/lib/audio/vad.ts`

Algorithme energy-based pour détecter la fin de parole :

```typescript
class VoiceActivityDetector {
  private readonly energyThreshold = 0.02;
  private readonly silenceMs = 1000;
  private readonly minSpeechMs = 500;

  process(samples: Float32Array): void {
    const energy = this.calculateRmsEnergy(samples);
    const isSpeech = energy > this.energyThreshold;

    if (isSpeech && !this.wasSpeaking) {
      this.onSpeechStart?.();
    }

    if (!isSpeech && this.wasSpeaking) {
      this.silenceDurationMs += chunkDuration;
      if (this.silenceDurationMs >= this.silenceMs) {
        this.onSpeechEnd?.();  // Trigger transcription
      }
    }
  }

  private calculateRmsEnergy(samples: Float32Array): number {
    // RMS = sqrt(mean(x²))
    const sumSquares = samples.reduce((sum, x) => sum + x * x, 0);
    return Math.sqrt(sumSquares / samples.length);
  }
}
```

### Paramètres VAD

| Paramètre | Valeur | Description |
|-----------|--------|-------------|
| `VOICE_MODE_VAD_ENERGY_THRESHOLD` | 0.02 | Seuil énergie RMS |
| `VOICE_MODE_VAD_SILENCE_MS` | 1000 | Silence pour fin de parole |
| `VOICE_MODE_MIN_SPEECH_MS` | 500 | Durée minimum parole valide |

---

## Speech-to-Text (STT)

### Deux Modèles Distincts

| Composant | Modèle | Contexte | Usage |
|-----------|--------|----------|-------|
| **KWS (Frontend)** | Whisper tiny | WASM bundled | Détection wake word |
| **STT (Backend)** | Whisper small INT8 | Python | Transcription complète |

### Pourquoi Deux Modèles ?

- **KWS** : Léger (~3MB WASM), temps réel, détecte juste "OK"
- **STT** : Plus précis (375MB), 99+ langues, transcription complète

### Installation Modèle STT

```bash
# Télécharger le modèle Whisper Small
./scripts/download-whisper-model.sh
```

**Fichiers requis** :
```
apps/api/models/whisper-small/
├── encoder.onnx
├── decoder.onnx
└── tokens.txt
```

---

## Configuration

### Variables d'Environnement Backend

```bash
# STT
VOICE_STT_ENABLED=true
VOICE_STT_MODEL_PATH=/models/whisper-small
VOICE_STT_NUM_THREADS=4
VOICE_STT_LANGUAGE=              # Auto-detect si vide
VOICE_STT_TASK=transcribe        # transcribe | translate
VOICE_STT_MAX_DURATION_SECONDS=60

# WebSocket
VOICE_WS_TICKET_TTL_SECONDS=60
VOICE_WS_RATE_LIMIT_MAX_CALLS=10
VOICE_WS_RATE_LIMIT_WINDOW_SECONDS=60
VOICE_WS_IDLE_TIMEOUT_SECONDS=120
```

### Constants Frontend

**Fichier** : `apps/web/src/lib/constants.ts`

```typescript
// WebSocket
VOICE_INPUT_WS_RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000]
VOICE_INPUT_HEARTBEAT_INTERVAL_MS = 30000

// Audio
VOICE_INPUT_SAMPLE_RATE = 16000
VOICE_INPUT_CHUNK_SIZE = 4096  // 256ms

// Wake Word
VOICE_MODE_DEFAULT_WAKE_WORD = 'OK Guy'  // User-facing display value
VOICE_MODE_KWS_THRESHOLD = 0.25

// VAD
VOICE_MODE_VAD_SILENCE_MS = 1000
VOICE_MODE_VAD_ENERGY_THRESHOLD = 0.02
VOICE_MODE_MIN_SPEECH_MS = 500

// Recording
VOICE_MODE_MAX_RECORDING_SECONDS = 60
VOICE_MODE_IDLE_TIMEOUT_SECONDS = 300

// Persistence
VOICE_MODE_ENABLED_KEY = 'voice_mode_enabled'
```

---

## Sécurité

### BFF Pattern (WebSocket Auth)

1. **Ticket single-use** : Supprimé après validation
2. **TTL court** : 60 secondes d'expiration
3. **Session cookie** : Auth REST via session existante

### Rate Limiting

- **Per-user** : 10 connexions WebSocket / minute
- **Tracking** : Redis avec user_id

### Audio Buffer Protection

- **Max size** : `STT_MAX_AUDIO_BYTES` (~10MB)
- **Close code** : 4013 si dépassement

### Headers COOP/COEP

**Requis pour** : `SharedArrayBuffer` utilisé par Sherpa-onnx WASM pour le threading.

**Pourquoi** : Les navigateurs modernes (Chrome 92+, Firefox 79+, Safari 15.2+) restreignent `SharedArrayBuffer` pour des raisons de sécurité (Spectre). Les headers COOP/COEP créent un environnement "cross-origin isolated" qui autorise `SharedArrayBuffer`.

**Configuration Next.js** (`apps/web/next.config.ts`) :

```typescript
async headers() {
  return [
    {
      source: '/(.*)',
      headers: [
        {
          key: 'Cross-Origin-Opener-Policy',
          value: 'same-origin',
        },
        {
          key: 'Cross-Origin-Embedder-Policy',
          value: 'require-corp',
        },
      ],
    },
  ];
}
```

**Vérification** :

```javascript
// Console navigateur
console.log(crossOriginIsolated);  // Doit être: true

// Si false, SharedArrayBuffer non disponible
if (!crossOriginIsolated) {
  console.warn('WASM threading disabled - COOP/COEP headers missing');
}
```

**Conséquences COEP `require-corp`** :
- Les ressources externes (images, scripts) doivent avoir :
  - `Cross-Origin-Resource-Policy: cross-origin` OU
  - Être servies depuis le même domaine
- Solution pour images externes : utiliser `<img crossorigin="anonymous">` ou proxy

**Configuration Production (Nginx exemple)** :

```nginx
add_header Cross-Origin-Opener-Policy "same-origin" always;
add_header Cross-Origin-Embedder-Policy "require-corp" always;
```

**Détection navigateur** :

```typescript
// apps/web/src/lib/audio/sherpaKws.ts
const isWasmSupported = () => {
  return (
    typeof WebAssembly !== 'undefined' &&
    typeof SharedArrayBuffer !== 'undefined' &&
    crossOriginIsolated
  );
};
```

---

## Métriques

### Prometheus Backend

```python
# WebSocket
websocket_connections_active = Gauge("websocket_connections_active")
websocket_connections_total = Counter("websocket_connections_total", ["status"])
websocket_audio_bytes_received = Counter("websocket_audio_bytes_received")
websocket_connection_duration_seconds = Histogram("websocket_connection_duration_seconds")
websocket_tickets_issued_total = Counter("websocket_tickets_issued_total")
websocket_tickets_validated_total = Counter("websocket_tickets_validated_total", ["status"])

# STT
stt_audio_duration_seconds = Histogram("stt_audio_duration_seconds")
stt_transcription_duration_seconds = Histogram("stt_transcription_duration_seconds")
stt_transcriptions_total = Counter("stt_transcriptions_total", ["status"])
stt_errors_total = Counter("stt_errors_total", ["error_type"])
```

### Logs Structurés

```python
logger.info("websocket_ticket_issued", user_id=user_id)
logger.info("websocket_connected", user_id=user_id)
logger.info("websocket_rate_limited", user_id=user_id)
logger.info("stt_transcription_completed", duration_seconds=2.5, text_length=50)
```

---

## Dépannage

### Wake Word Non Détecté

1. Vérifier que `SharedArrayBuffer` est supporté (COOP/COEP headers)
2. Vérifier les logs console `kws_transcription` (toutes les transcriptions)
3. Augmenter `VOICE_MODE_KWS_THRESHOLD` si trop de faux positifs
4. Vérifier que le microphone est autorisé

### Transcription Vide

1. Vérifier que le modèle STT est téléchargé
2. Vérifier `VOICE_STT_ENABLED=true`
3. Consulter les logs backend `stt_transcription_completed`
4. Vérifier les métriques `stt_errors_total`

### WebSocket Déconnecté

1. Vérifier le close code (4001=ticket, 4029=rate limit)
2. Vérifier les métriques `websocket_tickets_validated_total{status="invalid"}`
3. Auto-reconnect après ~30s (5 tentatives)

### Performance Dégradée

1. Vérifier `VOICE_STT_NUM_THREADS` (défaut: 4)
2. Vérifier la charge CPU backend
3. Consulter `stt_transcription_duration_seconds`

### Erreur "SharedArrayBuffer not supported"

Ajouter les headers COOP/COEP dans `next.config.ts`.

---

## Références

### Frontend

- **VoiceOverlay**: `apps/web/src/components/voice/VoiceOverlay.tsx`
- **VoiceModeBadge**: `apps/web/src/components/voice/VoiceModeBadge.tsx`
- **useVoiceMode**: `apps/web/src/hooks/useVoiceMode.ts`
- **useSherpaKws**: `apps/web/src/hooks/useSherpaKws.ts`
- **useVAD**: `apps/web/src/hooks/useVAD.ts`
- **sherpaKws**: `apps/web/src/lib/audio/sherpaKws.ts`
- **vad**: `apps/web/src/lib/audio/vad.ts`
- **VoiceInputService**: `apps/web/src/lib/voice-input-service.ts`
- **voiceModeStore**: `apps/web/src/stores/voiceModeStore.ts`
- **constants**: `apps/web/src/lib/constants.ts`

### Backend

- **Voice Router**: `apps/api/src/domains/voice/router.py`
- **TicketStore**: `apps/api/src/domains/voice/ticket_store.py`
- **SherpaSttService**: `apps/api/src/domains/voice/stt/sherpa_stt.py`
- **Voice Config**: `apps/api/src/core/config/voice.py`
- **Voice Metrics**: `apps/api/src/infrastructure/observability/metrics_voice.py`

### Documentation

- [ADR-050: Voice Domain TTS Architecture](../architecture/ADR-050-Voice-Domain-TTS-Architecture.md)
- [ADR-054: Voice Input Architecture](../architecture/ADR-054-Voice-Input-Architecture.md)
- [Sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/)

---

**Fin de VOICE_MODE.md** - Documentation technique Voice Mode.
