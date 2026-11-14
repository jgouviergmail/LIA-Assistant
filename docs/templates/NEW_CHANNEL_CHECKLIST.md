# Checklist : Ajouter un Nouveau Canal de Messagerie

**Nom du canal** : _________________________ (ex. Discord, WhatsApp, Slack)
**Développeur** : _________________________
**Date** : _________________________

> Telegram est le seul canal implémenté et cette liste n'a encore jamais été déroulée pour un second canal. Elle décrit ce que le code exige aujourd'hui. L'état du domaine — ce qui est générique, ce qui est câblé sur Telegram, la question du transport — est tenu dans [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md), section « Ajout d'un Nouveau Canal » : le lire avant de commencer.

---

## Concepts clés

- `BaseChannelSender` : interface d'envoi (quatre méthodes)
- `BaseChannelWebhookHandler` : interface d'entrée par webhook (deux méthodes)
- `ChannelInboundMessage` / `ChannelOutboundMessage` : messages normalisés
- `UserChannelBinding` : liaison générique entre un compte LIA et un compte du canal
- `ChannelAssistantGateway` : frontière vers l'assistant, installée au démarrage ; le domaine des canaux n'importe pas celui des agents

Les quatre premiers vivent dans `domains/channels/` (`abstractions.py`, `models.py`). L'implémentation de référence est `infrastructure/channels/telegram/`.

---

## Phase 0 : Généraliser le domaine

Le traitement des messages importe encore directement l'implémentation Telegram. Tant que ces points ne sont pas généralisés, un second canal ne peut ni recevoir ni répondre.

- [ ] `domains/channels/router.py` : une route d'entrée et un traitement par canal ; l'expéditeur et le gestionnaire d'entrée choisis d'après le type de canal, plus construits en dur (`TelegramSender()`, `TelegramWebhookHandler()`)
- [ ] `send_text()` est une méthode de `TelegramSender` que `BaseChannelSender` ne déclare pas, et le routeur l'appelle : la déclarer dans l'interface ou ne plus l'appeler
- [ ] `domains/channels/inbound_handler.py` : le rendu du texte, le clavier des questions, la voix et l'indicateur de frappe fournis par le canal, plus importés du paquet Telegram ; la métrique des questions HITL étiquetée du type réel
- [ ] `domains/channels/message_router.py` : les messages du bot lus dans une table commune aux canaux, plus dans `TELEGRAM_BOT_MESSAGES`
- [ ] `domains/channels/read_projection.py` et `schemas.py` : le champ `telegram_bot_username` remplacé par une information portée par chaque canal
- [ ] `ChannelOutboundMessage.parse_mode` vaut `"HTML"` par défaut : décider ce que ce champ signifie pour un canal qui ne parle pas HTML
- [ ] `infrastructure/proactive/notification.py` : `_send_to_channel()` aiguille d'après le type de canal
- [ ] Écran : `ChannelSettings.tsx` et `useChannelBindings.ts` listent les canaux au lieu de supposer `telegram`

---

## Phase 1 : Type et modèle

- [ ] Ajouter la valeur à `ChannelType` (`domains/channels/models.py`) et sa constante `CHANNEL_TYPE_*` (`core/constants.py`)
- [ ] Vérifier que les colonnes de `UserChannelBinding` suffisent : `channel_type` (20 caractères), `channel_user_id` (100), `channel_username` (255). Le modèle n'a aucun champ libre par canal : une donnée de plus demande une migration Alembic
- [ ] Les deux contraintes d'unicité valent pour le nouveau canal : une liaison par compte et par type, un compte par identifiant externe et par type

---

## Phase 2 : Envoi

- [ ] Implémenter `BaseChannelSender` :

  ```python
  # apps/api/src/infrastructure/channels/votre_canal/sender.py
  from typing import Any

  from src.domains.channels.abstractions import BaseChannelSender, ChannelOutboundMessage


  class VotreCanalSender(BaseChannelSender):
      """Envoi de messages vers votre canal."""

      async def send_message(
          self, channel_user_id: str, message: ChannelOutboundMessage
      ) -> str | None: ...

      async def send_typing_indicator(self, channel_user_id: str) -> None: ...

      async def send_notification(
          self, channel_user_id: str, title: str, body: str, data: dict[str, Any] | None = None
      ) -> bool: ...

      async def remove_keyboard(self, channel_user_id: str, message_id: str) -> bool: ...
  ```

- [ ] `send_message()` rend l'identifiant du message envoyé, ou `None` quand le fournisseur l'a refusé
- [ ] Formateur : le Markdown de l'assistant converti au format du canal, puis découpé sous la limite de longueur du canal sans casser son balisage (Telegram : `formatter.py` et `html_split.py`)
- [ ] Les cartes HTML du chat web sont retirées avant l'envoi (Telegram : `strip_html_cards()`)
- [ ] Un envoi refusé parce que la personne a bloqué le bot coupe la liaison (Telegram : `Forbidden` → `_auto_disable_binding()`)
- [ ] L'attente que demande le fournisseur est respectée (Telegram : `flood_control.py`)

