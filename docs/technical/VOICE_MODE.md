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
| **Wake Word** | Activation par « Dis LIA » — français seul pour l'instant, en **bêta** ; « Stop » coupe la lecture | Classifieur openWakeWord par langue, ONNX Runtime Web dans un worker ([ADR-329](../architecture/ADR-329-Live-Standby-And-Multilingual-Wake-Word.md)) |
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
  │        └────(phrase « Dis LIA »)──────┘
  └────(enable voice mode)────┘
```

**Récupération d'erreur** (durcie en v1.21.26, ADR-116) : toute erreur
(permission micro refusée, échec de connexion WebSocket, **coupure WebSocket
pendant `processing`**) affiche l'erreur puis ramène la machine à `listening`
si le mode vocal est activé, `idle` sinon — jamais de paire incohérente
`state='listening'`/`isEnabled=false`, jamais de spinner `processing` bloqué.
Le guard de coupure lit l'état courant du store (pas la closure du render du
`startRecording`, qui avalait silencieusement les coupures), et le timeout de
setup est désarmé une fois l'enregistrement démarré (plus d'unhandled
rejection différée après les enregistrements au wake word). La machine
complète est verrouillée par la suite `useVoiceMode.test.ts` (sans audio
réel : fakes AudioContext/Worklet/getUserMedia, détection du mot de réveil,
VAD et WS capturés).

---

## Architecture

### Stack Complète

```
┌─────────────────────────────────────────────────────────────────┐
│                       FRONTEND (Next.js)                         │
├─────────────────────────────────────────────────────────────────┤
│  UI Layer                                                        │
│  ├── VoiceOverlay.tsx      Overlay fullscreen, états visuels    │
│  └── VoiceModeBadge.tsx    Badge mains libres, icône seule      │
│                                                                  │
│  Hooks Layer                                                     │
│  ├── useVoiceMode.ts       Orchestration principale             │
│  ├── useWakeWord.ts        Mot de réveil (WakeListener)         │
│  └── useVAD.ts             Hook React pour VAD                  │
│                                                                  │
│  Audio Layer                                                     │
│  ├── wake-word/            Moteur ONNX dans un worker (ADR-329) │
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

### Flux Complet (User dit « Dis LIA, quelque chose »)

