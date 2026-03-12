# Checklist: Ajouter un Nouveau Canal de Messagerie

**Nom du Canal**: _________________________ (ex: Discord, WhatsApp, Slack)
**Developpeur**: _________________________
**Date**: _________________________
**Temps estime**: 4-8h

---

## Concepts Cles

L'architecture multi-canal de LIA repose sur des abstractions generiques :

- `BaseChannelSender` : ABC pour envoyer des messages sortants
- `BaseChannelWebhookHandler` : ABC pour traiter les messages entrants (webhook)
- `UserChannelBinding` : Modele generique de liaison utilisateur ↔ canal

L'implementation Telegram sert de reference : `infrastructure/channels/telegram/`

---

## Phase 1: Abstractions & Modeles (1h)

### 1.1 Type de canal

- [ ] **Ajouter le type de canal** dans l'enum `ChannelType` :
  ```python
  # domains/channels/models.py
  class ChannelType(str, Enum):
      TELEGRAM = "telegram"
      VOTRE_CANAL = "votre_canal"  # Ajouter ici
  ```

### 1.2 Modele de binding

- [ ] **Le modele `UserChannelBinding` est generique** — verifier qu'il supporte votre canal :
  - Champ `channel_type` : utilise l'enum `ChannelType`
  - Champ `channel_user_id` : identifiant de l'utilisateur sur le canal externe
  - Champ `metadata` : JSON pour donnees specifiques au canal (ex: chat_id pour Telegram)

- [ ] **Migration Alembic** si des champs supplementaires sont necessaires :
  ```bash
  cd apps/api
  alembic revision --autogenerate -m "add votre_canal channel support"
  ```

---

## Phase 2: Sender (Sortant) (1-2h)

### 2.1 Implementer BaseChannelSender

- [ ] **Creer le fichier sender** :
  ```
  apps/api/src/infrastructure/channels/votre_canal/
  ├── __init__.py
  ├── sender.py          # Implementation BaseChannelSender
  ├── formatter.py        # Formatage messages pour ce canal
  └── webhook.py          # Webhook handler (si entrant)
  ```

- [ ] **Implementer `sender.py`** :
  ```python
  from domains.channels.abstractions import BaseChannelSender

  class VotreCanalSender(BaseChannelSender):
      """Envoi de messages via {votre_canal}."""

      async def send_text(
          self, channel_user_id: str, text: str, **kwargs
      ) -> bool:
          """Envoie un message texte."""
          ...

      async def send_notification(
          self, channel_user_id: str, title: str, body: str, **kwargs
      ) -> bool:
          """Envoie une notification formatee."""
          ...

      async def send_hitl_approval(
          self, channel_user_id: str, plan_summary: str,
          approval_id: str, **kwargs
      ) -> bool:
          """Envoie une demande d'approbation HITL."""
          # Implementer des boutons/reactions si le canal le supporte
          ...
  ```

### 2.2 Formatter

- [ ] **Implementer le formateur** pour adapter le contenu au canal :
  - Markdown → format natif du canal
  - Troncature selon les limites du canal (ex: Telegram 4096 chars, Discord 2000 chars)
  - Gestion des medias (images, fichiers)

---

## Phase 3: Webhook Handler (Entrant) (1-2h)

### 3.1 Implementer le webhook

- [ ] **Creer `webhook.py`** :
  ```python
  from domains.channels.abstractions import BaseChannelWebhookHandler

  class VotreCanalWebhookHandler(BaseChannelWebhookHandler):
      """Traitement des messages entrants via webhook."""

      async def validate_request(self, request: Request) -> bool:
          """Valide la signature/authenticite du webhook."""
          ...

      async def handle_message(self, payload: dict) -> None:
          """Traite un message entrant."""
          # 1. Extraire le texte/media
          # 2. Trouver l'utilisateur lie (UserChannelBinding)
          # 3. Envoyer au pipeline de chat
          # 4. Retourner la reponse via sender
          ...
  ```

### 3.2 Route webhook

- [ ] **Ajouter la route webhook** dans le router channels :
  ```python
  @router.post("/webhook/votre_canal")
  async def votre_canal_webhook(request: Request):
      handler = VotreCanalWebhookHandler()
      if not await handler.validate_request(request):
          raise HTTPException(403)
      # Retourner 200 immediatement, traiter en background
      asyncio.create_task(handler.handle_message(payload))
      return {"ok": True}
  ```

---

## Phase 4: OTP Linking (30 min)

