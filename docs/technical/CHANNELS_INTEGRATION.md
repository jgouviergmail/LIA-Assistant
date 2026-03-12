# Multi-Channel Messaging Integration (evolution F3)

> Architecture et guide d'intégration pour les canaux de messagerie externes (Telegram).

**Phase**: evolution Feature 3 — Multi-Channel Telegram Integration
**Créé**: 2026-03-03
**Statut**: Implémenté

---

## Vue d'Ensemble

LIA supporte les **canaux de messagerie externes** comme complément à l'interface web. Les utilisateurs peuvent chatter avec LIA, recevoir des notifications proactives, approuver des plans HITL et envoyer des messages vocaux — le tout depuis Telegram.

L'architecture est **générique** : Telegram est la première implémentation, mais l'abstraction `BaseChannelSender` et le modèle `UserChannelBinding` permettent d'ajouter d'autres canaux (Discord, WhatsApp...) sans modifier le domaine.

### Fonctionnalités

| Fonctionnalité | Description |
|---------------|-------------|
| Chat bidirectionnel | Messages texte Telegram ↔ pipeline agent LIA |
| Notifications proactives | Intérêts, rappels, actions planifiées, [heartbeat autonome](./HEARTBEAT_AUTONOME.md) → Telegram |
| HITL (Human-in-the-Loop) | Boutons inline Telegram pour approuver/rejeter des plans |
| Messages vocaux | OGG/Opus → PCM 16kHz → Sherpa STT → texte |
| Liaison OTP | Code 6 chiffres via Redis, TTL 5min, single-use |
| Multi-langue | 6 langues (fr, en, es, de, it, zh) pour les messages bot et boutons HITL |

---

## Architecture

```
INBOUND (Telegram → LIA):
Telegram Bot API → POST /api/v1/channels/telegram/webhook
  → TelegramWebhookHandler (signature check, parse Update → ChannelInboundMessage)
  → ChannelMessageRouter (lookup binding, rate limit, per-user Redis lock)
  → InboundMessageHandler (AgentService.stream_chat_response, collect tokens)
  → TelegramSender (format MD→HTML, split 4000 chars, send via Bot API)

OUTBOUND (LIA → Telegram notifications):
NotificationDispatcher.dispatch()
  → Step 1: Archive (existant)
  → Step 2: FCM push (existant)
  → Step 3: SSE real-time (existant)
  → Step 4: _send_channels() → send_notification_to_channels() → _send_to_channel() → TelegramSender.send_notification()
```

### Structure des Fichiers

```
apps/api/src/domains/channels/           # Domaine (générique)
├── abstractions.py                      # Interfaces: BaseChannelSender, ChannelInboundMessage, etc.
├── models.py                            # UserChannelBinding (SQLAlchemy)
├── schemas.py                           # Pydantic: OTP, Binding CRUD
├── repository.py                        # UserChannelBindingRepository
├── service.py                           # ChannelService (OTP, CRUD, toggle)
├── message_router.py                    # ChannelMessageRouter (binding lookup, lock, rate limit)
├── inbound_handler.py                   # InboundMessageHandler (agent pipeline, content_replacement dedup)
└── router.py                            # FastAPI endpoints + webhook + background tasks

apps/api/src/infrastructure/channels/    # Infrastructure (spécifique Telegram)
└── telegram/
    ├── bot.py                           # Bot lifecycle (init/shutdown, webhook setup, getMe → bot_username)
    ├── webhook_handler.py               # Signature check, parse Update
    ├── sender.py                        # TelegramSender (send, typing, edit, notification)
    ├── formatter.py                     # MD→HTML, split, strip_html_cards, notification format, bot messages i18n
    ├── hitl_keyboard.py                 # InlineKeyboard builders pour HITL (6 langues)
    └── voice.py                         # Download OGG → transcode PCM → Sherpa STT

apps/web/src/
├── components/settings/ChannelSettings.tsx    # UI liaison Telegram
└── hooks/useChannelBindings.ts                # API hooks
```

---

## Configuration

### Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `CHANNELS_ENABLED` | `false` | Feature flag global |
| `TELEGRAM_BOT_TOKEN` | — | Token @BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | — | Secret pour validation webhook |
| `TELEGRAM_WEBHOOK_URL` | — | URL publique prod (si absent → long polling dev) |
| `TELEGRAM_BOT_USERNAME` | *(auto)* | Optionnel — auto-découvert via `getMe` au démarrage. Le setting `.env` n'est plus nécessaire. |
| `TELEGRAM_MESSAGE_MAX_LENGTH` | `4000` | Max avant split (100-4096) |
| `CHANNEL_OTP_TTL_SECONDS` | `300` | TTL OTP Redis |
| `CHANNEL_OTP_LENGTH` | `6` | Longueur code OTP |
| `CHANNEL_RATE_LIMIT_PER_USER_PER_MINUTE` | `10` | Rate limit inbound |
| `CHANNEL_RATE_LIMIT_GLOBAL_PER_SECOND` | `25` | Rate limit global bot |
| `CHANNEL_MESSAGE_LOCK_TTL_SECONDS` | `120` | Lock Redis per-user |