```
1. VoiceModeBadge (badge grisé : un appui l'active)
   └─→ store.enable() → state='listening'

2. Écoute du mot de réveil (useWakeWord → WakeListener)
   └─→ le modèle de la langue de l'interface se charge (worker, ONNX Runtime Web)
   └─→ PUIS le micro s'ouvre (16 kHz, morceaux de 80 ms, pcm-worklet)
   └─→ chaque morceau est scoré dans le worker

3. User dit « Dis LIA »
   └─→ le worker détecte la phrase
   └─→ handleWakeWordDetected()
   └─→ onWakeWord() : la voix de LIA se coupe si elle parlait (interruption)
   └─→ handOff() : la capture se ferme mais REMET son flux vivant
   └─→ startRecording(flux remis)

4. Recording context initialisé
   └─→ flux remis (aucun getUserMedia ; sinon un nouveau micro)
   └─→ VoiceInputService pré-connecté (sinon connect())
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

### 1. VoiceModeBadge.tsx

**Fichier** : `apps/web/src/components/voice/VoiceModeBadge.tsx`

Badge mains libres, **toujours affiché** dans le groupe central de l'entête du
chat (dans l'ordre : mains libres, jauge de contexte, espaces de connaissances),
**icône seule** à toutes les largeurs : l'état passe par l'icône et la couleur, les
mots par le nom accessible et l'infobulle.

- **Inactif** (grisé) : un appui active le mode mains libres.
- **Actif** : un appui agit sur l'état courant (parler, arrêter) ; un **appui long**
  (500 ms) le désactive — au clavier, **maintenir Espace** (Entrée reste un appui).
- Les deux transitions enregistrent la préférence (`PATCH /auth/me/voice-mode-preference`,
  la même requête que Réglages › Mode vocal) et l'annoncent avec les messages de
  cette page.

```typescript
// Long press (turns hands-free mode OFF only; never armed while off)
onMouseDown / onTouchStart / Space keydown → setTimeout(500ms) → disable()
release, leave, blur (before 500ms) → cancel timer
// The click that ends a fired press is swallowed
```

**Icône et couleur par état** :
| État | Icône | Couleur | Animation |
|------|-------|---------|-----------|
| Inactif | Micro | Gris discret | - |
| Navigateur non compatible | Micro barré | Gris discret, désactivé | - |
| Initializing | Spinner | Amber | Spin |
| Listening | Micro | Green | - |
| Recording | Micro | Green | Pulse |
| Processing | Spinner | Green/80 | Spin |
| Speaking | Ondes audio | Dark green | - |

### 2. useVoiceMode.ts

**Fichier** : `apps/web/src/hooks/useVoiceMode.ts`

Hook principal d'orchestration du Voice Mode.

**Trois contextes audio séparés** :

| Contexte | Usage | Cleanup |
|----------|-------|---------|
| **Mot de réveil** | Capture dédiée du `WakeListener` (continu en `listening`) | `pause()` / `handOff()` du listener |
| **Recording** | Capture vocale après la phrase (reprend le flux remis) | `cleanupAudio()` |
| **VAD** | Détection fin de parole | Avec recording |

**API** :
```typescript
const {
  // State
  isEnabled, state, error,
  wakeWordState, wakePhrase,   // 'idle' | 'loading' | 'listening' | 'unavailable'

  // Actions
  enable, disable, toggle,
  startRecording, stopRecording,

  // Handlers
  handleTap, handleStop,
} = useVoiceMode({
  onTranscription: (text) => { /* use transcribed text */ },
  onStartSpeaking: () => { /* TTS starting */ },
  onStopSpeaking: () => { /* TTS ended */ },
  onError: (error) => { /* handle error */ },
});
```

### 4. voiceModeStore.ts (Zustand)

**Fichier** : `apps/web/src/stores/voiceModeStore.ts`

```typescript
interface VoiceModeState {
  isEnabled: boolean;           // Persisted (localStorage)
  state: VoiceModeState;        // idle|listening|recording|processing|speaking
  error: Error | null;
  lastWakeWordTime: number | null;  // l'état du détecteur vit dans useWakeWord
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

Depuis [ADR-329](../architecture/ADR-329-Live-Standby-And-Multilingual-Wake-Word.md),
la phrase est celle de la langue de l'interface. Une phrase est un **modèle
entraîné**, jamais une saisie libre : `phrases.ts` déclare celles que la boîte à
outils entraîne (« Dis LIA » en fr, « Hey LIA » en en/de, « Oye LIA » en es,
« Ehi LIA » en it, « 嗨 LIA » en zh), mais seul ce qui est **livré** est offert.

### Langues livrées et statut bêta

`WAKE_MODEL_STATUS` (`lib/audio/wake-word/manifest.ts`) déclare les langues dont
un modèle est livré et leur statut : aujourd'hui `{ fr: 'beta' }`. Pour toute
autre langue d'interface, `wakeLanguageOf` répond `null` : l'écouteur reste
`unavailable` sans jamais demander un manifeste absent ni ouvrir le micro, le
badge offre l'appui pour parler, et les réglages disent que la phrase n'existe
pas encore dans cette langue (jamais un « {{phrase}} » vide). `beta` signifie
que le banc n'atteint pas encore ses seuils publiés (verdict `no-go` du
manifeste — mesures du modèle français : rappel 88 % au propre, 50 % à 10 dB,
0,5 faux déclenchement par heure sur la parole française) ; les réglages
affichent un badge « Bêta » et une note. La garde `shipped-models.test.ts` tient
le statut au verdict dans les deux sens : `stable` exige `go` pour la phrase
ET le mot « Stop », un modèle `beta` dont le banc dit `go` doit passer
`stable`, et aucun manifeste n'est livré pour une langue non déclarée.

### Moteur (`apps/web/src/lib/audio/wake-word/`)

```
Micro (WakeListener, 16 kHz, 1 280 échantillons = 80 ms, pcm-worklet)
    ↓ transferable int16
Worker module (worker.ts → worker-core.ts)
    ↓
engine.ts : melspectrogram des 1 760 derniers échantillons (x/10 + 2)
          → fenêtre de 76 trames mel → embedding (96)
          → fenêtre de 16 embeddings → score du classifieur
    ↓
policy.ts : échauffement, seuil, patience, période réfractaire (du manifeste)
    ↓
'detected' → onDetected → handOff() du flux → enregistrement
```

