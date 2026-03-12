# Migration Guide - LIA Architecture Updates

> **Version**: 1.0.1
> **Date**: 2025-12-27
> **Concerne**: Config Module Split (ADR-009), Email Domain Renaming (ADR-010)

---

## Vue d'ensemble

Ce guide documente les migrations nécessaires suite aux changements architecturaux majeurs de novembre 2025.

### Changements Majeurs

1. **ADR-009: Configuration Module Split** - Config.py monolithique → 8 modules
2. **ADR-010: Email Domain Renaming** - `gmail/` → `emails/` (multi-provider)
3. **Phase 2.4: Rate Limiting** - Redis distributed rate limiter

---

## Migration 1 : Configuration Modulaire

### Impact : ✅ Rétrocompatible 100%

**Aucun changement requis dans le code existant.**

#### Ancien Pattern (Continue de fonctionner)

```python
# ✅ Code existant - AUCUN CHANGEMENT
from src.core.config import settings

api_key = settings.openai_api_key
db_url = settings.postgres_url
redis_url = settings.redis_url
```

#### Nouveau Pattern (Optionnel - Tests unitaires)

```python
# ✅ Tests unitaires par module désormais possibles
from src.core.config.llm import LLMSettings

def test_llm_config():
    config = LLMSettings(
        openai_api_key="sk-test",
        openai_model="gpt-4"
    )
    assert config.openai_api_key == "sk-test"
```

#### Fichiers Modifiés

- ✅ `src/core/config.py` → `src/core/config/__init__.py` (composition)
- ✅ Ajouté : 7 modules (`security.py`, `database.py`, `observability.py`, etc.)
- ✅ Tests : 5 → 17 tests (coverage 45% → 72%)

#### Action Requise

**Aucune** - Import `from src.core.config import settings` continue de fonctionner identiquement.

---

## Migration 2 : Email Domain Renaming (gmail → emails)

### Impact : ⚠️ Breaking changes internes uniquement

**Code client (outils, agents) : AUCUN CHANGEMENT**

Architecture interne mise à jour pour support multi-provider (Gmail, Outlook, IMAP futur).

#### Fichiers Renommés

| Ancien | Nouveau | Type |
|--------|---------|------|
| `src/domains/agents/gmail/` | `src/domains/agents/emails/` | Directory |
| `gmail_tools.py` | `emails_tools.py` | File |
| `gmail_agent_builder.py` | `emails_agent_builder.py` | File |
| `prompts/.../gmail_agent_prompt.txt` | `prompts/.../emails_agent_prompt.txt` | File |
| `GmailHandler` | `EmailsHandler` | Class |
| `GmailFormatter` | `EmailFormatter` | Class |

#### Imports à Mettre à Jour (Si utilisés directement)

**Ancien** :
```python
# ❌ Import ancien (deprecated)
from src.domains.agents.gmail.gmail_tools import list_gmail_messages
from src.domains.agents.graphs.gmail_agent_builder import GmailAgentBuilder
```

**Nouveau** :
```python
# ✅ Import nouveau
from src.domains.agents.emails.emails_tools import list_email_messages
from src.domains.agents.graphs.emails_agent_builder import EmailsAgentBuilder
```

#### Domain Registry

**Ancien** :
```python
# domain_taxonomy.py
DOMAIN_REGISTRY = {
    "gmail": DomainConfig(
        name="gmail",
        agent_names=["gmail_agent"]
    )
}
```

**Nouveau** :
```python
# domain_taxonomy.py
DOMAIN_REGISTRY = {
    "emails": DomainConfig(  # ← Generic naming
        name="emails",
        agent_names=["emails_agent"]
    )
}
```

#### Catalogue Manifests

**Ancien** :
```python
# catalogue_manifests.py
GMAIL_AGENT_MANIFEST = AgentManifest(
    name="gmail_agent",
    tools=["list_gmail_messages", "get_gmail_details"]
)
```

**Nouveau** :
```python
# catalogue_manifests.py
EMAILS_AGENT_MANIFEST = AgentManifest(
    name="emails_agent",
    tools=["list_email_messages", "get_email_details"]
)
```

#### Router Prompts

**Ancien** :
```txt
# router_system_prompt.txt
Available domains: ["contacts", "gmail"]
```

**Nouveau** :
```txt
# router_system_prompt.txt
Available domains: ["contacts", "emails"]
```

#### Action Requise

1. ✅ **Si imports directs** : Mettre à jour imports `gmail` → `emails`
2. ✅ **Si nouveaux agents** : Utiliser `emails` comme domain (pas `gmail`)
3. ✅ **Tests** : Vérifier que domaine `"emails"` est utilisé
4. ✅ **Prompts custom** : Remplacer `gmail` → `emails`

**Note** : URLs Gmail (`https://mail.google.com/...`) et scopes OAuth (`gmail.readonly`) restent inchangés (provider-specific, pas domain).

---

## Migration 3 : Rate Limiting Distribué

### Impact : ⚠️ Nouveau connector clients doivent injecter rate limiter

#### Ancien Pattern (Sans Rate Limiting)

