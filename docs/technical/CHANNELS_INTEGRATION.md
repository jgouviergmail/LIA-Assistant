# Multi-Channel Messaging Integration (evolution F3)

> Architecture et guide d'intégration pour les canaux de messagerie externes (Telegram).

**Phase**: evolution Feature 3 — Multi-Channel Telegram Integration
**Créé**: 2026-03-03
**Statut**: Implémenté

---

## Vue d'Ensemble

LIA supporte les **canaux de messagerie externes** comme complément à l'interface web. Les utilisateurs peuvent chatter avec LIA, recevoir des notifications proactives, répondre aux questions HITL (confirmer un brouillon ou une action, trancher une ambiguïté) et envoyer des messages vocaux — le tout depuis Telegram.

L'architecture est **générique** : Telegram est la première implémentation, mais l'abstraction `BaseChannelSender` et le modèle `UserChannelBinding` permettent d'ajouter d'autres canaux (Discord, WhatsApp...) sans modifier le domaine.

### Fonctionnalités

| Fonctionnalité | Description |
|---------------|-------------|
| Chat bidirectionnel | Messages texte Telegram ↔ pipeline agent LIA |
| Notifications proactives | Intérêts, rappels, actions planifiées, [heartbeat autonome](./HEARTBEAT_AUTONOME.md) → Telegram |
| HITL (Human-in-the-Loop) | Boutons inline Telegram pour confirmer ou annuler un brouillon, une action, une boucle FOR_EACH ; réponse tapée pour une clarification |
| Messages vocaux | OGG/Opus → PCM 16kHz → Sherpa STT → texte |
| Liaison OTP | Code 6 chiffres via Redis, TTL 5min, single-use |
| Multi-langue | 6 langues (fr, en, es, de, it, zh-CN — le code backend du chinois) pour les messages du bot et les boutons HITL : la langue du compte lié, celle que déclare le client Telegram tant que personne n'est connu (ADR-323) |

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
| `CHANNEL_MESSAGE_LOCK_TTL_SECONDS` | `120` | Borne de crash du verrou de tour (réarmé pendant le tour) |

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
7. Webhook → parse → détecte `/start {otp}` → `_handle_otp_verification()` ; tant que
   le code n'est pas vérifié, le bot parle la langue que déclare le client Telegram
   (`from.language_code`)
8. Redis : vérifie le code (usage unique) ; le compte qu'il nomme est lu et la
   liaison créée dans UNE session courte, désactivé compris : un compte désactivé
   reçoit `account_inactive` et n'est jamais lié ; un compte introuvable, une
   lecture ou une écriture qui échoue répondent `error` et ne lient rien — jamais
   un compte que personne n'a pu vérifier
9. Le bot répond `otp_success` dans la langue du compte, une fois la session
   fermée (ADR-304)

**Anti-brute-force** : Redis `channel_otp_attempts:{chat_id}` avec INCR + EXPIRE 15min. Après 5 tentatives → blocage 15min.

### 2. Message Inbound

**Critique** : Le webhook retourne 200 immédiatement (sinon Telegram retry ~5s). Le traitement se fait en `asyncio.create_task()`.