- **Arithmétique** : celle d'openWakeWord en streaming, à l'identique ; tenue à
  la référence de la boîte à outils par une fixture dorée exécutée sur les VRAIS
  modèles par ONNX Runtime Web (`__tests__/parity.test.ts`).
- **Runtime** : `onnxruntime-web/wasm`, **monothread, sans proxy** : ni
  `SharedArrayBuffer` ni isolation cross-origin — les deux conditions qui
  ôtaient le mot de réveil à iOS et aux coques natives (sonde mobile :
  `scripts/mobile-probe/`). Le binaire est servi depuis `/ort/<version>/`,
  copié du paquet par `apps/web/scripts/copy-ort-runtime.mjs` avant
  `next dev` / `next build` (jamais un CDN).
- **Modèles** : versionnés dans `apps/web/public/models/wake/v1/` — deux étages
  partagés (`shared/`) et un classifieur par langue, chaque fichier nommé
  d'après son SHA-256, et un `manifest.json` par langue (phrase, politique,
  fichiers avec taille et SHA-256, mesures, provenance et licences). Le
  navigateur refuse tout fichier qui ne correspond pas à son manifeste ; la
  garde `shipped-models.test.ts` tient chaque modèle livré à son manifeste.
- **Cache** : fichiers de modèle et binaire servis `immutable` (leur nom ou leur
  dossier change avec leur contenu), manifeste revalidé (`next.config.ts`).
- **Entraînement** : hors ligne, dans `scripts/wake-word/` (son README décrit
  les données, leurs licences et les mesures d'acceptation ; la procédure complète
  est expliquée dans [WAKE_WORD_TRAINING.md](WAKE_WORD_TRAINING.md)).

### États (`WakeListenerState`)

| État | Sens | Badge |
|------|------|-------|
| `loading` | le modèle de la langue se charge | « Initialisation » |
| `listening` | micro ouvert, la phrase est écoutée | « Prononce « Dis LIA » ou appuie pour parler » |
| `idle` | en pause (enregistrement, réponse, micro pris par une réunion, le mode Live ou la radio) | appui pour parler |
| `unavailable` | pas de modèle pour la langue, runtime absent, fichier refusé | appui pour parler |

Le micro ne s'ouvre **qu'après** le chargement du modèle : une langue sans
modèle utilisable n'allume jamais le micro. Une détection n'est remontée que
pendant l'écoute **et** si le dernier appel de l'appelant demandait d'écouter.