```python
# ❌ Ancien client (vulnerable)
class MyClient(BaseGoogleClient):
    def __init__(self, user_id, credentials, connector_service):
        super().__init__(user_id, credentials, connector_service)

    async def _make_request(self, url: str):
        # Pas de rate limiting ❌
        response = await self.session.get(url)
        return response.json()
```

#### Nouveau Pattern (Avec Rate Limiting)

```python
# ✅ Nouveau client (protected)
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

class MyClient(BaseGoogleClient):
    def __init__(
        self,
        user_id: UUID,
        credentials: dict,
        connector_service: ConnectorService,
        rate_limiter: RedisRateLimiter  # ← NEW
    ):
        super().__init__(user_id, credentials, connector_service)
        self.rate_limiter = rate_limiter

    async def _make_request(self, url: str):
        # Check rate limit BEFORE request
        allowed = await self.rate_limiter.acquire(
            key=f"my_api:{self.user_id}",
            max_calls=60,
            window_seconds=60
        )

        if not allowed:
            raise RateLimitExceeded("API rate limit exceeded")

        # Make request (rate limit passed)
        response = await self.session.get(url)
        return response.json()
```

#### Dependency Injection

```python
# src/api/v1/dependencies.py
from fastapi import Depends
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

async def get_rate_limiter(
    redis: Redis = Depends(get_redis_client)
) -> RedisRateLimiter:
    return RedisRateLimiter(redis=redis)
```

#### Configuration

```python
# src/core/config/security.py
class SecuritySettings(BaseSettings):
    rate_limit_per_minute: int = Field(60, env="RATE_LIMIT_PER_MINUTE")
    rate_limit_burst: int = Field(100, env="RATE_LIMIT_BURST")
    google_api_rate_limit: int = Field(60, env="GOOGLE_API_RATE_LIMIT")
```

```bash
# .env
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=100
GOOGLE_API_RATE_LIMIT=60
```

#### Action Requise

1. ✅ **Nouveaux clients** : Injecter `RedisRateLimiter` dans `__init__`
2. ✅ **Méthodes API** : Appeler `rate_limiter.acquire()` avant requête
3. ✅ **Configuration** : Ajouter rate limits dans `security.py` ou `connectors.py`
4. ✅ **Tests** : Créer tests unitaires + integration (voir `test_redis_limiter*.py`)

---

## Checklist Migration Complète

### Développeur Backend

- [ ] Vérifier imports : Aucun import direct de `src.core.config.py` (obsolète)
- [ ] Si agent custom : Renommer domaine `gmail` → `emails` si applicable
- [ ] Si nouveau client : Injecter `RedisRateLimiter`
- [ ] Tests passent : `pytest tests/unit tests/integration -v`
- [ ] Mypy OK : `mypy src/`

### Développeur Frontend

- [ ] Aucun changement requis (API endpoints inchangés)
- [ ] Tester flow email dans UI (domaine `emails` invisible côté front)

### DevOps

- [ ] Variables d'environnement : Vérifier `.env` coverage tous modules config
- [ ] Redis : Vérifier disponibilité (rate limiting requires Redis)
- [ ] Monitoring : Dashboards Grafana mis à jour (rate limit metrics)

### Documentation

- [ ] README.md : ✅ Mis à jour
- [ ] CONTRIBUTING.md : ✅ Mis à jour (structure config/)
- [ ] ARCHITECTURE.md : ✅ Mis à jour (config + rate limiting sections)
- [ ] Guides : ✅ Mis à jour (gmail → emails, config modulaire)

---

## Rollback Procedure

### Si problème avec configuration modulaire

```bash
# 1. Restore config.py backup
git checkout HEAD~1 -- src/core/config.py

# 2. Remove config/ directory
rm -rf src/core/config/

# 3. Restart services
docker-compose restart api
```

### Si problème avec email domain

```bash
# 1. Revert email domain rename
git revert <commit-sha-email-rename>

# 2. Restore domain taxonomy
git checkout HEAD~1 -- src/domains/agents/registry/domain_taxonomy.py

# 3. Restart services
docker-compose restart api
```

---

## Support & Questions

### Issues Connus

1. **Import error "cannot import settings from config.py"**
   - **Cause** : Import cache non invalidé
   - **Solution** : Restart Python interpreter, rebuild Docker images

2. **Domain "emails" not found in taxonomy**
   - **Cause** : `domain_taxonomy.py` non mis à jour
   - **Solution** : Ajouter `"emails": DomainConfig(...)` dans DOMAIN_REGISTRY

3. **Rate limiter "Redis connection refused"**
   - **Cause** : Redis non démarré
   - **Solution** : `docker-compose up -d redis`

### Ressources

- **ADR-009** : [Config Module Split](../architecture/ADR-009-Config-Module-Split.md)
- **ADR-010** : [Email Domain Renaming](../architecture/ADR-010-Email-Domain-Renaming.md)
- **RATE_LIMITING.md** : [Rate Limiting Documentation](../technical/RATE_LIMITING.md)
- **CONFIG_ARCHITECTURE.md** : [Configuration Architecture](./CONFIG_ARCHITECTURE.md)

---

**Fin du Migration Guide** - LIA Architecture Updates (Novembre 2025)