1. `POST /channels/telegram/webhook` → validate signature → `return {"ok": True}`
2. Background task: `process_telegram_update(payload)`
3. `TelegramWebhookHandler.parse_update()` → `ChannelInboundMessage`
4. `ChannelMessageRouter.route_message()`:
   - `read_binding_and_person()` : le binding par `(channel_type, channel_user_id)`
     et la ligne `User` qu'il nomme, dans une session courte, comptes et bindings
     désactivés compris ; une lecture en échec reçoit `error`, un inconnu `unbound`,
     dans la langue déclarée — celle du client Telegram
   - `resolve_channel_preferences(user)` : langue, fuseau, mémoire, journaux et
     psyché, lus sur la ligne du compte
   - Refus, dans cet ordre : `refusal_for()` (un compte désactivé reçoit
     `account_inactive`, un binding coupé `channel_disabled`), puis la limite de
     débit par personne (`busy`), dans la langue du compte, et rien ne tourne.
     Chaque message refusé est compté, mais la personne n'est avertie qu'une
     fois par fenêtre de débit (clé `channel_rate:notice:*`, partagée avec les
     boutons HITL — `answer_refusal()`) : répondu message par message, un
     compte qui continuait d'écrire recevait autant de réponses qu'il envoyait
     de messages. Un cache qui ne peut pas noter l'avertissement ne fait pas
     taire le refus : la personne est avertie (`channel_refusal_notice_unavailable`
     au journal), comme le limiteur de débit laisse passer quand il ne peut pas
     compter
   - Verrou Redis `channel_msg_lock:{user_id}` à jeton de propriétaire
     (`try_claim`) ; déjà pris → `busy`. Il est TENU pendant tout le tour
     (`held_claim` : réarmé plusieurs fois par `CHANNEL_MESSAGE_LOCK_TTL_SECONDS`,
     qui n'est qu'une borne en cas de crash — un tour dure bien plus), et au
     plus `BACKGROUND_RUNS_STREAM_SAFETY_TTL_SECONDS` (la plus longue exécution
     plausible) : au-delà, le tour est arrêté et le verrou rendu
   - La question en attente : `read_pending_question(conversation_id)`, lue dans la
     base Redis « cache », là où le moteur l'écrit, et non dans celle du verrou de
     tour ; lue à plat comme le chat la lit (`HITLStore.get_pending`), elle donne
     le run où la question a été posée (`run_id`), que la réponse reprend
5. `InboundMessageHandler.handle()`:
   - Si voice → download OGG → transcode → Sherpa STT → texte
   - Typing indicator continu (toutes les 4s)
   - `AgentService.stream_chat_response()` → lu jusqu'à son terme (`_ChannelTurn`) : sa queue enregistre la question en attente et commite les jetons
   - Si le tour s'est arrêté sur une question → la question (`hitl_question_token` / `generated_question`) + son clavier inline
   - Sinon → `markdown_to_telegram_html()` → split → send
6. `held_claim` libère le verrou en comparant son jeton : un verrou qu'un autre tour a
   pris n'est jamais libéré — la libération n'est même pas demandée quand le
   gardien a vu la reprise, et quand la reprise suit son dernier rafraîchissement
   la comparaison répond 0 —, et le tour qui l'a perdu est arrêté
   au rafraîchissement suivant — tant que le cache répond, les deux tours coexistent
   au plus une période de rafraîchissement ; un cache injoignable ne décide rien —
   (`ClaimLost`, compté `claim_lost`, la personne reçoit `error`) ; une autre
   annulation (arrêt du worker) reste une annulation, propagée une fois le verrou
   libéré

**Déduplication `content_replacement`** : Le streaming LangGraph peut émettre le texte final de deux façons — incrémentalement via des chunks `token`, puis en bloc via un chunk `content_replacement` (texte post-traitement avec HTML cards). `InboundMessageHandler._stream_and_collect()` (qui lit le flux par `_ChannelTurn`) retient `content_replacement` comme source **autoritaire** : quand présent, il remplace les tokens collectés (après `strip_html_cards()` pour retirer le HTML). En fallback (réponses simples sans cards), les tokens collectés sont utilisés directement.

**Session DB** : Background task utilise `async with get_db_context() as db:` (hors lifecycle requête FastAPI).

### 3. HITL via Telegram

Chaque type d'interaction déclare sa réponse (`hitl_keyboard._HITL_TYPE_BUTTONS`, vérifié au démarrage) :
- **Boutons inline** : Draft Critique et Tool Confirmation (`[Confirmer] [Annuler]`), FOR_EACH Confirm (`[Continuer] [Arrêter]`) — Plan Approval (`[Approuver] [Rejeter]`) et Destructive Confirm (`[Confirmer] [Annuler]`) n'ont aujourd'hui aucun producteur
- **Réponse texte** : Clarification, Entity Disambiguation — Edit Confirmation, déclarée aussi, n'a aucun producteur