La phrase s'écoute aussi pendant que LIA lit sa réponse à voix haute : la dire
coupe sa voix **avant** que l'enregistrement s'ouvre (`onWakeWord` → `stopVoice`
du chat, le même arrêt qu'un clic). Sans cela, sa voix continuait par-dessus la
personne jusqu'à l'envoi de la transcription. Si rien n'est dit ensuite, la
transcription est vide et aucun message ne part.

**Le mot « stop »** coupe aussi sa voix, sans rien d'autre : ni enregistrement, ni
transcription, ni message. Chaque langue a le sien (« Stop » en français, anglais et
italien, « Stopp » en allemand, « 停下 » en chinois, « Detente » en espagnol),
nommé par `STOP_WORDS` (`phrases.ts`) et par l'indice du badge. C'est un second
classifieur sur les mêmes plongements, déclaré dans le manifeste de la langue sous
`commands`, posté par le worker comme `command` et relayé par l'écouteur sous la même
garde que la phrase (`useWakeWord.onCommand` → `useVoiceMode.onInterrupt`). Il n'est pas
armé : entendu quand rien ne joue, il n'arrête rien.

Le même `WakeListener` réveille une **session Live en veille** (ADR-329,
[LIVE_MODE.md](LIVE_MODE.md) § « Standby and wake ») : il écoute sur sa propre
capture tant que la page est visible, et libère le micro avant que la connexion
du réveil ne s'ouvre. Pendant une session Live — en veille comprise — l'écoute du
mode vocal classique reste en pause : un seul mot de réveil écoute à la fois.

## Voice Activity Detection

### VoiceActivityDetector

**Fichier** : `apps/web/src/lib/audio/vad.ts`

Algorithme energy-based pour détecter la fin de parole :

```typescript
class VoiceActivityDetector {
  private readonly energyThreshold = 0.02;
  private readonly silenceMs = 750;  // VOICE_MODE_VAD_SILENCE_MS
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

### Deux Backends, choix par utilisateur (ADR-080)

Depuis v1.20.x, l'utilisateur choisit son backend STT via la préférence
`voice_stt_mode` (`local` | `remote`) — applicable au push-to-talk **comme**
au mode wake-word, indépendamment du toggle `voice_mode_enabled` :

| Backend | Modèle | Coût | Audio | Quand |
|---------|--------|------|-------|-------|
| **`local`** (default) | Sherpa-onnx Whisper Small INT8 (Python backend) | Gratuit | Reste sur le serveur LIA | Confidentialité maximum, qualité honnête |
| **`remote`** | ElevenLabs Scribe v2 (cloud) | $0.22 / heure d'audio | Transmis à ElevenLabs | Qualité supérieure, refacturable |

Le mot de réveil (frontend, un modèle par langue, ADR-329) reste local dans
les deux cas — seul le segment de parole **après** la détection de la phrase
est routé selon `voice_stt_mode`.

### Routage backend

`apps/api/src/domains/voice/stt/factory.py` expose
`get_stt_service_for_mode(mode)` qui retourne une instance conforme au
`SttServiceProtocol` :

```python
async def transcribe_pcm_int16_async(
    self,
    pcm_int16_bytes: bytes,
    sample_rate: int = 16000,
    language: str | None = None,
) -> STTResult: ...
```

- **`local`** → singleton `SherpaSttService` (existant, inchangé pour le
  canal Telegram).
- **`remote`** → nouvelle instance `ElevenLabsSttService(api_key, model,
  base_url, timeout)`. La clé API est récupérée depuis
  `LLMConfigOverrideCache.get_api_key("elevenlabs")` (chiffrée Fernet
  dans `provider_api_keys`). Le modèle est lu via
  `LLMConfigOverrideCache.get_override("voice_transcription")` mergé
  avec `LLM_DEFAULTS["voice_transcription"]` (par défaut
  `elevenlabs/scribe_v2`).

### ElevenLabs Scribe — protocole

`POST {base_url}/speech-to-text` en multipart :

| Champ | Valeur |
|-------|--------|
| `file` | `pcm_int16_bytes` (binaire, content-type `application/octet-stream`) |
| `file_format` | `pcm_s16le_16` — PCM brut Int16 LE 16 kHz mono **sans wrap WAV** (confirmé verbatim par la doc) |
| `model_id` | `scribe_v2` (default) ou `scribe_v1` |
| `tag_audio_events` | `false` |
| `timestamps_granularity` | `none` |
| `language_code` | ISO-639-1 si dans `{en, fr, de, es, it, zh}` ; sinon omis (auto-detect) |

Header : `xi-api-key: <decrypted_key>`. Permission requise sur la clé :
**`speech_to_text`** (granulaire ElevenLabs).

Réponse :

```json
{
  "text": "Bonjour, quelle heure est-il ?",
  "audio_duration_secs": 1.85,
  "language_code": "fr"
}
```

`audio_duration_secs` est l'autorité sur la durée — utilisé pour le
calcul de coût et la persistance par-message. Pas de calcul depuis le
buffer.

### Mapping erreurs

| HTTP | `STTProviderError.code` | Close code WS |
|------|-------------------------|---------------|
| 429 | `provider_rate_limited` (+ `retry_after_seconds`) | 4029 |
| 422 | `provider_invalid_response` | 4002 |
| Autres 4xx/5xx | `provider_http_error` | 4002 |
| Timeout | `provider_timeout` | 4002 |
| (clé absente) | `elevenlabs_api_key_missing` | 4002 |

Le frontend reçoit `{type: "error", code, message, retry_after_seconds}`
juste avant la fermeture WS, ce qui permet un toast précis et un retry
intelligent (pas de fallback silencieux vers Sherpa local).

### Pricing & cost attribution

- Tarif ElevenLabs stocké tel quel dans `llm_model_pricing` :
  `pricing_unit=per_audio_hour`, `input_unit_price=0.22`. Voir ADR-080
  pour la décision d'extension du modèle pricing.
- Cache pricing sync-safe : `get_cached_cost_audio_usd_eur(model,
  duration_seconds)` dans `infrastructure/cache/pricing_cache.py`.
- Coût attribué à la **bulle utilisateur** :
  `conversation_messages.{stt_provider, stt_audio_duration_seconds,
  stt_cost_usd, stt_cost_eur, stt_usd_to_eur_rate}`.
- Agrégat dashboard : `user_statistics.{cycle, total}_stt_*` ; le coût
  s'ajoute à `cycle_cost_eur` / `total_cost_eur` (donc visible
  automatiquement dans la card "Cost" et inclus dans la check
  `usage_limits.cost_limit_per_cycle`).
- Exports CSV : `consumption-summary` enrichi (3 nouvelles colonnes
  `total_stt_*`) + nouveau type `stt-usage` (user + admin) avec une
  ligne par message remote-STT.

### Check usage_limits avant l'appel ElevenLabs

`/ws/audio` exécute `UsageLimitService.check_user_allowed(user_id)`
**avant** l'appel à ElevenLabs lorsque `voice_stt_mode='remote'`. Si
l'utilisateur dépasse `cost_limit_per_cycle`, la WebSocket se ferme avec
le close code 4029 et **aucun coût ElevenLabs n'est facturable** —
défense réelle, pas reactive.

### Ticket WebSocket étendu

`POST /voice/ticket` lit `current_user.voice_stt_mode` au moment de
l'émission et embarque la valeur dans le payload Redis
(`{user_id, language, voice_stt_mode}`). Le handler `/ws/audio`
récupère la pref via le ticket consommé et résout le bon backend via
la factory — aucun lookup DB par transcription.

### Modèles locaux requis (mode `local`)

| Composant | Modèle | Contexte | Usage |
|-----------|--------|----------|-------|
| **Mot de réveil (Frontend)** | openWakeWord, un classifieur par langue | ONNX Runtime Web (versionné) | Détection de la phrase |
| **STT (Backend)** | Whisper small INT8 | Python | Transcription complète |

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
# Audio long : le moteur Whisper de sherpa-onnx ne décode que les 30 premières
# secondes d'un buffer et jette le reste (mesuré le 2026-09-02). Au-delà du
# plafond « une passe », le service découpe l'audio en fenêtres alignées sur les
# silences (Silero VAD) ; les deux plafonds restent sous 30 s. Modèle VAD absent
# = fenêtres fixes (dégradé), jamais une troncature.
VOICE_STT_SINGLE_PASS_MAX_SECONDS=25
VOICE_STT_WINDOW_SECONDS=20
VOICE_STT_VAD_MODEL_PATH=/models/silero-vad/silero_vad.onnx
VOICE_STT_VAD_THRESHOLD=0.5
VOICE_STT_VAD_MIN_SILENCE_SECONDS=0.4
VOICE_STT_VAD_MIN_SPEECH_SECONDS=0.25

# WebSocket
VOICE_WS_TICKET_TTL_SECONDS=60
VOICE_WS_RATE_LIMIT_MAX_CALLS=10
VOICE_WS_RATE_LIMIT_WINDOW_SECONDS=60
VOICE_WS_IDLE_TIMEOUT_SECONDS=120
```

### Constants Frontend

**Fichier** : `apps/web/src/lib/constants.ts`

Audio (`VOICE_INPUT_SAMPLE_RATE`, `VOICE_INPUT_CHUNK_SIZE`), WebSocket
(`VOICE_INPUT_WS_RECONNECT_DELAYS`, `VOICE_INPUT_HEARTBEAT_INTERVAL_MS`), VAD
(`VOICE_MODE_VAD_SILENCE_MS`, `VOICE_MODE_VAD_ENERGY_THRESHOLD`,
`VOICE_MODE_MIN_SPEECH_MS`), enregistrement (`VOICE_MODE_MAX_RECORDING_SECONDS`)
et persistance (`VOICE_MODE_ENABLED_KEY`) — leurs valeurs vivent dans le
fichier, pas ici. La phrase et la politique de détection du mot de réveil
appartiennent à son modèle (manifeste), pas aux constantes.

---

## Sécurité---

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

Le mode vocal **n'en dépend plus** : le mot de réveil s'exécute en WASM
monothread (ADR-329), sans `SharedArrayBuffer` ni isolation. Les en-têtes
restent servis pour la posture décrite par
[ADR-136](../architecture/ADR-136-COEP-Posture-And-Widget-Failure-States.md)
(`COEP` résolu par `resolveCoepMode`, `credentialless` par défaut) ; leur choix
ne coûte plus le mot de réveil sur aucune plateforme.

**Prérequis navigateur du mot de réveil** (`isWakeWordSupported()`) : un worker
module, WebAssembly, un `AudioContext` et un `AudioWorkletNode`,
`crypto.subtle.digest` (contexte sécurisé) et `getUserMedia`.

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

1. Le badge doit afficher la phrase : sinon l'état est `unavailable` (pas de
   modèle pour la langue de l'interface, runtime absent, fichier refusé par
   son SHA-256) — la console du worker le dit