### Mode Dev vs Prod

| Aspect | Dev (pas de TELEGRAM_WEBHOOK_URL) | Prod (TELEGRAM_WEBHOOK_URL set) |
|--------|-----------------------------------|--------------------------------|
| Transport | Long polling via `python-telegram-bot` Application | Webhook via FastAPI endpoint |
| Bridge | `MessageHandler` + `CallbackQueryHandler` → `process_telegram_update()` | FastAPI endpoint → `process_telegram_update()` |
| URL publique | Non requise | Requise (HTTPS) |

---

## Flux Principaux

### 1. Liaison OTP

1. UI affiche le nom du bot (`@BotName`) dès l'état vide (auto-découvert via `getMe` au démarrage, exposé dans `GET /channels` → `telegram_bot_username`)
2. User clique "Lier Telegram" dans Settings > Features > Canaux
3. `POST /channels/otp/generate` → code 6 chiffres
4. Redis: `SET channel_otp:{code} = {user_id, channel_type} EX 300`
5. UI affiche le code + lien `@BotName`
6. User envoie `/start {code}` au bot
7. Webhook → parse → détecte `/start {otp}` → `_handle_otp_verification()`
8. Redis: GET → crée `UserChannelBinding` → DEL (single-use)
9. Bot répond "Compte lié avec succès !" dans la langue de l'user

**Anti-brute-force** : Redis `channel_otp_attempts:{chat_id}` avec INCR + EXPIRE 15min. Après 5 tentatives → blocage 15min.

### 2. Message Inbound

**Critique** : Le webhook retourne 200 immédiatement (sinon Telegram retry ~5s). Le traitement se fait en `asyncio.create_task()`.

1. `POST /channels/telegram/webhook` → validate signature → `return {"ok": True}`
2. Background task: `_process_telegram_update(payload)`
3. `TelegramWebhookHandler.parse_update()` → `ChannelInboundMessage`
4. `ChannelMessageRouter.route_message()`:
   - Lookup binding par `(channel_type, channel_user_id)`
   - Load User (timezone, language, memory_enabled)
   - Rate limit check
   - Redis lock `channel_msg_lock:{user_id}` (SET NX EX 120s)
   - Check HITL pending via `HITLStore.get_interrupt(conversation_id)`
5. `InboundMessageHandler.handle()`:
   - Si voice → download OGG → transcode → Sherpa STT → texte
   - Typing indicator continu (toutes les 4s)
   - `AgentService.stream_chat_response()` → collect tokens
   - Si HITL interrupt détecté → format plan + inline keyboard
   - Sinon → `markdown_to_telegram_html()` → split → send
6. Release Redis lock

**Déduplication `content_replacement`** : Le streaming LangGraph peut émettre le texte final de deux façons — incrémentalement via des chunks `token`, puis en bloc via un chunk `content_replacement` (texte post-traitement avec HTML cards). `InboundMessageHandler._stream_and_collect()` utilise `content_replacement` comme source **autoritaire** : quand présent, il remplace les tokens collectés (après `strip_html_cards()` pour retirer le HTML). En fallback (réponses simples sans cards), les tokens collectés sont utilisés directement.

**Session DB** : Background task utilise `async with get_db_context() as db:` (hors lifecycle requête FastAPI).

### 3. HITL via Telegram

6 types HITL, 2 patterns :
- **Boutons inline** : Plan Approval (`[Approuver] [Rejeter]`), Destructive Confirm (`[Confirmer] [Annuler]`), FOR_EACH Confirm (`[Continuer] [Arrêter]`)
- **Réponse texte** : Clarification, Draft Critique, Modifier Review

**Callback flow** :
1. Agent émet `hitl_interrupt_metadata` + `hitl_interrupt_complete`
2. `InboundMessageHandler` détecte dans la boucle de streaming
3. `hitl_keyboard.py` construit l'InlineKeyboard avec `callback_data = "hitl:{action}:{conversation_id}"`
4. User appuie sur un bouton → Telegram envoie `callback_query`
5. `_handle_hitl_callback()` : parse → lookup binding → verify HITL pending → edit message (retirer boutons) → `stream_chat_response(original_run_id=...)` pour reprendre le graph

### 4. Notifications Outbound

`NotificationDispatcher.dispatch()` a été étendu avec un 4ème canal :
1. Archive (existant)
2. FCM push (existant, tronqué à 150 chars)
3. SSE real-time (existant)
4. **Channels** : `_send_channels()` → `send_notification_to_channels()` → `_send_to_channel()` → `TelegramSender.send_notification()` (contenu complet, non tronqué)