**Callback flow** :
1. Agent émet `hitl_interrupt_metadata`, la question en `hitl_question_token`, puis `hitl_interrupt_complete` (`generated_question`) ; la queue du flux enregistre la question en attente
2. `InboundMessageHandler` lit le flux jusqu'à son terme, puis envoie la question
3. `hitl_keyboard.py` construit l'InlineKeyboard avec `callback_data = "hitl:{action}:{conversation_id}:{empreinte}"` — l'empreinte nomme la question (`question_fingerprint` de son `message_id`)
4. User appuie sur un bouton → Telegram envoie `callback_query`
5. `_handle_hitl_callback()` : parse → `read_binding_and_person()` et `refusal_for()`, comme le flux entrant (un compte désactivé ou un binding coupé est refusé, jamais repris) → le même verrou de tour que le message, tenu pendant la reprise (un double appui ou un bouton pressé pendant un tour reçoit `busy`), chaque refus compté — un compte refusé est averti une fois par fenêtre, par la même clé que ses messages —, un échec de la reprise répondu et journalisé → la conversation du bouton doit être celle de la personne (une lecture en échec reçoit `error`), la question encore en attente, et l'empreinte du bouton la sienne — sinon `hitl_expired` et clavier retiré, jamais un silence → clavier retiré, texte conservé (`remove_keyboard`) → `stream_chat_response(original_run_id=..., hitl_decision={message_id, action})` : la décision structurée de la carte du chat, appliquée sans modèle, dans la langue du compte

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
| Messages concurrents | Verrou Redis par personne à jeton de propriétaire, pris par le message comme par le bouton (`try_claim`), tenu pendant le tour et libéré par son jeton (`held_claim` ; `CHANNEL_MESSAGE_LOCK_TTL_SECONDS` borne un crash) |
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
| `channel_otp_generated_total` | Counter | channel_type |
| `channel_otp_verified_total` | Counter | channel_type, status |
| `channel_hitl_decisions_total` (questions HITL envoyées) | Counter | channel_type, decision |
| `channel_voice_transcriptions_total` | Counter | channel_type, status |
| `channel_voice_duration_seconds` | Histogram | channel_type |
| `channel_notifications_sent_total` | Counter | channel_type, task_type |
| `channel_notification_errors_total` | Counter | channel_type, error_type |

### structlog Events

Les principaux événements du canal, avec ce que chacun signifie, sont listés dans [GUIDE_TELEGRAM_INTEGRATION.md § 11.2](../guides/GUIDE_TELEGRAM_INTEGRATION.md).

---

## Tests

```bash
# Tous les tests channels, canaux de notification compris
# (--no-cov : le plancher de couverture de pyproject.toml vaut pour la suite
# entière ; un sous-ensemble vert sortirait en échec)
cd apps/api && .venv/Scripts/pytest tests/unit/domains/channels/ tests/unit/infrastructure/channels/ tests/unit/infrastructure/proactive/test_notification_channels.py -v --no-cov

# Tests spécifiques
.venv/Scripts/pytest tests/unit/domains/channels/test_inbound_handler.py -v --no-cov
.venv/Scripts/pytest tests/unit/infrastructure/channels/telegram/test_voice.py -v --no-cov
.venv/Scripts/pytest tests/unit/infrastructure/channels/telegram/test_hitl_keyboard.py -v --no-cov
```

Les suites de tests du canal sont `tests/unit/domains/channels/`,
`tests/unit/infrastructure/channels/` et les canaux de notification
(`tests/unit/infrastructure/proactive/test_notification_channels.py`). Leur nombre
se lit, il ne se recopie pas :

```bash
cd apps/api && .venv/Scripts/pytest --collect-only --no-cov tests/unit/domains/channels tests/unit/infrastructure/channels tests/unit/infrastructure/proactive/test_notification_channels.py | tail -1
```

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