2. Vérifier que `/models/wake/v1/<langue>/manifest.json` et `/ort/<version>/`
   répondent (un `pnpm run dev` / `build` copie le binaire)
3. Vérifier que le microphone est autorisé (un refus est journalisé
   `voice_mode_wake_word_microphone_failed`, l'appui pour parler reste)
4. Le seuil et la patience sont ceux du manifeste, mesurés à l'entraînement :
   ils se changent en réentraînant (`scripts/wake-word`), jamais en production

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

### Erreur générique « une erreur s'est produite lors de la saisie vocale » (CSP)

La capture vocale (push-to-talk, mot de réveil **et** enregistrement) charge son `AudioWorklet`
depuis une URL `blob:`. D'après la spec CSP niveau 3, la destination fetch d'un
worklet est `audioworklet`, **gouvernée par `script-src`** (et non `worker-src`).
La CSP de l'app **doit donc conserver `blob:` dans `script-src`** — la retirer
bloque `audioWorklet.addModule()`, l'exception remonte en erreur générique et
**aucun octet audio n'est envoyé** (symptôme backend : le WebSocket se connecte
puis `websocket_disconnected_by_client` avec `total_bytes_received: 0`). Les
deux politiques CSP vivent dans `apps/web/src/lib/csp.ts` et chaque directive
porteuse est épinglée par un test de non-régression (`csp.test.ts`). Voir
[ADR-098](../architecture/ADR-098-CSP-Widget-Airlock.md) (régression réelle de
la vague 3).

