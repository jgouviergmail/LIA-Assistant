# Guide FCM Push Notifications

> Guide pratique pour implémenter et gérer les notifications push avec Firebase Cloud Messaging dans LIA

**Version**: 1.0
**Date**: 2025-12-28
**ADR**: [ADR-051: Reminder & Notification System](../architecture/ADR-051-Reminder-Notification-System.md)

---

## 📋 Table des Matières

- [Introduction](#introduction)
- [Architecture](#architecture)
- [Configuration Firebase](#configuration-firebase)
- [Modèle de Données](#modèle-de-données)
- [Enregistrement Token](#enregistrement-token)
- [Envoi de Notifications](#envoi-de-notifications)
- [Gestion des Tokens Invalides](#gestion-des-tokens-invalides)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Introduction

### Qu'est-ce que FCM ?

**Firebase Cloud Messaging (FCM)** est le service de notifications push de Google. Il permet d'envoyer des messages vers :
- **Android** : Notifications natives
- **iOS** : Via APNs (Apple Push Notification service)
- **Web** : Service Workers

### Cas d'Usage dans LIA

- **Rappels** : Notifications personnalisées via LLM
- **Alertes système** : Connexions OAuth expirées
- **Messages temps-réel** : Complément au SSE

> **Note multi-canal (v6.2)** : FCM est un des canaux de livraison du `NotificationDispatcher`. Depuis evolution F3, les notifications sont aussi envoyées via les canaux de messagerie externes liés par l'utilisateur (Telegram, etc.). Voir [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md) et [NOTIFICATIONS_FLOW.md](../technical/NOTIFICATIONS_FLOW.md) pour le pipeline complet.

### Dépendances

```toml
# pyproject.toml
[project.dependencies]
firebase-admin = "6.5.0"
```

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI)                          │
│                                                                     │
│  ┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐   │
│  │  Reminder   │───▶│ FCMNotification  │───▶│ Firebase Admin  │   │
│  │  Service    │    │    Service       │    │      SDK        │   │
│  └─────────────┘    └──────────────────┘    └────────┬────────┘   │
│                              │                        │            │
│                              ▼                        │            │
│                     ┌────────────────┐               │            │
│                     │ UserFCMToken   │               │            │
│                     │    (DB)        │               │            │
│                     └────────────────┘               │            │
└──────────────────────────────────────────────────────┼────────────┘
                                                       │
                                                       ▼
                                        ┌──────────────────────────┐
                                        │   Firebase Cloud         │
                                        │   Messaging Server       │
                                        └──────────────┬───────────┘
                                                       │
                    ┌──────────────────────────────────┼────────────────────┐
                    │                                  │                    │
                    ▼                                  ▼                    ▼
            ┌──────────────┐                 ┌──────────────┐      ┌──────────────┐
            │   Android    │                 │     iOS      │      │     Web      │
            │   Device     │                 │   Device     │      │   Browser    │
            └──────────────┘                 └──────────────┘      └──────────────┘
```

---

## ⚙️ Configuration Firebase

### Étape 1 : Créer un Projet Firebase

1. Aller sur [Firebase Console](https://console.firebase.google.com/)
2. Créer un nouveau projet ou utiliser un existant
3. Activer Cloud Messaging

### Étape 2 : Générer la Clé de Service

1. **Project Settings** → **Service accounts**
2. Cliquer **Generate new private key**
3. Télécharger le fichier JSON

### Étape 3 : Configurer l'Application

```python
# apps/api/src/core/config/notifications.py
from pydantic_settings import BaseSettings
from pydantic import Field

class NotificationsSettings(BaseSettings):
    """FCM Push Notification configuration."""

    # Path to Firebase service account JSON
    firebase_credentials_path: str = Field(
        default="config/firebase-service-account.json",
        description="Path to Firebase service account JSON file"
    )

    # Default notification settings
    fcm_default_ttl: int = Field(
        default=86400,
        description="Time-to-live for FCM messages in seconds (24h)"
    )

    fcm_android_priority: str = Field(
        default="high",
        description="Android notification priority (high/normal)"
    )

    fcm_enabled: bool = Field(
        default=True,
        description="Enable/disable FCM notifications"
    )
```

### Étape 4 : Initialiser Firebase Admin SDK

```python
# apps/api/src/infrastructure/notifications/firebase_init.py
import firebase_admin
from firebase_admin import credentials, messaging
from pathlib import Path
import structlog

logger = structlog.get_logger()

_firebase_app = None

def initialize_firebase():
    """Initialize Firebase Admin SDK (singleton)."""
    global _firebase_app

    if _firebase_app:
        return _firebase_app

    cred_path = Path(settings.firebase_credentials_path)

    if not cred_path.exists():
        logger.warning("firebase_credentials_not_found", path=str(cred_path))
        return None

    try:
        cred = credentials.Certificate(str(cred_path))
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("firebase_initialized")
        return _firebase_app

    except Exception as e:
        logger.exception("firebase_init_failed", error=str(e))
        return None

def get_firebase_app():
    """Get Firebase app instance."""
    return _firebase_app or initialize_firebase()
```

---

## 📊 Modèle de Données

### Table UserFCMToken

```python
# apps/api/src/domains/notifications/models.py
from sqlalchemy import Column, String, ForeignKey, Enum, DateTime
from sqlalchemy.dialects.postgresql import UUID
from src.core.database import Base
import enum

class DevicePlatform(str, enum.Enum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"

class UserFCMToken(Base):
    """Stores FCM tokens for push notifications."""

    __tablename__ = "user_fcm_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token = Column(String(512), nullable=False, unique=True)
    platform = Column(Enum(DevicePlatform), nullable=False)
    device_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(UTC))
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_user_fcm_tokens_user_id", "user_id"),
    )
```

### Migration Alembic

```python
# alembic/versions/2025_12_28_xxxx_add_user_fcm_tokens.py
def upgrade():
    op.create_table(
        "user_fcm_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("token", sa.String(512), unique=True, nullable=False),
        sa.Column("platform", sa.Enum("android", "ios", "web", name="deviceplatform")),
        sa.Column("device_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_fcm_tokens_user_id", "user_fcm_tokens", ["user_id"])

def downgrade():
    op.drop_table("user_fcm_tokens")
```

---

## 📱 Enregistrement Token

### API Endpoint

```python
# apps/api/src/api/v1/notifications.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/notifications", tags=["notifications"])

class RegisterFCMTokenRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=512)
    platform: DevicePlatform
    device_name: str | None = Field(None, max_length=255)

class RegisterFCMTokenResponse(BaseModel):
    success: bool
    message: str

@router.post("/fcm/register", response_model=RegisterFCMTokenResponse)
async def register_fcm_token(
    request: RegisterFCMTokenRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Register FCM token for push notifications.

    Called by mobile/web app after getting token from Firebase SDK.
    """
    service = FCMNotificationService(db)

    result = await service.register_token(
        user_id=user.id,
        token=request.token,
        platform=request.platform,
        device_name=request.device_name,
    )

    return RegisterFCMTokenResponse(
        success=result,
        message="Token registered successfully" if result else "Token registration failed",
    )

@router.delete("/fcm/unregister")
async def unregister_fcm_token(
    token: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db_session),
):
    """Unregister FCM token (logout, uninstall)."""
    service = FCMNotificationService(db)
    await service.unregister_token(user.id, token)
    return {"success": True}
```

### Service d'Enregistrement

```python
# apps/api/src/domains/notifications/service.py
from sqlalchemy import select, delete
from datetime import datetime, UTC

class FCMNotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_token(
        self,
        user_id: UUID,
        token: str,
        platform: DevicePlatform,
        device_name: str | None = None,
    ) -> bool:
        """
        Register or update FCM token.

        Uses UPSERT to handle re-registration.
        """
        try:
            # Check if token exists for another user
            existing = await self._get_token_by_value(token)

            if existing:
                if existing.user_id != user_id:
                    # Token transferred to new user - delete old
                    await self.db.delete(existing)
                else:
                    # Same user, update last_used
                    existing.last_used_at = datetime.now(UTC)
                    existing.platform = platform
                    existing.device_name = device_name
                    await self.db.commit()
                    return True

            # Create new token
            new_token = UserFCMToken(
                user_id=user_id,
                token=token,
                platform=platform,
                device_name=device_name,
            )
            self.db.add(new_token)
            await self.db.commit()

            logger.info(
                "fcm_token_registered",
                user_id=str(user_id),
                platform=platform.value,
            )
            return True

        except Exception as e:
            logger.exception("fcm_token_registration_failed", error=str(e))
            await self.db.rollback()
            return False

    async def get_user_tokens(self, user_id: UUID) -> list[UserFCMToken]:
        """Get all FCM tokens for a user."""
        stmt = select(UserFCMToken).where(UserFCMToken.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
```

---

## 📤 Envoi de Notifications

### Service d'Envoi

```python
# apps/api/src/domains/notifications/service.py
from firebase_admin import messaging
from dataclasses import dataclass

@dataclass
class SendResult:
    success_count: int
    failure_count: int
    failed_tokens: list[str]

class FCMNotificationService:
    # ... (register methods above)

    async def send_notification(
        self,
        user_id: UUID,
        title: str,
        body: str,
        data: dict | None = None,
        image_url: str | None = None,
    ) -> SendResult:
        """
        Send push notification to all user devices.

        Args:
            user_id: Target user
            title: Notification title
            body: Notification body
            data: Optional data payload (for app handling)
            image_url: Optional image URL

        Returns:
            SendResult with success/failure counts
        """
        tokens = await self.get_user_tokens(user_id)

        if not tokens:
            logger.info("no_fcm_tokens", user_id=str(user_id))
            return SendResult(success_count=0, failure_count=0, failed_tokens=[])

        # Build notification
        notification = messaging.Notification(
            title=title,
            body=body,
            image=image_url,
        )

        # Build messages for each token
        messages = []
        for token_record in tokens:
            message = messaging.Message(
                notification=notification,
                data=data or {},
                token=token_record.token,
                android=self._android_config(token_record.platform),
                webpush=self._webpush_config() if token_record.platform == DevicePlatform.WEB else None,
                apns=self._apns_config() if token_record.platform == DevicePlatform.IOS else None,
            )
            messages.append((token_record, message))

        # Send batch
        return await self._send_batch(messages)

    def _android_config(self, platform: DevicePlatform) -> messaging.AndroidConfig | None:
        if platform != DevicePlatform.ANDROID:
            return None

        return messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                icon="ic_notification",
                color="#4A90D9",
                channel_id="reminders",
            ),
        )

    def _webpush_config(self) -> messaging.WebpushConfig:
        return messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                icon="/icons/notification-icon.png",
            ),
        )

    def _apns_config(self) -> messaging.APNSConfig:
        return messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(),
                    sound="default",
                    badge=1,
                ),
            ),
        )

    async def _send_batch(
        self,
        messages: list[tuple[UserFCMToken, messaging.Message]],
    ) -> SendResult:
        """Send batch of messages and handle responses."""
        success_count = 0
        failure_count = 0
        failed_tokens = []

        for token_record, message in messages:
            try:
                messaging.send(message)
                success_count += 1

                # Update last_used
                token_record.last_used_at = datetime.now(UTC)

            except messaging.UnregisteredError:
                # Token invalid - mark for deletion
                failure_count += 1
                failed_tokens.append(token_record.token)
                await self._delete_invalid_token(token_record)

            except Exception as e:
                failure_count += 1
                logger.warning(
                    "fcm_send_failed",
                    token=token_record.token[:20] + "...",
                    error=str(e),
                )

        await self.db.commit()

        return SendResult(
            success_count=success_count,
            failure_count=failure_count,
            failed_tokens=failed_tokens,
        )
```

### Envoi pour Rappels (avec LLM)

```python
# apps/api/src/infrastructure/scheduler/reminder_notification.py

async def send_reminder_notification(
    user_id: UUID,
    reminder: Reminder,
    personalized_message: str,
):
    """Send FCM notification for a reminder."""

    async with get_db_context() as db:
        service = FCMNotificationService(db)

        result = await service.send_notification(
            user_id=user_id,
            title="Rappel",
            body=personalized_message,
            data={
                "type": "reminder",
                "reminder_id": str(reminder.id),
                "original_message": reminder.original_message,
            },
        )

        # Track metrics
        if result.success_count > 0:
            reminder_notifications_sent_total.inc()
        else:
            reminder_notifications_failed_total.inc()

        return result
```

---

## 🗑️ Gestion des Tokens Invalides

### Cleanup Automatique

```python
# apps/api/src/domains/notifications/service.py

async def _delete_invalid_token(self, token_record: UserFCMToken):
    """Delete invalid token from database."""
    await self.db.delete(token_record)
    logger.info(
        "fcm_token_deleted",
        user_id=str(token_record.user_id),
        reason="unregistered",
    )

async def cleanup_stale_tokens(self, days_inactive: int = 30):
    """
    Remove tokens not used for N days.

    Run periodically via background job.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days_inactive)

    stmt = delete(UserFCMToken).where(
        UserFCMToken.last_used_at < cutoff
    )
    result = await self.db.execute(stmt)
    await self.db.commit()

    logger.info("fcm_tokens_cleaned", deleted=result.rowcount)
```

### Erreurs Firebase Communes

| Erreur | Cause | Action |
|--------|-------|--------|
| `UnregisteredError` | App désinstallée | Supprimer token |
| `InvalidArgumentError` | Token malformé | Supprimer token |
| `SenderIdMismatchError` | Mauvais projet Firebase | Vérifier config |
| `QuotaExceededError` | Rate limit dépassé | Retry avec backoff |

---

## 🧪 Testing

### Mock Firebase pour Tests

```python
# tests/conftest.py
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_firebase():
    """Mock Firebase Admin SDK."""
    with patch("firebase_admin.messaging") as mock_messaging:
        mock_messaging.send.return_value = "mock_message_id"
        yield mock_messaging

@pytest.fixture
def mock_firebase_error():
    """Mock Firebase with UnregisteredError."""
    with patch("firebase_admin.messaging") as mock_messaging:
        from firebase_admin.exceptions import UnregisteredError
        mock_messaging.send.side_effect = UnregisteredError("Token invalid")
        yield mock_messaging
```

### Test Unitaire

```python
# tests/unit/domains/notifications/test_fcm_service.py
import pytest
from uuid import uuid4

@pytest.mark.asyncio
async def test_send_notification_success(mock_firebase, test_db_session):
    """Test successful notification send."""
    user_id = uuid4()

    # Create test token
    token = UserFCMToken(
        user_id=user_id,
        token="test_token_123",
        platform=DevicePlatform.ANDROID,
    )
    test_db_session.add(token)
    await test_db_session.commit()

    service = FCMNotificationService(test_db_session)
    result = await service.send_notification(
        user_id=user_id,
        title="Test",
        body="Test message",
    )

    assert result.success_count == 1
    assert result.failure_count == 0
    mock_firebase.send.assert_called_once()

@pytest.mark.asyncio
async def test_invalid_token_cleanup(mock_firebase_error, test_db_session):
    """Test invalid tokens are deleted."""
    user_id = uuid4()

    token = UserFCMToken(
        user_id=user_id,
        token="invalid_token",
        platform=DevicePlatform.ANDROID,
    )
    test_db_session.add(token)
    await test_db_session.commit()

    service = FCMNotificationService(test_db_session)
    result = await service.send_notification(
        user_id=user_id,
        title="Test",
        body="Test message",
    )

    assert result.failure_count == 1
    assert "invalid_token" in result.failed_tokens

    # Token should be deleted
    remaining = await service.get_user_tokens(user_id)
    assert len(remaining) == 0
```

### Test d'Intégration (avec Firebase Emulator)

```bash
# Démarrer Firebase Emulator
firebase emulators:start --only messaging

# Exporter variable
export FIREBASE_EMULATOR_HOST="localhost:9099"
```

```python
# tests/integration/notifications/test_fcm_integration.py
import pytest
import os

@pytest.mark.skipif(
    not os.getenv("FIREBASE_EMULATOR_HOST"),
    reason="Firebase Emulator not running"
)
@pytest.mark.asyncio
@pytest.mark.integration
async def test_fcm_with_emulator(test_db_session):
    """Integration test with Firebase Emulator."""
    # Real Firebase calls but to emulator
    service = FCMNotificationService(test_db_session)
    # ...
```

---

## 🔧 Troubleshooting

### Notification non reçue

1. **Vérifier le token** :
   ```python
   tokens = await service.get_user_tokens(user_id)
   print(f"Tokens: {len(tokens)}")
   ```

2. **Vérifier les credentials Firebase** :
   ```bash
   cat config/firebase-service-account.json | jq '.project_id'
   ```

3. **Vérifier les logs** :
   ```bash
   docker logs lia-api-1 2>&1 | grep "fcm"
   ```

### Token toujours invalide

1. **Frontend** : Vérifier que le token est généré après permissions
2. **Backend** : Vérifier que le token n'est pas tronqué
3. **Firebase Console** : Vérifier que Cloud Messaging est activé

### Rate Limiting

Firebase impose des limites :
- **1000 messages/seconde** par projet
- **200 messages/minute** par topic

**Solution** : Batch + backoff
```python
async def send_batch_with_backoff(messages, batch_size=500):
    for batch in chunks(messages, batch_size):
        await send_batch(batch)
        await asyncio.sleep(0.1)  # Rate limit safety
```

---

## Architecture Multi-Canal (v6.2+)

### FCM dans le contexte multi-canal

Depuis la v6.2, FCM est **un canal parmi d'autres** dans l'architecture de notifications. Le `NotificationDispatcher` (ou `BroadcastService`) orchestre la livraison multi-canal :

```
NotificationDispatcher
    ├── Archive en DB (toujours)
    ├── SSE real-time (toujours)
    ├── FCM Push (si FCM_NOTIFICATIONS_ENABLED et push active pour l'utilisateur)
    └── Telegram (si CHANNELS_ENABLED et utilisateur lie a Telegram)
```

### Sources de notifications

FCM push est utilise par **3 sources de notifications** :

| Source | Description | Feature Flag |
|--------|-------------|-------------|
| **Reminders** | Rappels ponctuels utilisateur | Aucun (toujours actif) |
| **Interests** | Notifications centres d'interet proactives | Aucun (toujours actif) |
| **Heartbeat Autonome** | Notifications proactives LLM-driven | `HEARTBEAT_ENABLED` |

### Configuration Feature Flags

```bash
# Activer FCM Push (global)
FCM_NOTIFICATIONS_ENABLED=true

# Activer Telegram comme canal supplementaire
CHANNELS_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# Activer Heartbeat comme source supplementaire
HEARTBEAT_ENABLED=true
```

### Controle Utilisateur

Chaque utilisateur peut controler independamment :
- **Push notifications** (FCM) : activable/desactivable dans Parametres
- **Telegram notifications** : activable/desactivable dans Parametres > Telegram
- **Heartbeat push** : activable/desactivable separement (`heartbeat_push_enabled`)

> Voir [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md) pour la documentation Telegram complete.
> Voir [HEARTBEAT_AUTONOME.md](../technical/HEARTBEAT_AUTONOME.md) pour la documentation Heartbeat complete.

---

## Ressources

### Documentation

- [Firebase Cloud Messaging](https://firebase.google.com/docs/cloud-messaging)
- [Firebase Admin Python SDK](https://firebase.google.com/docs/admin/setup)
- [ADR-051: Reminder & Notification System](../architecture/ADR-051-Reminder-Notification-System.md)
- [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md) — Multi-Channel Messaging (Telegram)
- [HEARTBEAT_AUTONOME.md](../technical/HEARTBEAT_AUTONOME.md) — Notifications proactives autonomes

### Code Source

- **Models**: `apps/api/src/domains/notifications/models.py`
- **Service**: `apps/api/src/domains/notifications/service.py`
- **API Endpoints**: `apps/api/src/api/v1/notifications.py`
- **Firebase Init**: `apps/api/src/infrastructure/notifications/firebase_init.py`
- **Config**: `apps/api/src/core/config/notifications.py`

### Frontend Integration

- **React Native** : `@react-native-firebase/messaging`
- **Web** : `firebase/messaging` + Service Worker
- **Flutter** : `firebase_messaging`

---

**Fin du guide** - FCM Push Notifications dans LIA