### 4.1 Flow de liaison

- [ ] **Reutiliser le systeme OTP generique** :
  ```python
  # Le flow est identique pour tous les canaux :
  # 1. User demande un code OTP dans l'app web
  # 2. User envoie le code dans le canal externe (ex: /start CODE)
  # 3. Backend valide le code et cree le UserChannelBinding
  ```

- [ ] **Implementer la commande de liaison** dans le webhook handler :
  ```python
  async def handle_link_command(self, channel_user_id: str, otp_code: str):
      # Valider le code OTP
      # Creer le UserChannelBinding
      # Envoyer message de confirmation
      ...
  ```

---

## Phase 5: Configuration (15 min)

### 5.1 Settings

- [ ] **Ajouter les settings** dans `core/config/channels.py` :
  ```python
  # Votre Canal
  votre_canal_api_key: str | None = Field(None, env="VOTRE_CANAL_API_KEY")
  votre_canal_webhook_secret: str | None = Field(None, env="VOTRE_CANAL_WEBHOOK_SECRET")
  ```

### 5.2 Feature flag

- [ ] **Le feature flag global `CHANNELS_ENABLED`** active/desactive tous les canaux
- [ ] **Ajouter un flag specifique** si necessaire :
  ```bash
  VOTRE_CANAL_ENABLED=false
  ```

### 5.3 .env

- [ ] **Documenter dans `.env.example`** :
  ```bash
  # Votre Canal
  VOTRE_CANAL_API_KEY=
  VOTRE_CANAL_WEBHOOK_SECRET=
  ```

---

## Phase 6: Integration NotificationDispatcher (15 min)

- [ ] **Ajouter le canal dans NotificationDispatcher** :
  ```python
  # domains/notifications/broadcast_service.py
  async def _send_to_channels(self, user: User, content: NotificationContent):
      # ... existing Telegram logic ...

      # Ajouter votre canal
      if user has votre_canal binding:
          sender = VotreCanalSender()
          await sender.send_notification(
              channel_user_id=binding.channel_user_id,
              title=content.title,
              body=content.body,
          )
  ```

---

## Phase 7: Tests (1h)

### 7.1 Tests unitaires

- [ ] **Test sender** :
  ```python
  async def test_send_text():
      sender = VotreCanalSender()
      result = await sender.send_text("user_123", "Hello")
      assert result is True
  ```

- [ ] **Test webhook validation** :
  ```python
  async def test_webhook_valid_signature():
      handler = VotreCanalWebhookHandler()
      assert await handler.validate_request(valid_request) is True

  async def test_webhook_invalid_signature():
      assert await handler.validate_request(invalid_request) is False
  ```

- [ ] **Test OTP linking** :
  ```python
  async def test_otp_link_success():
      # Generer OTP, valider, verifier binding
      ...
  ```

### 7.2 Tests integration

- [ ] **Test flow complet** : message entrant → traitement → reponse sortante

---

## Phase 8: Observabilite (15 min)

- [ ] **Ajouter les metriques Prometheus RED** :
  ```python
  channel_message_total = Counter(
      "channel_votre_canal_message_total",
      "Messages traites",
      ["direction", "status"],  # direction: "inbound"/"outbound"
  )

  channel_message_duration = Histogram(
      "channel_votre_canal_message_duration_seconds",
      "Duree de traitement",
  )
  ```

---

## Phase 9: Documentation (15 min)

- [ ] **Mettre a jour `docs/technical/CHANNELS_INTEGRATION.md`** avec le nouveau canal
- [ ] **Mettre a jour `CLAUDE.md`** (feature flags, types)
- [ ] **Mettre a jour `.env.example`** avec les nouvelles variables

---

## Validation Finale

- [ ] Sender implemente (send_text, send_notification, send_hitl_approval)
- [ ] Webhook handler fonctionnel (validation, traitement, reponse)
- [ ] OTP linking operationnel
- [ ] Integration NotificationDispatcher
- [ ] Tests unitaires et integration passent
- [ ] Metriques Prometheus ajoutees
- [ ] Documentation a jour

**Date de completion**: _________________________
**Notes**: _________________________

---

## References

- `domains/channels/abstractions.py` — Interfaces generiques
- `infrastructure/channels/telegram/` — Implementation de reference (Telegram)
- `docs/technical/CHANNELS_INTEGRATION.md` — Documentation technique
- `docs/guides/GUIDE_TELEGRAM_INTEGRATION.md` — Guide pratique Telegram