---

## Références

### Frontend

- **VoiceModeBadge**: `apps/web/src/components/voice/VoiceModeBadge.tsx`
- **useVoiceMode**: `apps/web/src/hooks/useVoiceMode.ts`
- **useWakeWord**: `apps/web/src/hooks/useWakeWord.ts`
- **wake-word**: `apps/web/src/lib/audio/wake-word/` (listener, detector, worker, engine, policy, manifest, phrases)
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
- [ADR-329: Live standby and a multilingual wake word](../architecture/ADR-329-Live-Standby-And-Multilingual-Wake-Word.md)
- [openWakeWord](https://github.com/dscripka/openWakeWord) · [ONNX Runtime Web](https://onnxruntime.ai/docs/tutorials/web/)

---

## Latency Optimizations

### Push-to-Talk (`useVoiceInput`)

| Optimization | Technique | Gain |
|-------------|-----------|------|
| WS pre-warm | `VoiceInputService` connected in background during idle state | ~100-400ms |
| Parallel setup | `Promise.allSettled([getUserMedia, service.connect()])` | ~100-300ms |
| Worklet cache | Blob URL created once via `useRef`, reused across recordings | ~20-50ms |
| Cancel support | `cancelledRef` allows aborting during 'connecting' state | UX |
| Setup timeout | `VOICE_RECORDING_SETUP_TIMEOUT_MS` (10s) prevents indefinite blocking | Reliability |

### Voice Mode Wake Word (`useVoiceMode`)

| Optimization | Technique | Gain |
|-------------|-----------|------|
| Stream reuse | The wake word's live stream handed to the recording (`handOff`, skip `getUserMedia`), on a detection and on a tap | ~200-800ms |
| WS pre-warm | Service pre-connected during listening state | ~100-300ms |
| Parallel fallback | `Promise.allSettled` when stream reuse unavailable | ~100-300ms |
| Worklet cache | Same as push-to-talk | ~20-50ms |
| VAD tuning | Silence threshold reduced from 1000ms to 750ms | ~250ms perceived |
| Ready chime | Auditory feedback via Web Audio API oscillators (C5→E5 major third) | UX |

### Per-User STT Language

The user's preferred language (stored in `user.language` DB column) is passed through the WebSocket ticket to the backend STT service. `SherpaSttService` maintains a cache of `OfflineRecognizer` instances keyed by language code, so each user gets Whisper transcription biased to their language.

---

**Fin de VOICE_MODE.md** - Documentation technique Voice Mode.
