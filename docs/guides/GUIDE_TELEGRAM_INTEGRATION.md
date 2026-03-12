# Guide Pratique : Integration Telegram

> Guide developpeur pour l'integration du canal Telegram dans LIA.

**Version** : 1.0
**Date** : 2026-03-08
**Phase** : evolution Feature 3 -- Multi-Channel Telegram Integration
**Reference technique** : [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md)

---

## Table des matieres

1. [Introduction](#1-introduction)
2. [Architecture](#2-architecture)
3. [Configuration Telegram](#3-configuration-telegram)
4. [OTP Linking](#4-otp-linking)
5. [Webhook Handler](#5-webhook-handler)
6. [HITL via Telegram](#6-hitl-via-telegram)
7. [Notifications sortantes](#7-notifications-sortantes)
8. [Voice Transcription](#8-voice-transcription)
9. [Comment ajouter un nouveau canal](#9-comment-ajouter-un-nouveau-canal)
10. [Securite](#10-securite)
11. [Observabilite](#11-observabilite)
12. [Testing](#12-testing)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Introduction

LIA supporte les **canaux de messagerie externes** comme complement a l'interface web. Telegram est la **premiere implementation concrete** d'une architecture multi-canal generique.

### Fonctionnalites offertes via Telegram

| Fonctionnalite | Description |
|----------------|-------------|
| Chat bidirectionnel | Messages texte Telegram <-> pipeline agent LIA |
| Notifications proactives | Interets, rappels, actions planifiees, heartbeat autonome -> Telegram |
| HITL (Human-in-the-Loop) | Boutons inline Telegram pour approuver/rejeter des plans |
| Messages vocaux | OGG/Opus -> PCM 16kHz -> Sherpa STT -> texte |
| Liaison OTP | Code 6 chiffres via Redis, TTL 5min, single-use |
| Multi-langue | 6 langues (fr, en, es, de, it, zh) pour les messages bot et boutons HITL |

L'architecture est **generique** : les abstractions `BaseChannelSender` et `BaseChannelWebhookHandler` permettent d'ajouter d'autres canaux (Discord, WhatsApp...) sans modifier le domaine.

---

## 2. Architecture

### 2.1 Separation domaine / infrastructure

L'integration suit le pattern DDD du projet :

- **Domaine** (`domains/channels/`) : abstractions generiques, modeles, service, router -- independant de Telegram
- **Infrastructure** (`infrastructure/channels/telegram/`) : implementation specifique Telegram (bot API, formatage, HITL keyboard, voice)

### 2.2 Structure des fichiers

```
apps/api/src/domains/channels/           # Domaine (generique)
+-- abstractions.py                      # Interfaces : BaseChannelSender, BaseChannelWebhookHandler
+-- models.py                            # UserChannelBinding (SQLAlchemy), ChannelType (StrEnum)
+-- schemas.py                           # Pydantic v2 : OTP, Binding CRUD
+-- repository.py                        # UserChannelBindingRepository
+-- service.py                           # ChannelService (OTP, CRUD, toggle)
+-- message_router.py                    # ChannelMessageRouter (binding lookup, lock, rate limit)
+-- inbound_handler.py                   # InboundMessageHandler (agent pipeline, content_replacement)
+-- router.py                            # FastAPI endpoints + webhook + background tasks

apps/api/src/infrastructure/channels/    # Infrastructure (specifique Telegram)
+-- telegram/
    +-- bot.py                           # Bot lifecycle (init/shutdown, webhook setup, getMe)
    +-- webhook_handler.py               # Signature check, parse Update -> ChannelInboundMessage
    +-- sender.py                        # TelegramSender (send, typing, edit, notification)
    +-- formatter.py                     # MD->HTML, split, strip_html_cards, i18n messages
    +-- hitl_keyboard.py                 # InlineKeyboard builders pour HITL (6 langues)
    +-- voice.py                         # Download OGG -> transcode PCM -> Sherpa STT
```

### 2.3 Abstractions generiques

Deux classes abstraites definissent le contrat pour chaque canal :

**`BaseChannelSender`** (`domains/channels/abstractions.py`) -- 4 methodes obligatoires :

```python
class BaseChannelSender(ABC):
    @abstractmethod
    async def send_message(self, channel_user_id: str, message: ChannelOutboundMessage) -> str | None: ...

    @abstractmethod
    async def send_typing_indicator(self, channel_user_id: str) -> None: ...

    @abstractmethod
    async def send_notification(self, channel_user_id: str, title: str, body: str, data: dict[str, Any] | None = None) -> bool: ...

    @abstractmethod
    async def edit_message(self, channel_user_id: str, message_id: str, new_text: str, parse_mode: str = "HTML") -> bool: ...
```

**`BaseChannelWebhookHandler`** (`domains/channels/abstractions.py`) -- 2 methodes obligatoires :

```python
class BaseChannelWebhookHandler(ABC):
    @abstractmethod
    async def validate_signature(self, body: bytes, signature: str) -> bool: ...

    @abstractmethod
    async def parse_update(self, payload: dict) -> ChannelInboundMessage | None: ...
```

### 2.4 Flux de donnees

```
INBOUND (Telegram -> LIA) :
Telegram Bot API -> POST /api/v1/channels/telegram/webhook
  -> TelegramWebhookHandler (signature check, parse Update -> ChannelInboundMessage)
  -> ChannelMessageRouter (lookup binding, rate limit, per-user Redis lock)
  -> InboundMessageHandler (AgentService.stream_chat_response, collect tokens)
  -> TelegramSender (format MD->HTML, split 4000 chars, send via Bot API)

OUTBOUND (LIA -> Telegram notifications) :
NotificationDispatcher.dispatch()
  -> Step 1 : Archive (existant)
  -> Step 2 : FCM push (existant)
  -> Step 3 : SSE real-time (existant)
  -> Step 4 : _send_channels() -> send_notification_to_channels()
     -> _send_to_channel() -> TelegramSender.send_notification()
```

### 2.5 Data classes de transit

**`ChannelInboundMessage`** -- message entrant normalise :

```python
@dataclass
class ChannelInboundMessage:
    channel_type: ChannelType
    channel_user_id: str          # Telegram chat_id
    text: str | None = None
    voice_file_id: str | None = None
    voice_duration_seconds: int | None = None
    callback_data: str | None = None    # HITL button press
    message_id: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
```

**`ChannelOutboundMessage`** -- message sortant normalise :

```python
@dataclass
class ChannelOutboundMessage:
    text: str
    parse_mode: str = "HTML"
    reply_markup: dict | None = None    # Inline keyboard (HITL buttons)
```

---

## 3. Configuration Telegram

### 3.1 Creer un bot Telegram

1. Ouvrir [@BotFather](https://t.me/BotFather) sur Telegram
2. Envoyer `/newbot`
3. Choisir un nom (ex: "LIA Assistant") et un username (ex: `lia_assistant_bot`)
4. BotFather renvoie le **token** (format `123456789:ABCDEFghijklmnop...`)
5. Configurer les commandes du bot : `/setcommands` puis `start - Lier votre compte`

### 3.2 Variables d'environnement

Ajouter dans `.env` :

```bash
# Feature flag (obligatoire)
CHANNELS_ENABLED=true

# Token BotFather (obligatoire)
TELEGRAM_BOT_TOKEN=123456789:ABCDEFghijklmnop...

# Webhook secret (recommande en production)
TELEGRAM_WEBHOOK_SECRET=un-secret-aleatoire-fort

# URL webhook (production uniquement -- sans cette variable, le bot utilise le long polling)
TELEGRAM_WEBHOOK_URL=https://api.example.com/api/v1/channels/telegram/webhook
```

Toutes les variables sont definies dans `core/config/channels.py` via la classe `ChannelsSettings` :

| Variable | Defaut | Description |
|----------|--------|-------------|
| `CHANNELS_ENABLED` | `false` | Feature flag global |
| `TELEGRAM_BOT_TOKEN` | -- | Token @BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | -- | Secret pour validation webhook |
| `TELEGRAM_WEBHOOK_URL` | -- | URL publique prod (si absent -> long polling dev) |
| `TELEGRAM_MESSAGE_MAX_LENGTH` | `4000` | Max avant split (100-4096) |
| `CHANNEL_OTP_TTL_SECONDS` | `300` | TTL OTP Redis |
| `CHANNEL_OTP_LENGTH` | `6` | Longueur code OTP |
| `CHANNEL_OTP_MAX_ATTEMPTS` | `5` | Max tentatives OTP avant blocage |
| `CHANNEL_OTP_BLOCK_TTL_SECONDS` | `900` | Duree blocage brute-force |
| `CHANNEL_RATE_LIMIT_PER_USER_PER_MINUTE` | `10` | Rate limit inbound par utilisateur |
| `CHANNEL_RATE_LIMIT_GLOBAL_PER_SECOND` | `25` | Rate limit global bot |
| `CHANNEL_MESSAGE_LOCK_TTL_SECONDS` | `120` | Lock Redis per-user |

### 3.3 Mode Dev vs Prod

| Aspect | Dev (pas de `TELEGRAM_WEBHOOK_URL`) | Prod (`TELEGRAM_WEBHOOK_URL` configure) |
|--------|-------------------------------------|----------------------------------------|
| Transport | Long polling via `python-telegram-bot` Application | Webhook via FastAPI endpoint |
| Bridge | `MessageHandler` + `CallbackQueryHandler` -> `process_telegram_update()` | FastAPI endpoint -> `process_telegram_update()` |
| URL publique | Non requise | Requise (HTTPS) |
| Secret | Optionnel (accepts all en dev) | Fortement recommande |

Le choix est automatique dans `bot.py` :

```python
# apps/api/src/infrastructure/channels/telegram/bot.py
if webhook_url:
    # Production : set webhook with secret token
    await _bot.set_webhook(
        url=webhook_url,
        secret_token=webhook_secret,
        allowed_updates=["message", "callback_query"],
    )
else:
    # Development : long polling
    _application.add_handler(MessageHandler(filters.ALL, _polling_handler))
    _application.add_handler(CallbackQueryHandler(_polling_handler))
    await _application.updater.start_polling(
        allowed_updates=["message", "callback_query"],
    )
```

### 3.4 Initialisation et shutdown

Le bot est initialise au demarrage de l'application dans `main.py` (lifespan) et ferme proprement a l'arret :

```python
# Initialisation
from src.infrastructure.channels.telegram.bot import initialize_telegram_bot
await initialize_telegram_bot()  # Retourne Bot | None

# Shutdown
from src.infrastructure.channels.telegram.bot import shutdown_telegram_bot
await shutdown_telegram_bot()  # Supprime webhook ou arrete polling
```

Le username du bot est **auto-decouvert** via `getMe()` au demarrage -- plus besoin de le configurer manuellement.

---

## 4. OTP Linking

### 4.1 Flux complet

Le processus de liaison d'un compte LIA a Telegram utilise un code OTP (One-Time Password) :

```
1. [Frontend] UI Settings > Features > Canaux -> affiche @BotName (auto-decouvert via getMe)
2. [Frontend] Clic "Lier Telegram" -> POST /api/v1/channels/otp/generate
3. [Backend]  ChannelService.generate_otp() -> code 6 chiffres
4. [Redis]    SET channel_otp:{code} = {"user_id": "...", "channel_type": "telegram"} EX 300
5. [Frontend] Affiche le code + lien deep-link @BotName
6. [User]     Ouvre Telegram, envoie /start {code} au bot
7. [Backend]  Webhook -> parse -> detecte /start {otp} -> _handle_otp_verification()
8. [Backend]  ChannelService.verify_otp() -> Redis GET+DELETE atomique (pipeline)
9. [Backend]  ChannelService.create_binding() -> INSERT UserChannelBinding
10. [Bot]     Repond "Compte lie avec succes !" dans la langue de l'utilisateur
```

### 4.2 Generation OTP

```python
# apps/api/src/domains/channels/service.py
async def generate_otp(self, user_id: UUID, channel_type: ChannelType) -> tuple[str, int]:
    # Verifie qu'il n'y a pas deja un binding
    existing = await self.repository.get_by_user_and_type(user_id, channel_type.value)
    if existing:
        raise ValidationError("You already have a telegram account linked.")

    # Code cryptographiquement securise
    code = "".join(secrets.choice("0123456789") for _ in range(otp_length))

    # Stockage Redis avec TTL
    key = f"{CHANNEL_OTP_REDIS_PREFIX}{code}"
    data = {"user_id": str(user_id), "channel_type": channel_type.value}
    await redis.setex(key, otp_ttl, json.dumps(data))

    return code, otp_ttl
```

### 4.3 Verification OTP

La verification est **statique** (appelee depuis le webhook handler en background task avec sa propre session DB) :

```python
# apps/api/src/domains/channels/service.py
@staticmethod
async def verify_otp(code, channel_type, channel_user_id, channel_username=None):
    # 1. Check brute-force block
    # 2. Redis pipeline atomique : GET + DELETE (consume OTP)
    pipe = redis.pipeline()
    pipe.get(key)
    pipe.delete(key)
    results = await pipe.execute()
    # 3. Verify channel_type match
    # 4. Clear attempt counter on success
    return data  # {"user_id": "...", "channel_type": "telegram"}
```

### 4.4 Endpoints API

| Methode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/v1/channels/otp/generate` | Generer un code OTP |
| `GET` | `/api/v1/channels` | Lister les bindings + `telegram_bot_username` |
| `PATCH` | `/api/v1/channels/{binding_id}/toggle` | Activer/desactiver un binding |
| `DELETE` | `/api/v1/channels/{binding_id}` | Supprimer un binding (deliaison) |
| `POST` | `/api/v1/channels/telegram/webhook` | Webhook Telegram (non authentifie, valide par secret) |

---

## 5. Webhook Handler

### 5.1 Point d'entree

Le webhook est un endpoint **non authentifie** (pas de session cookie) -- la securite repose sur le header `X-Telegram-Bot-Api-Secret-Token` :

```python
# apps/api/src/domains/channels/router.py
@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request) -> dict:
    body = await request.body()
    signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    handler = TelegramWebhookHandler()
    if not await handler.validate_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    payload = json.loads(body)

    # Fire-and-forget : retourne 200 immediatement
    asyncio.create_task(process_telegram_update(payload))
    return {"ok": True}
```

**Point critique** : Le webhook **retourne 200 immediatement**. Le traitement se fait dans `asyncio.create_task()` en background. Sinon Telegram renvoie la mise a jour apres ~5 secondes de timeout.

### 5.2 Validation de signature

```python
# apps/api/src/infrastructure/channels/telegram/webhook_handler.py
async def validate_signature(self, body: bytes, signature: str) -> bool:
    expected = getattr(settings, "telegram_webhook_secret", None)
    if not expected:
        return True  # Dev mode : accepte tout

    if not signature:
        return False

    return hmac.compare_digest(signature, expected)  # Comparaison constant-time
```

### 5.3 Parsing des Updates

Le `TelegramWebhookHandler.parse_update()` gere trois types de mises a jour :

1. **Messages texte** : `payload["message"]["text"]`
2. **Messages vocaux** : `payload["message"]["voice"]`
3. **Callback queries** : `payload["callback_query"]` (boutons inline HITL)

Les types ignores (edited messages, channel posts, photos, stickers...) retournent `None`.

### 5.4 Pipeline de traitement

La fonction `process_telegram_update()` orchestre le traitement en background :

```python
# apps/api/src/domains/channels/router.py
async def process_telegram_update(payload: dict) -> None:
    message = await handler.parse_update(payload)
    if message is None:
        return

    # OTP : /start {code}
    if message.text and message.text.startswith("/start "):
        await _handle_otp_verification(...)
        return

    # HITL callback query (bouton inline)
    if message.callback_data:
        await _handle_hitl_callback(message)
        return

    # Message standard -> ChannelMessageRouter
    message_router = ChannelMessageRouter(redis=redis, sender=sender)
    await message_router.route_message(message)
```

### 5.5 ChannelMessageRouter -- pipeline de securite

Le `ChannelMessageRouter` applique les controles suivants dans l'ordre :

1. **Binding lookup** : `(channel_type, channel_user_id)` -> `UserChannelBinding`
2. **Rate limit** : Redis rate limiter, max 10 messages/user/minute
3. **Redis lock per-user** : `SET NX EX 120s` -- non-bloquant, envoie "busy" si deja verrouille
4. **Load User** : timezone, language, memory_enabled
5. **HITL check** : verifie si un HITL est en attente via `HITLStore`
6. **Dispatch** : `InboundMessageHandler.handle()`
7. **Release lock** : dans le bloc `finally`

**Session DB** : Le background task utilise `async with get_db_context() as db:` (pas `Depends(get_db)`) car il s'execute hors du lifecycle de la requete FastAPI.

### 5.6 Deduplication `content_replacement`

Le streaming LangGraph peut emettre le texte final de deux facons -- incrementalement via des chunks `token`, puis en bloc via un chunk `content_replacement`. L'`InboundMessageHandler._stream_and_collect()` utilise `content_replacement` comme source **autoritaire** : quand present, il remplace les tokens collectes (apres `strip_html_cards()` pour retirer le HTML des cards web). En fallback, les tokens collectes sont utilises directement.

---

## 6. HITL via Telegram

### 6.1 Types HITL et patterns

6 types HITL, repartis en 2 patterns d'interaction :

**Pattern boutons inline** (inline keyboard) :

| Type HITL | Boutons | callback_data |
|-----------|---------|---------------|
| `plan_approval` | [Approuver] [Rejeter] | `hitl:approve:{conv_id}` / `hitl:reject:{conv_id}` |
| `destructive_confirm` | [Confirmer] [Annuler] | `hitl:confirm:{conv_id}` / `hitl:cancel:{conv_id}` |
| `for_each_confirm` | [Continuer] [Arreter] | `hitl:continue:{conv_id}` / `hitl:stop:{conv_id}` |

**Pattern reponse texte libre** (pas de keyboard) :

| Type HITL | Comportement |
|-----------|-------------|
| `clarification` | L'utilisateur repond en texte libre |
| `draft_critique` | L'utilisateur repond en texte libre |
| `modifier_review` | L'utilisateur repond en texte libre |

### 6.2 Construction du keyboard

```python
# apps/api/src/infrastructure/channels/telegram/hitl_keyboard.py
def build_hitl_keyboard(hitl_type: str, conversation_id: str, language: str = "fr") -> dict:
    button_pair = _HITL_TYPE_BUTTONS.get(hitl_type)
    if not button_pair:
        return {}  # Text-based HITL, pas de keyboard

    action_positive, action_negative = button_pair
    return {
        "inline_keyboard": [[
            {
                "text": get_button_label(action_positive, language),
                "callback_data": f"hitl:{action_positive}:{conversation_id}",
            },
            {
                "text": get_button_label(action_negative, language),
                "callback_data": f"hitl:{action_negative}:{conversation_id}",
            },
        ]]
    }
```

### 6.3 Labels localises (6 langues)

Les labels des boutons HITL sont definis dans `HITL_BUTTON_LABELS` :

```python
HITL_BUTTON_LABELS = {
    "approve": {"fr": "Approuver", "en": "Approve", "es": "Aprobar", "de": "Genehmigen", "it": "Approvare", "zh": "批准"},
    "reject":  {"fr": "Rejeter",   "en": "Reject",  "es": "Rechazar", "de": "Ablehnen",  "it": "Rifiutare", "zh": "拒绝"},
    # ... confirm, cancel, continue, stop
}
```

### 6.4 Traitement du callback

Quand l'utilisateur appuie sur un bouton inline :

1. Telegram envoie un `callback_query` au webhook
2. `parse_hitl_callback_data("hitl:approve:conv-123")` -> `("approve", "conv-123")`
3. Lookup binding par `(telegram, chat_id)` -> user_id
4. Verification HITL encore pending via `HITLStore.get_interrupt(conversation_id)`
5. Edition du message original : suppression des boutons, affichage de la decision
6. Reprise du pipeline agent via `InboundMessageHandler.handle()` avec `pending_hitl` et `original_run_id`

---

## 7. Notifications sortantes

### 7.1 Architecture

Le `NotificationDispatcher.dispatch()` a ete etendu avec un 4eme canal de livraison :

1. **Archive** : stockage en base (existant)
2. **FCM push** : notification mobile Firebase, tronquee a 150 chars (existant)
3. **SSE real-time** : push temps reel vers le frontend web (existant)
4. **Channels** : `_send_channels()` -> `TelegramSender.send_notification()` (contenu **integral**, non tronque)

### 7.2 Envoi via TelegramSender

```python
# apps/api/src/infrastructure/channels/telegram/sender.py
async def send_notification(self, channel_user_id, title, body, data=None) -> bool:
    formatted = format_notification(title, body)  # "<b>Titre</b>\n\nCorps du message"
    message = ChannelOutboundMessage(text=formatted, parse_mode="HTML")
    result = await self.send_message(channel_user_id, message)
    return result is not None
```

### 7.3 Formatage des notifications

```python
# apps/api/src/infrastructure/channels/telegram/formatter.py
def format_notification(title: str, body: str) -> str:
    return f"<b>{html.escape(title)}</b>\n\n{html.escape(body)}"
```

Le `html.escape()` est essentiel pour eviter les erreurs `BadRequest` de Telegram causees par les caracteres `&`, `<`, `>` non echappes.

### 7.4 Types de notifications supportes

| Source | Module appelant |
|--------|----------------|
| Rappels utilisateur | `infrastructure/scheduler/reminder_notification.py` |
| Interets proactifs | `NotificationDispatcher._send_channels()` |
| Heartbeat autonome | `NotificationDispatcher._send_channels()` |
| Actions planifiees | `NotificationDispatcher._send_channels()` |

### 7.5 Gestion du bot bloque

Si l'utilisateur a bloque le bot, `TelegramSender` recoit une exception `Forbidden`. Le binding est automatiquement desactive :

```python
# apps/api/src/infrastructure/channels/telegram/sender.py
except Forbidden:
    logger.warning("telegram_bot_blocked", chat_id=channel_user_id)
    asyncio.create_task(_auto_disable_binding(channel_user_id))
    return None
```

---

## 8. Voice Transcription

### 8.1 Pipeline

```
Telegram voice message (OGG/Opus)
  -> Download via Bot API (limite 20 MB)
  -> pydub.AudioSegment.from_ogg() (necessite ffmpeg)
  -> Resample 16kHz mono, 16-bit
  -> Conversion float PCM [-1.0, 1.0]
  -> SherpaSttService.transcribe_async()
  -> Texte
```

### 8.2 Implementation

```python
# apps/api/src/infrastructure/channels/telegram/voice.py
async def transcribe_voice_message(bot, voice_file_id, voice_duration_seconds=None) -> str | None:
    # 1. Rejet messages trop longs (> 120 secondes)
    if voice_duration_seconds and voice_duration_seconds > _MAX_VOICE_DURATION_SECONDS:
        return None

    # 2. Download OGG bytes (avec validation taille)
    ogg_bytes = await _download_voice_file(bot, voice_file_id)

    # 3. Transcode CPU-bound via run_in_executor
    loop = asyncio.get_running_loop()
    samples = await loop.run_in_executor(None, _ogg_to_pcm_float, ogg_bytes)

    # 4. Transcription Sherpa STT
    stt = SherpaSttService(settings)
    text = await stt.transcribe_async(audio_samples=samples, sample_rate=16000)
    return text if text else None
```

### 8.3 Prerequis

- **ffmpeg** doit etre installe dans le container Docker (`apt-get install -y ffmpeg`)
- **pydub** doit etre dans les requirements Python
- Le transcodage est CPU-bound : il est execute dans un `ThreadPoolExecutor` via `run_in_executor`
- Limite de duree : 120 secondes maximum
- Limite de taille : 20 MB (`TELEGRAM_MAX_VOICE_FILE_SIZE`)

---

## 9. Comment ajouter un nouveau canal

Pour ajouter un canal (ex: Discord), suivre ces etapes :

### 9.1 Modele

Ajouter le type dans l'enum `ChannelType` :

```python
# apps/api/src/domains/channels/models.py
class ChannelType(StrEnum):
    TELEGRAM = "telegram"
    DISCORD = "discord"     # Nouveau
```

### 9.2 Infrastructure -- Sender

Creer `infrastructure/channels/discord/sender.py` implementant `BaseChannelSender` :

```python
# apps/api/src/infrastructure/channels/discord/sender.py
from src.domains.channels.abstractions import BaseChannelSender, ChannelOutboundMessage

class DiscordSender(BaseChannelSender):
    async def send_message(self, channel_user_id: str, message: ChannelOutboundMessage) -> str | None:
        # Implementation specifique Discord
        ...

    async def send_typing_indicator(self, channel_user_id: str) -> None:
        ...

    async def send_notification(self, channel_user_id: str, title: str, body: str, data=None) -> bool:
        ...

    async def edit_message(self, channel_user_id: str, message_id: str, new_text: str, parse_mode: str = "HTML") -> bool:
        ...
```

### 9.3 Infrastructure -- Webhook Handler

Creer `infrastructure/channels/discord/webhook_handler.py` implementant `BaseChannelWebhookHandler` :

```python
from src.domains.channels.abstractions import BaseChannelWebhookHandler, ChannelInboundMessage

class DiscordWebhookHandler(BaseChannelWebhookHandler):
    async def validate_signature(self, body: bytes, signature: str) -> bool:
        # Validation Ed25519 specifique Discord
        ...

    async def parse_update(self, payload: dict) -> ChannelInboundMessage | None:
        # Parse Discord interaction -> ChannelInboundMessage
        ...
```

### 9.4 Routage des notifications

Ajouter le routage dans la fonction `_send_to_channel()` du module de notification :

```python
async def _send_to_channel(binding: UserChannelBinding, title: str, body: str) -> bool:
    if binding.channel_type == ChannelType.TELEGRAM:
        sender = TelegramSender()
        return await sender.send_notification(binding.channel_user_id, title, body)
    elif binding.channel_type == ChannelType.DISCORD:
        sender = DiscordSender()
        return await sender.send_notification(binding.channel_user_id, title, body)
    return False
```

### 9.5 Router FastAPI

Ajouter un endpoint webhook dans `router.py` pour Discord.

### 9.6 Internationalisation

Ajouter les messages bot et labels HITL dans les dictionnaires i18n de `formatter.py` et `hitl_keyboard.py`.

### 9.7 Configuration

Ajouter les settings Discord dans `core/config/channels.py` et les constantes dans `core/constants.py`.

### 9.8 Checklist

- [ ] `ChannelType` enum mis a jour
- [ ] `BaseChannelSender` implemente
- [ ] `BaseChannelWebhookHandler` implemente
- [ ] Routage notification ajoute
- [ ] Endpoint webhook ajoute
- [ ] Messages bot i18n (6 langues)
- [ ] Labels HITL i18n (6 langues)
- [ ] Configuration `.env` + `ChannelsSettings`
- [ ] Constantes dans `core/constants.py`
- [ ] Tests unitaires
- [ ] Migration Alembic (si colonnes supplementaires)

---

## 10. Securite

### 10.1 Matrice des risques et mitigations

| Risque | Mitigation | Implementation |
|--------|-----------|----------------|
| Webhook forge | `X-Telegram-Bot-Api-Secret-Token` avec `hmac.compare_digest` | `TelegramWebhookHandler.validate_signature()` |
| Spam / flooding | Rate limit per-user (10/min) + global (25/sec) | `ChannelMessageRouter` + `RedisRateLimiter` |
| Messages concurrents | Redis lock per-user (`SET NX EX 120s`) | `ChannelMessageRouter.route_message()` |
| Usurpation d'identite | OTP single-use + TTL + contraintes UNIQUE bidirectionnelles | `ChannelService.verify_otp()` + `UserChannelBinding` |
| Brute-force OTP | Max 5 tentatives par `chat_id`, blocage 15min | `ChannelService.verify_otp()` + Redis counter |
| Bot bloque par user | Auto-disable binding sur `telegram.error.Forbidden` | `TelegramSender._auto_disable_binding()` |
| Voice DoS (OOM) | Limite 20 MB download + 120s duree | `voice.py` : `_download_voice_file()` |

### 10.2 Anti-brute-force OTP

```python
# Redis key: channel_otp_attempts:{chat_id}
# Increment a chaque tentative echouee, EXPIRE 15min
# Apres 5 tentatives -> blocage 15min

attempts_key = f"{CHANNEL_OTP_ATTEMPTS_REDIS_PREFIX}{channel_user_id}"
current_attempts = await redis.get(attempts_key)
if current_attempts and int(current_attempts) >= max_attempts:
    return None  # Bloque

# Sur echec : increment
pipe.incr(attempts_key)
pipe.expire(attempts_key, block_ttl)

# Sur succes : reset
await redis.delete(attempts_key)
```

### 10.3 Contraintes d'unicite de la base

Le modele `UserChannelBinding` impose deux contraintes UNIQUE :
- `UNIQUE(user_id, channel_type)` : un utilisateur ne peut lier qu'un seul compte Telegram
- `UNIQUE(channel_type, channel_user_id)` : un compte Telegram ne peut etre lie qu'a un seul utilisateur

Plus un **index partiel** pour le hot path webhook :
```python
Index("ix_channel_bindings_active_lookup", "channel_type", "channel_user_id",
      postgresql_where="is_active = true")
```

---

## 11. Observabilite

### 11.1 Metriques Prometheus

Le module `metrics_channels.py` expose 9 metriques suivant le pattern RED (Rate, Errors, Duration) :

| Metrique | Type | Labels |
|----------|------|--------|
| `channel_messages_received_total` | Counter | `channel_type`, `message_type` |
| `channel_message_processing_duration_seconds` | Histogram | `channel_type` |
| `channel_messages_rejected_total` | Counter | `channel_type`, `reason` |
| `channel_messages_sent_total` | Counter | `channel_type`, `message_type` |
| `channel_send_errors_total` | Counter | `channel_type`, `error_type` |
| `channel_active_bindings` | Gauge | `channel_type` |
| `channel_hitl_decisions_total` | Counter | `channel_type`, `decision` |
| `channel_voice_transcriptions_total` | Counter | `channel_type`, `status` |
| `channel_notifications_sent_total` | Counter | `channel_type` |

### 11.2 Evenements structlog

Les evenements de logging suivent les conventions structlog du projet :

| Evenement | Contexte |
|-----------|---------|
| `telegram_bot_initialized` | Demarrage du bot (polling ou webhook) |
| `telegram_webhook_received` | Reception d'un Update brut |
| `channel_message_routed` | Message dispatche au handler |
| `channel_otp_generated` | Code OTP genere |
| `channel_otp_verified` | Code OTP valide avec succes |
| `channel_notification_sent` | Notification sortante envoyee |
| `telegram_hitl_callback_processed` | Callback HITL traite |
| `telegram_bot_blocked` | Bot bloque par l'utilisateur (Forbidden) |
| `channel_message_rate_limited` | Message rejete (rate limit) |
| `channel_inbound_hitl_interrupt` | Interruption HITL detectee pendant le streaming |

---

## 12. Testing

### 12.1 Commandes de test

```bash
# Tous les tests channels (164 tests)
task test:backend:unit:fast -- \
  tests/unit/domains/channels/ \
  tests/unit/infrastructure/channels/ \
  tests/unit/infrastructure/proactive/test_notification_channels.py

# Tests specifiques par fichier
cd apps/api
.venv/Scripts/pytest tests/unit/domains/channels/test_service.py -v
.venv/Scripts/pytest tests/unit/domains/channels/test_message_router.py -v
.venv/Scripts/pytest tests/unit/domains/channels/test_inbound_handler.py -v
.venv/Scripts/pytest tests/unit/infrastructure/channels/telegram/test_formatter.py -v
.venv/Scripts/pytest tests/unit/infrastructure/channels/telegram/test_webhook_handler.py -v
.venv/Scripts/pytest tests/unit/infrastructure/channels/telegram/test_hitl_keyboard.py -v
.venv/Scripts/pytest tests/unit/infrastructure/channels/telegram/test_voice.py -v
```

### 12.2 Repartition des tests

| Suite | Nombre |
|-------|--------|
| `test_models.py` | 10 |
| `test_schemas.py` | 9 |
| `test_service.py` | 15 |
| `test_message_router.py` | 9 |
| `test_inbound_handler.py` | 16 |
| `test_formatter.py` | 37 |
| `test_webhook_handler.py` | 19 |
| `test_hitl_keyboard.py` | 24 |
| `test_voice.py` | 13 |
| `test_notification_channels.py` | 12 |
| **Total** | **164** |

### 12.3 Mocker le webhook en test

Pour tester le webhook sans Telegram reel, creer un payload simule :

```python
import pytest
from src.infrastructure.channels.telegram.webhook_handler import TelegramWebhookHandler

@pytest.mark.asyncio
async def test_parse_text_message():
    handler = TelegramWebhookHandler()
    payload = {
        "update_id": 123456,
        "message": {
            "message_id": 42,
            "chat": {"id": 98765, "type": "private"},
            "from": {"id": 98765, "first_name": "Alice", "username": "alice42"},
            "text": "Quel temps fait-il ?",
            "date": 1709683200,
        },
    }
    message = await handler.parse_update(payload)
    assert message is not None
    assert message.text == "Quel temps fait-il ?"
    assert message.channel_user_id == "98765"
```

### 12.4 Mocker le TelegramSender

```python
from unittest.mock import AsyncMock
from src.domains.channels.abstractions import BaseChannelSender

def create_mock_sender() -> BaseChannelSender:
    sender = AsyncMock(spec=BaseChannelSender)
    sender.send_message.return_value = "msg_123"
    sender.send_notification.return_value = True
    sender.send_typing_indicator.return_value = None
    sender.edit_message.return_value = True
    return sender
```

### 12.5 Tester le callback HITL

```python
@pytest.mark.asyncio
async def test_parse_hitl_callback():
    handler = TelegramWebhookHandler()
    payload = {
        "update_id": 123457,
        "callback_query": {
            "id": "cb_123",
            "data": "hitl:approve:conv-uuid-here",
            "message": {
                "message_id": 42,
                "chat": {"id": 98765, "type": "private"},
            },
            "from": {"id": 98765, "first_name": "Alice"},
        },
    }
    message = await handler.parse_update(payload)
    assert message is not None
    assert message.callback_data == "hitl:approve:conv-uuid-here"
```

---

## 13. Troubleshooting

### Probleme : Le bot ne repond pas

1. Verifier `CHANNELS_ENABLED=true` dans `.env`
2. Verifier `TELEGRAM_BOT_TOKEN` est configure
3. Verifier les logs : `telegram_bot_initialized` doit apparaitre au demarrage
4. En mode dev : verifier que le long polling est actif (`telegram_bot_initialized_polling`)
5. En mode prod : verifier que l'URL webhook est accessible en HTTPS

### Probleme : Webhook renvoie 403

- Verifier que `TELEGRAM_WEBHOOK_SECRET` dans `.env` correspond au secret configure lors de `set_webhook()`
- En dev sans secret configure, le handler accepte tout (log warning `telegram_webhook_no_secret_configured`)

### Probleme : OTP invalide ou expire

- Le code OTP a un TTL de 300 secondes (5 minutes) -- l'utilisateur doit agir rapidement
- Le code est **single-use** : une fois consomme (meme en echec de creation du binding), il faut en generer un nouveau
- Si `channel_otp_brute_force_blocked` dans les logs : l'utilisateur a depasse 5 tentatives, attendre 15 minutes

### Probleme : Messages vocaux non transcrits

- Verifier que `ffmpeg` est installe dans le container Docker
- Verifier les logs : `telegram_voice_transcription_failed` avec le stack trace
- Limite de duree : 120 secondes maximum (`telegram_voice_too_long`)
- Limite de taille : 20 MB maximum (`telegram_voice_file_too_large`)

### Probleme : HITL buttons ne fonctionnent pas

- Verifier que `callback_query` est dans `allowed_updates` du webhook
- Verifier les logs : `telegram_hitl_callback_invalid` si le format `callback_data` est incorrect
- `telegram_hitl_callback_expired` : l'interruption HITL a expire cote serveur

### Probleme : Notifications non recues

- Verifier que le binding est actif (`is_active = true`)
- `telegram_bot_blocked` dans les logs : l'utilisateur a bloque le bot (binding auto-desactive)
- `telegram_rate_limit` : le bot a atteint les limites Telegram Bot API (retry automatique)

### Probleme : Messages tronques ou mal formates

- Le formatage Markdown -> HTML est basique (bold, italic, code, links)
- Les cards HTML du frontend web sont strippees automatiquement via `strip_html_cards()`
- Si `telegram_send_bad_request` : le HTML genere est invalide, le sender retente en texte brut (fallback)
- Verifier `TELEGRAM_MESSAGE_MAX_LENGTH` (defaut 4000, max Telegram 4096)

### Probleme : "Je traite encore votre message precedent"

- Le Redis lock per-user est actif pendant 120 secondes
- Si le message precedent est encore en cours de traitement, le nouveau message recoit "busy"
- Verifier `CHANNEL_MESSAGE_LOCK_TTL_SECONDS` si le pipeline agent est systematiquement trop lent
