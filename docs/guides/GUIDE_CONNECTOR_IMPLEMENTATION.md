# Guide d'Implémentation des Connecteurs

**Version** : 1.0
**Dernière mise à jour** : 2025-12-27
**Statut** : ✅ Stable

Ce guide explique comment implémenter de nouveaux connecteurs dans LIA. Trois types de connecteurs sont supportés :

1. **Connecteurs OAuth** (ex: Google Gmail, Google Contacts)
2. **Connecteurs API Key** (ex: OpenAI, Anthropic, services tiers)
3. **Connecteurs Hybrid** (ex: Philips Hue — local API key for LAN control + remote OAuth2 for cloud access)

---

## Table des Matières

- [Architecture Générale](#architecture-générale)
- [Connecteurs API Key](#connecteurs-api-key)
  - [Quand utiliser](#quand-utiliser-api-key)
  - [Étapes d'implémentation](#étapes-dimplémentation-api-key)
  - [Exemple complet](#exemple-complet-api-key)
  - [Sécurité](#sécurité-api-key)
- [Connecteurs Google OAuth](#connecteurs-google-oauth)
  - [Quand utiliser](#quand-utiliser-oauth)
  - [Étapes d'implémentation](#étapes-dimplémentation-oauth)
  - [Exemple complet](#exemple-complet-oauth)
  - [Flow PKCE](#flow-pkce)
- [Bonnes Pratiques](#bonnes-pratiques)
- [Tests](#tests)

---

## Architecture Générale

```
apps/api/src/domains/connectors/
├── clients/
│   ├── base_api_key_client.py    # Classe abstraite pour API Key
│   ├── base_google_client.py     # Classe abstraite pour Google OAuth
│   ├── google_gmail_client.py    # Implémentation Gmail
│   ├── google_people_client.py   # Implémentation Contacts
│   └── philips_hue_client.py     # Implémentation Philips Hue (hybrid: API key + OAuth)
├── models.py                      # ConnectorType enum, modèle DB
├── schemas.py                     # Pydantic schemas
├── service.py                     # Business logic
├── repository.py                  # Data access
└── router.py                      # API endpoints
```

---

## Connecteurs API Key

### Quand utiliser API Key

- Services utilisant des clés API statiques
- Pas de flow OAuth nécessaire
- L'utilisateur obtient une clé depuis le dashboard du service
- Exemples : OpenAI, Anthropic, Stripe, SendGrid

### Étapes d'implémentation API Key

#### 1. Ajouter le ConnectorType

```python
# models.py
class ConnectorType(str, enum.Enum):
    # ... existing types ...
    OPENAI = "openai"
    STRIPE = "stripe"
```

#### 2. Créer le Client

```python
# clients/openai_client.py
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.models import ConnectorType

class OpenAIClient(BaseAPIKeyClient):
    """OpenAI API client."""

    connector_type = ConnectorType.OPENAI
    api_base_url = "https://api.openai.com/v1"
    auth_header_name = "Authorization"
    auth_header_prefix = "Bearer"

    async def validate_api_key(self) -> bool:
        """Validate key by calling models endpoint."""
        try:
            result = await self._make_request("GET", "/models", max_retries=1)
            return "data" in result
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models."""
        result = await self._make_request("GET", "/models")
        return [m["id"] for m in result.get("data", [])]
```

#### 3. Configurer l'Auth (options)

**Header Authentication (défaut)** :
```python
auth_header_name = "Authorization"
auth_header_prefix = "Bearer"  # Résultat: "Authorization: Bearer <key>"
```

**Sans préfixe** :
```python
auth_header_name = "X-API-Key"
auth_header_prefix = ""  # Résultat: "X-API-Key: <key>"
```

**Query Parameter** :
```python
auth_method = "query"
auth_query_param = "api_key"  # Résultat: ?api_key=<key>
```

### Exemple complet API Key

```python
# clients/stripe_client.py
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials

class StripeClient(BaseAPIKeyClient):
    """Stripe API client with API key authentication."""

    connector_type = ConnectorType.STRIPE
    api_base_url = "https://api.stripe.com/v1"
    auth_header_name = "Authorization"
    auth_header_prefix = "Bearer"

    async def validate_api_key(self) -> bool:
        """Validate by fetching account info."""
        try:
            await self._make_request("GET", "/account", max_retries=1)
            return True
        except Exception:
            return False

    async def list_customers(self, limit: int = 10) -> list[dict]:
        """List customers."""
        result = await self._make_request(
            "GET",
            "/customers",
            params={"limit": limit}
        )
        return result.get("data", [])

    async def create_customer(self, email: str, name: str) -> dict:
        """Create a new customer."""
        return await self._make_request(
            "POST",
            "/customers",
            json_data={"email": email, "name": name}
        )
```

**Utilisation** :
```python
# Dans un agent ou service
from src.domains.connectors.clients.stripe_client import StripeClient

async def process_with_stripe(user_id: UUID, connector_service):
    # Get credentials
    credentials = await connector_service.get_api_key_credentials(
        user_id, ConnectorType.STRIPE
    )

    if not credentials:
        raise ValueError("Stripe not configured")

    # Create client
    client = StripeClient(
        user_id=user_id,
        credentials=credentials,
        rate_limit_per_second=25,  # Stripe limit
    )

    try:
        customers = await client.list_customers()
        return customers
    finally:
        await client.close()
```

### Sécurité API Key

#### Stockage

- Les clés sont **chiffrées avec Fernet** avant stockage
- La clé Fernet est dans `FERNET_KEY` (env var)
- Jamais de clé en clair dans les logs

```python
# Encryption automatique dans le service
encrypted = encrypt_data(credentials.model_dump_json())
connector.credentials_encrypted = encrypted

# Decryption
decrypted = decrypt_data(connector.credentials_encrypted)
credentials = APIKeyCredentials.model_validate_json(decrypted)
```

#### Masquage pour logs/UI

```python
def _mask_api_key(self, key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"
# "sk-proj-abcdefghijklmnop" -> "sk-p...mnop"
```

#### Frontend

- Input type `password` par défaut
- Toggle pour afficher temporairement
- Validation côté client ET serveur
- Jamais stocké dans le state global

---

## Connecteurs Google OAuth

### Quand utiliser OAuth

- APIs Google (Gmail, Drive, Calendar, Contacts)
- Besoin d'accès au compte utilisateur
- Scopes spécifiques requis
- Token refresh automatique

### Étapes d'implémentation OAuth

#### 1. Ajouter le ConnectorType

```python
# models.py
class ConnectorType(str, enum.Enum):
    GOOGLE_DRIVE = "google_drive"
    GOOGLE_TASKS = "google_tasks"
```

#### 2. Définir les Scopes

```python
# schemas.py
GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
```

#### 3. Créer le Client

```python
# clients/google_drive_client.py
from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.models import ConnectorType

class GoogleDriveClient(BaseGoogleClient):
    """Google Drive API client."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    api_base_url = "https://www.googleapis.com/drive/v3"

    async def list_files(self, page_size: int = 100) -> list[dict]:
        """List files in Drive."""
        result = await self._make_request(
            "GET",
            "/files",
            params={
                "pageSize": page_size,
                "fields": "files(id,name,mimeType,modifiedTime)"
            }
        )
        return result.get("files", [])

    async def get_file(self, file_id: str) -> dict:
        """Get file metadata."""
        return await self._make_request(
            "GET",
            f"/files/{file_id}",
            params={"fields": "*"}
        )
```

#### 4. Créer le Provider OAuth

```python
# src/core/oauth/providers/google.py (ajouter méthode)
@classmethod
def for_drive(cls, settings: Settings) -> "GoogleOAuthProvider":
    """Create provider for Google Drive."""
    from src.domains.connectors.schemas import GOOGLE_DRIVE_SCOPES
    return cls(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=f"{settings.api_url}/api/v1/connectors/google-drive/callback",
        scopes=GOOGLE_DRIVE_SCOPES,
    )
```

#### 5. Ajouter les Endpoints

```python
# router.py
@router.get("/google-drive/authorize")
async def initiate_google_drive_oauth(...):
    service = ConnectorService(db)
    return await service.initiate_google_drive_oauth(user_id)

@router.get("/google-drive/callback")
async def google_drive_oauth_callback(code: str, state: str, ...):
    service = ConnectorService(db)
    connector = await service.handle_google_drive_callback_stateless(code, state)
    return RedirectResponse(...)
```

#### 6. Ajouter les méthodes Service

```python
# service.py
async def initiate_google_drive_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
    redis = await get_redis_session()
    session_service = SessionService(redis)

    from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler

    provider = GoogleOAuthProvider.for_drive(settings)
    flow_handler = OAuthFlowHandler(provider, session_service)

    auth_url, state = await flow_handler.initiate_flow(
        additional_params={"access_type": "offline", "prompt": "consent"},
        metadata={
            FIELD_USER_ID: str(user_id),
            FIELD_CONNECTOR_TYPE: ConnectorType.GOOGLE_DRIVE.value,
        },
    )

    return ConnectorOAuthInitiate(authorization_url=auth_url, state=state)

async def handle_google_drive_callback_stateless(
    self, code: str, state: str
) -> ConnectorResponse:
    from src.core.oauth import GoogleOAuthProvider

    return await self._handle_oauth_connector_callback_stateless(
        code=code,
        state=state,
        connector_type=ConnectorType.GOOGLE_DRIVE,
        provider_factory_method=GoogleOAuthProvider.for_drive,
        default_scopes=GOOGLE_DRIVE_SCOPES,
    )
```

### Flow PKCE

Tous les connecteurs OAuth utilisent **PKCE** (Proof Key for Code Exchange) :

1. **Initiation** : Génération de `code_verifier` et `code_challenge`
2. **Authorize** : Envoi du `code_challenge` à Google
3. **Callback** : Échange du `code` avec le `code_verifier`

C'est géré automatiquement par `OAuthFlowHandler`.

### Exemple complet OAuth

Voir les implémentations existantes :
- `clients/google_gmail_client.py`
- `clients/google_people_client.py`

---

## Bonnes Pratiques

### Rate Limiting

```python
# Configurer selon les limites du service
client = StripeClient(
    user_id=user_id,
    credentials=credentials,
    rate_limit_per_second=25,  # Stripe: 25/s en test, 100/s en prod
)
```

### Gestion des erreurs

```python
async def safe_operation(client):
    try:
        return await client.list_items()
    except HTTPException as e:
        if e.status_code == 401:
            # Clé invalide ou expirée
            logger.error("auth_failed", ...)
        elif e.status_code == 429:
            # Rate limit (déjà géré par retry, mais informer l'user)
            logger.warning("rate_limited", ...)
        raise
    finally:
        await client.close()
```

### Cleanup

**Toujours fermer le client** :
```python
try:
    result = await client.do_something()
finally:
    await client.close()
```

Ou utiliser un context manager :
```python
async with client:  # Si implémenté
    result = await client.do_something()
```

### Logs

```python
logger.info(
    "connector_operation_success",
    user_id=str(self.user_id),
    connector_type=self.connector_type.value,
    operation="list_items",
    items_count=len(result),
)

# JAMAIS logger la clé complète
logger.debug(
    "using_api_key",
    masked_key=self._mask_api_key(self.credentials.api_key),
)
```

---

## Tests

### Tests Unitaires

```python
# tests/unit/connectors/test_my_client.py
class TestMyClient:
    @pytest.mark.asyncio
    async def test_list_items(self):
        credentials = APIKeyCredentials(api_key="test-key-12345678")
        client = MyClient(user_id=uuid4(), credentials=credentials)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": [...]}

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.list_items()

        assert len(result) == expected
        await client.close()
```

### Tests d'Intégration

```python
# tests/integration/test_connector_activation.py
@pytest.mark.integration
class TestAPIKeyActivation:
    @pytest.mark.asyncio
    async def test_activate_api_key_connector(
        self, async_client, authenticated_client
    ):
        client, user = authenticated_client

        response = await client.post(
            "/api/v1/connectors/api-key/activate",
            json={
                "api_key": "sk-test-valid-key-12345678",
                "connector_type": "openai",
                "key_name": "Test Key",
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["connector_type"] == "openai"
        assert data["status"] == "active"
```

---

## Checklist d'Implémentation

### API Key Connector

- [ ] Ajouter `ConnectorType` dans `models.py`
- [ ] Créer client héritant de `BaseAPIKeyClient`
- [ ] Implémenter `validate_api_key()` (optionnel mais recommandé)
- [ ] Implémenter les méthodes métier
- [ ] Ajouter le label dans `CONNECTOR_LABELS` (frontend)
- [ ] Ajouter les traductions i18n
- [ ] Écrire les tests unitaires
- [ ] Documenter les rate limits du service

### OAuth Connector

- [ ] Ajouter `ConnectorType` dans `models.py`
- [ ] Définir les scopes dans `schemas.py`
- [ ] Créer client héritant de `BaseGoogleClient`
- [ ] Ajouter provider factory method
- [ ] Ajouter endpoints `authorize` et `callback`
- [ ] Ajouter méthodes service `initiate_*` et `handle_*_callback`
- [ ] Mettre à jour `CONNECTOR_LABELS` (frontend)
- [ ] Ajouter les traductions i18n
- [ ] Écrire les tests unitaires et d'intégration
- [ ] Tester le flow complet (authorize → callback → use)

---

## Support

Pour toute question :
- Voir les implémentations existantes comme référence
- Consulter les tests pour des exemples d'utilisation
- Ouvrir une issue avec le tag `connector`