**Point d'entrée public** : `send_notification_to_channels()` (fonction module-level dans `notification.py`) est réutilisable par tout système de notification (proactive, reminders, scheduled actions). Les canaux reçoivent le contenu intégral ; seul FCM est tronqué (preview mobile).

**Callers** :
- `NotificationDispatcher._send_channels()` → notifications proactives (intérêts, heartbeat)
- `reminder_notification.py` → rappels utilisateur (si `CHANNELS_ENABLED=true`)

### 5. Messages Vocaux

Pipeline : Telegram OGG/Opus → `pydub.AudioSegment` (ffmpeg) → resample 16kHz mono → float PCM → `SherpaSttService.transcribe_async()` → texte

**Prérequis** : `ffmpeg` installé dans le container Docker (`apt-get install -y ffmpeg`).

---

## Modèle de Données

### `UserChannelBinding`

| Colonne | Type | Contraintes |
|---------|------|------------|
| `id` | UUID PK | BaseModel |
| `user_id` | UUID FK users | CASCADE, indexed |
| `channel_type` | String(20) | NOT NULL |
| `channel_user_id` | String(100) | NOT NULL |
| `channel_username` | String(255) | nullable |
| `is_active` | Boolean | default true |
| `created_at` / `updated_at` | DateTime | BaseModel |

**Contraintes** :
- `UNIQUE(user_id, channel_type)` — un seul Telegram par user
- `UNIQUE(channel_type, channel_user_id)` — un seul user par compte Telegram
- Partial index sur `(channel_type, channel_user_id) WHERE is_active = true`

---

## Sécurité

| Risque | Mitigation |
|--------|-----------|
| Webhook forgé | `X-Telegram-Bot-Api-Secret-Token` (hmac.compare_digest) |
| Spam | Rate limit per-user (10/min) + global (25/sec) |
| Messages concurrents | Redis lock per-user (SET NX EX 120s) |
| Usurpation d'identité | OTP single-use + TTL + UNIQUE constraints bidirectionnelles |
| Brute-force OTP | Max 5 tentatives par chat_id, blocage 15min |
| Bot bloqué par user | Auto-disable binding sur `telegram.error.Forbidden` |
| Voice DoS (OOM) | Limite 20 MB sur le download OGG (`TELEGRAM_MAX_VOICE_FILE_SIZE`) |

---

## Observabilité

### Prometheus Metrics (`metrics_channels.py`)

| Métrique | Type | Labels |
|----------|------|--------|
| `channel_messages_received_total` | Counter | channel_type, message_type |
| `channel_message_processing_duration_seconds` | Histogram | channel_type |
| `channel_messages_rejected_total` | Counter | channel_type, reason |
| `channel_messages_sent_total` | Counter | channel_type, message_type |
| `channel_send_errors_total` | Counter | channel_type, error_type |
| `channel_active_bindings` | Gauge | channel_type |
| `channel_hitl_decisions_total` | Counter | channel_type, decision |
| `channel_voice_transcriptions_total` | Counter | channel_type, status |
| `channel_notifications_sent_total` | Counter | channel_type |

### structlog Events

`telegram_bot_initialized`, `telegram_webhook_received`, `channel_message_routed`, `channel_otp_generated`, `channel_otp_verified`, `channel_notification_sent`, `telegram_hitl_callback_processed`

---

## Tests

```bash
# Tous les tests channels (164 tests)
task test:backend:unit:fast -- tests/unit/domains/channels/ tests/unit/infrastructure/channels/ tests/unit/infrastructure/proactive/test_notification_channels.py

# Tests spécifiques
.venv/Scripts/pytest tests/unit/domains/channels/test_inbound_handler.py -v
.venv/Scripts/pytest tests/unit/infrastructure/channels/telegram/test_voice.py -v
.venv/Scripts/pytest tests/unit/infrastructure/channels/telegram/test_hitl_keyboard.py -v
```

| Suite | Tests |
|-------|-------|
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

---

## Ajout d'un Nouveau Canal

Pour ajouter un nouveau canal (ex: Discord) :

1. Ajouter `DISCORD = "discord"` dans `ChannelType` (`models.py`)
2. Créer `infrastructure/channels/discord/` avec `sender.py` implémentant `BaseChannelSender`
3. Ajouter le routage dans `_send_to_channel()` (fonction module-level dans `notification.py`)
4. Ajouter un webhook handler dans `router.py`
5. Ajouter les messages bot et labels HITL dans les dictionnaires i18n
6. Ajouter les constantes dans `core/constants.py`
7. Ajouter la configuration dans `core/config/channels.py`