---

## Phase 3 : Entrée

- [ ] Implémenter `BaseChannelWebhookHandler` :

  ```python
  # apps/api/src/infrastructure/channels/votre_canal/webhook_handler.py
  from src.domains.channels.abstractions import BaseChannelWebhookHandler, ChannelInboundMessage


  class VotreCanalWebhookHandler(BaseChannelWebhookHandler):
      """Authenticité et lecture des mises à jour de votre canal."""

      async def validate_signature(self, body: bytes, signature: str) -> bool: ...

      async def parse_update(self, payload: dict) -> ChannelInboundMessage | None: ...
  ```

- [ ] `validate_signature()` refuse quand aucun secret n'est configuré (SEC-024), et le démarrage refuse un mode webhook sans secret réel (modèle : `ChannelsSettings._webhook_mode_requires_a_real_secret`)
- [ ] La route vérifie l'authenticité avant toute lecture du corps quand le secret ne porte pas sur le corps (cas de Telegram) ; un échec passe par `raise_invalid_webhook_signature()` (`core/exceptions.py`), jamais par un `HTTPException` brut
- [ ] La route répond tout de suite et lance le traitement par `safe_fire_and_forget()` ; le traitement ouvre ses propres sessions par `get_db_context()` et n'en garde aucune ouverte pendant un appel réseau (ADR-304)
- [ ] Une livraison que le fournisseur rejoue est écartée (Telegram : `_claim_telegram_update()`)
- [ ] `parse_update()` rend `None` pour tout ce que le canal ne prend pas en charge
- [ ] Le canal ne livre pas par webhook mais par une connexion maintenue ouverte : aucun modèle n'existe en production, voir « Transport » dans le document technique

---

## Phase 4 : Liaison par code

Le parcours est le même pour tous les canaux :

1. `POST /channels/otp/generate`, avec le type de canal → `ChannelService.generate_otp()` : un code à usage unique, gardé `CHANNEL_OTP_TTL_SECONDS`
2. La personne envoie ce code au bot depuis le canal (Telegram : `/start {code}`)
3. `ChannelService.verify_otp()` consomme le code et compte les tentatives par identifiant externe (`CHANNEL_OTP_MAX_ATTEMPTS`, `CHANNEL_OTP_BLOCK_TTL_SECONDS`)
4. Le compte que nomme le code est lu, puis `ChannelService.create_binding()` écrit la liaison, dans une seule session courte ; un compte désactivé n'est jamais lié, et la réponse part une fois la session fermée (ADR-304)

- [ ] Détecter le code dans un message du canal (Telegram : `/start {code}`, dans `_dispatch_update()`)
- [ ] `_handle_otp_verification()` est aujourd'hui câblée sur Telegram : la généraliser (phase 0)
- [ ] Tant que le compte n'est pas connu, le bot répond dans la langue que déclare le client du canal ; ensuite dans celle du compte (ADR-323)

---

## Phase 5 : Questions de confirmation (HITL)

- [ ] Chaque type d'interaction déclare sa réponse — deux boutons ou du texte — dans `_HITL_TYPE_BUTTONS` (`hitl_keyboard.py`), vérifié au démarrage : le nouveau canal lit cette même déclaration
- [ ] Un bouton porte `hitl:{action}:{conversation_id}:{empreinte}` : vérifier que cette donnée tient dans ce que le canal accepte (Telegram : 64 octets)
- [ ] Un bouton pressé suit `_handle_hitl_callback()` : mêmes refus et même verrou de tour qu'un message ; une question expirée répond `hitl_expired` et perd son clavier (`remove_keyboard()`)
- [ ] Un canal sans boutons : toutes les questions sont répondues en texte

---

## Phase 6 : Notifications

- [ ] Ajouter la branche du canal dans `_send_to_channel()` (`infrastructure/proactive/notification.py`) : tout appelant de `send_notification_to_channels()` passe par elle
- [ ] `send_notification()` ne rend `True` que lorsque le fournisseur a pris le message : la livraison durable s'appuie sur ce résultat (`NotificationResult.durably_delivered`)

---

## Phase 7 : Configuration

- [ ] Réglages dans `ChannelsSettings` (`core/config/channels.py`), chacun avec sa description ; valeurs par défaut dans `core/constants.py`
- [ ] `CHANNELS_ENABLED` reste l'interrupteur global ; un interrupteur propre au canal n'est ajouté que s'il a un lecteur
- [ ] Gabarits d'environnement à jour (`.env.example`, `.env.prod.example` et les autres gabarits du dépôt) : `test_env_template_parity_guard.py` les compare aux valeurs par défaut du code
- [ ] Toute clé Redis nommée par un identifiant de compte déclare sa famille (`infrastructure/cache/key_families.py`, ADR-260)

---

## Phase 8 : Démarrage et arrêt

- [ ] Initialisation dans `infrastructure/startup/integrations.py` (Telegram : `init_telegram_bot()`), appelée par le `lifespan` de `main.py`, qui reste le seul point d'ordonnancement (ADR-123)
- [ ] Une ressource globale au bot — un webhook, une connexion — est posée par le seul leader du planificateur (`infrastructure/startup/schedulers.py`, ADR-304), jamais par chaque worker
- [ ] Arrêt dans `infrastructure/startup/shutdown.py` : un worker qui s'arrête ne retire pas une ressource dont les autres se servent

---

## Phase 9 : Langues

- [ ] Messages du bot et libellés des boutons dans les six langues (fr, en, es, de, it, zh-CN) ; modèles : `TELEGRAM_BOT_MESSAGES` et `HITL_BUTTON_LABELS`. Une table indexée par langue porte exactement ces six codes (`test_language_table_completeness_guard.py`)
- [ ] La langue passe par `resolve_language()` et `normalize_language()`, jamais par une valeur par défaut écrite en dur (ADR-323)
- [ ] Écran des réglages : chaque clé ajoutée existe dans les six fichiers de traduction du site (parité stricte, vérifiée au commit)

---

## Phase 10 : Écran

- [ ] `ChannelSettings.tsx` : état vide, liaison, bascule et suppression pour le nouveau canal
- [ ] `useChannelBindings.ts` : types et appels du nouveau canal
- [ ] FAQ : le canal y est décrit, dans les six langues (`apps/web/src/components/faq/faq-sections.ts`)

---

## Phase 11 : Observabilité et journaux

- [ ] Réutiliser les métriques de `metrics_channels.py` avec le label `channel_type` du canal ; ne pas créer de métrique par canal (une métrique que ni panneau ni alerte ne lit est refusée par `test_metric_coverage_ratchet_guard.py`)
- [ ] Rien de ce qu'une personne a écrit, ni nom ni identifiant personnel, au-dessus de DEBUG (ADR-317)
- [ ] La bibliothèque du fournisseur ne journalise ni jeton ni secret (Telegram : le journal `telegram` est limité à INFO)

---

## Phase 12 : Tests

- [ ] Tests unitaires en miroir du code : `apps/api/tests/unit/infrastructure/channels/votre_canal/`, et les suites du domaine dans `apps/api/tests/unit/domains/channels/`
- [ ] Envoi : message, découpe, refus du fournisseur, bot bloqué
- [ ] Entrée : secret absent, secret faux, secret juste ; livraison rejouée écartée
- [ ] Liaison : code valide, code expiré, tentatives épuisées, compte désactivé
- [ ] Question : bouton, double appui, question expirée
- [ ] Notification : envoyée, refusée
- [ ] Aucune suite ne se désactive faute de clé du fournisseur : le fournisseur est simulé (ADR-155)

---

## Phase 13 : Documentation

- [ ] [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md) : flux, réglages, et section « Ajout d'un Nouveau Canal » — en retirer ce qui a été généralisé
- [ ] Un guide du canal, sur le modèle de [GUIDE_TELEGRAM_INTEGRATION.md](../guides/GUIDE_TELEGRAM_INTEGRATION.md), écrit en anglais comme tout nouveau document
- [ ] [INDEX.md](../INDEX.md) ; un ADR si une décision d'architecture est prise (transport, généralisation du domaine)
- [ ] Cartes vivantes : un nouvel ADR ou un nouveau module d'infrastructure doit y figurer (`task docs:maps`, procédure dans [docs/maps/README.md](../maps/README.md))
- [ ] `task lint:docs`

---

## Validation finale

- [ ] Phase 0 faite : plus aucun import du paquet Telegram dans `domains/channels/`
- [ ] Envoi, entrée, liaison, questions et notifications fonctionnent sur le nouveau canal, et toujours sur Telegram
- [ ] `task lint`, `task test:backend:unit:fast`, `task test:frontend`
- [ ] Preuve de bout en bout sur un compte de test du canal : liaison, message, question, notification

**Date de complétion** : _________________________
**Notes** : _________________________

---

## Références

- `domains/channels/abstractions.py` — interfaces génériques
- `infrastructure/channels/telegram/` — implémentation de référence
- [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md) — document technique, état du domaine
- [GUIDE_TELEGRAM_INTEGRATION.md](../guides/GUIDE_TELEGRAM_INTEGRATION.md) — guide pratique Telegram
