# Guide Pratique : Tests et Qualité

**Version** : 1.2
**Dernière mise à jour** : 2026-03-08
**Statut** : ✅ Stable

---

## Table des matières

1. [Introduction](#introduction)
2. [Architecture de Tests](#architecture-de-tests)
3. [Configuration et Environnement](#configuration-et-environnement)
4. [Tests Unitaires](#tests-unitaires)
5. [Tests d'Intégration](#tests-dintégration)
6. [Tests End-to-End (E2E)](#tests-end-to-end-e2e)
7. [Tests d'Agents LangGraph](#tests-dagents-langgraph)
8. [Tests de Tools](#tests-de-tools)
9. [Mocking et Fixtures](#mocking-et-fixtures)
10. [Coverage et Qualité](#coverage-et-qualité)
11. [CI/CD Testing Workflow](#cicd-testing-workflow)
12. [Best Practices](#best-practices)
13. [Troubleshooting](#troubleshooting)
14. [Tests MCP (Model Context Protocol)](#tests-mcp-model-context-protocol)
15. [Tests Telegram (Multi-Channel)](#tests-telegram-multi-channel)
16. [Tests Heartbeat (Notifications Proactives)](#tests-heartbeat-notifications-proactives)
17. [Tests Scheduled Actions](#tests-scheduled-actions)
18. [Tests Frontend (Vitest)](#tests-frontend-vitest)
19. [Références](#références)

---

## Introduction

### Objectif du guide

Ce guide fournit une approche complète et pratique pour **écrire, exécuter et maintenir des tests** dans le projet LIA. Il couvre :

- **Pyramide de tests** : 86/12/2 (unit/integration/e2e)
- **Framework Pytest** : fixtures, async, parametrize, markers
- **Tests d'agents** : LangGraph, StateGraph, checkpointer
- **Tests de tools** : mocking OAuth, rate limiting, caching
- **Tests d'intégration** : PostgreSQL + Redis avec testcontainers
- **CI/CD** : GitHub Actions workflows, coverage

### Public cible

- **Développeurs backend** : écriture de tests pour FastAPI, SQLAlchemy, LangGraph
- **Développeurs agents** : tests de StateGraph, nodes, tools
- **DevOps** : configuration CI/CD, testcontainers
- **QA Engineers** : stratégies de test, coverage

### Prérequis

- **Python 3.12+** : tests backend
- **Pytest 8.3+** : framework de tests
- **Docker** : testcontainers pour PostgreSQL/Redis
- **Connaissances** : async/await, fixtures, mocking

---

## Architecture de Tests

### Pyramide de Tests (86/12/2)

LIA suit la **pyramide de tests optimisée** pour maximiser la vitesse et la fiabilité :

```
         E2E (2%)
        /
   Integration (12%)
      /
 Unit Tests (86%)
```

**Objectifs** :
- **86% Unit** : rapides (<10ms), isolation complète, pas de dépendances externes
- **12% Integration** : moyens (<500ms), bases de données réelles, Redis cache
- **2% E2E** : lents (<5s), flux complets, SSE streaming, HITL

**Rationale** :
- Unit tests : détection rapide de bugs, feedback instantané, 100% de couverture logique
- Integration tests : validation de l'intégration DB/cache/services externes
- E2E tests : validation des flux critiques utilisateur (HITL, streaming)

### Organisation des Tests

```
apps/api/tests/
├── conftest.py                     # Fixtures globales (db, Redis, users)
├── core/                           # Tests unitaires core
│   ├── test_security.py
│   ├── test_config.py
│   └── test_dependencies.py
├── domains/
│   ├── agents/
│   │   ├── test_agent_registry.py          # Unit tests
│   │   ├── test_catalogue_manifests.py
│   │   ├── services/                       # Service tests
│   │   │   ├── test_hitl_classifier.py
│   │   │   ├── test_question_generator.py
│   │   │   └── test_schema_validator.py
│   │   ├── mixins/                         # Mixin tests
│   │   │   ├── test_hitl_management_mixin.py
│   │   │   └── test_streaming_mixin.py
│   │   └── integration/                    # Integration/E2E tests
│   │       └── test_hitl_streaming_e2e.py
│   ├── auth/
│   │   ├── test_auth_service.py
│   │   └── test_jwt_tokens.py
│   └── conversations/
│       ├── test_conversation_service.py
│       └── test_conversation_repository.py
├── integration/                    # Tests d'intégration DB/Redis
│   ├── test_database_connection.py
│   └── test_redis_cache.py
└── e2e/                           # Tests E2E complets
    └── test_chat_api_flow.py
```

### Markers Pytest

Les **markers** permettent de filtrer les tests pour exécution sélective :

```python
# conftest.py
def pytest_configure(config):
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "e2e: End-to-end integration tests")
```

**Usage** :
```bash
# Exécuter uniquement les tests unitaires
pytest -m unit

# Exécuter tous sauf E2E
pytest -m "not e2e"

# Exécuter tests lents uniquement
pytest -m slow

# Exécuter tests de sécurité
pytest -m security
```

### Un module ne se désactive jamais sur une clé de provider (ADR-155)

```python
# INTERDIT — le fichier entier sort de la CI, en silence
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY"
)
```

`OPENAI_API_KEY` n'est présente ni dans le job CI `test-backend`, ni sur le
poste de qui n'en configure pas. Un module portant ce marqueur est donc
**intégralement sauté à chaque exécution** — et rien ne le signale : un test
sauté est vert, la couverture mesure les lignes atteintes et non les assertions
exécutées, et une revue voit un fichier de tests et en conclut que la surface
est protégée. Mesuré le 2026-07-26 : dix fichiers masquaient ainsi **219
fonctions de test** qui n'avaient jamais tourné ; réactivées, **142 revenaient
au rouge**, et leur réparation a exhumé quatre défauts de production réels.

Trois issues, par ordre de préférence :

1. **Le test n'a besoin que de la *forme* d'une réponse LLM** → on la simule.
   C'est un test unitaire, sans aucune porte d'environnement. Cas quasi général.
2. **Le test appelle réellement un provider payant** → `@pytest.mark.e2e` (ou
   `integration`). Les filtres `-m` de la CI nomment ces marqueurs, donc
   l'exclusion est **lisible dans la commande** au lieu d'être un silence.
3. **Un seul test a besoin d'une clé** → on garde le `skipif` sur *cette
   fonction*. Le reste du fichier continue de tourner.

Appliqué par `apps/api/tests/unit/test_no_env_skipped_suite_guard.py` (balayage
AST sur six variables de credential). Sa liste d'exemption est **shrink-only et
vide** : une entrée y signifie des tests que personne n'exécute.

---

## Configuration et Environnement

### Configuration Pytest (pyproject.toml)

```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-ra -q --strict-markers --cov=src --cov-report=term-missing --cov-report=html"
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
pythonpath = ["."]
markers = [
    "e2e: End-to-end integration tests (deselect with '-m \"not e2e\"')",
    "unit: Unit tests",
    "integration: Integration tests",
    "slow: Slow running tests",
    "security: Security tests",
]
```

**Explications** :
- `asyncio_mode = "auto"` : détection automatique des tests async
- `--strict-markers` : erreur si marker non déclaré (évite typos)
- `--cov=src` : couverture de code du dossier `src/`
- `testpaths = ["tests"]` : découverte automatique dans `tests/`

### Variables d'Environnement de Test

```python
# conftest.py - Configuration AVANT tout import
import os

# Disable OpenTelemetry pour éviter erreurs Tempo
os.environ["OTEL_SDK_DISABLED"] = "true"

# Redis test DB (DB 15 pour éviter conflits avec dev/prod)
if os.path.exists("/.dockerenv"):
    # Inside Docker: use service name
    os.environ["REDIS_URL"] = "redis://redis:6379/15"
else:
    # Local: use localhost
    os.environ["REDIS_URL"] = "redis://localhost:6379/15"
```

**Stratégie** :
- **DB 15 Redis** : isolation complète des tests (dev = DB 0)
- **OTEL_SDK_DISABLED** : évite connexions Tempo en tests
- **Détection Docker** : `/.dockerenv` pour switch automatique

### Testcontainers pour PostgreSQL

**Stratégie multi-environnement** :

```python
@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer | None, None, None]:
    """
    Create a PostgreSQL test container for integration tests.

    Strategy:
    - If inside Docker with accessible postgres service: Use existing postgres (no container)
    - If local with Docker socket: Create testcontainer
    - Otherwise: Skip DB tests
    """
    is_docker, external_db = _detect_environment()

    # Strategy 1: Use existing postgres from docker-compose (fastest)
    if is_docker and external_db:
        # No container needed, will use external DB directly
        yield None
    else:
        # Strategy 2: Create testcontainer (local development)
        try:
            with PostgresContainer("pgvector/pgvector:pg16", driver=None) as postgres:
                yield postgres
        except Exception as e:
            pytest.skip(f"Testcontainers not available: {e}")
```

**Avantages** :
- **CI/CD** : utilise postgres docker-compose existant (rapide)
- **Local** : crée testcontainer automatiquement (isolation)
- **Pas de Docker** : skip tests avec message explicite

### Redirection process-wide vers la base de test

Les fixtures ne suffisent pas : le code sous test passe aussi par des
**singletons process-wide** qui lisent leur URL en dehors des fixtures — le
moteur SQLAlchemy module-level derrière `get_db_context()`/`get_db_session()`
(72 sites d'appel : cache pricing, schedulers, tools…), `settings.database_url`
lu paresseusement par le pool du checkpointer LangGraph et celui du LangGraph
Store. Historiquement ces chemins utilisaient l'URL de `.env.test` (base de
développement) et restaient verts grâce à des fallbacks best-effort : attentes
de ~35 s sur des connexions vouées, `relation "store" does not exist`, appels
admin pricing à 21 s — une validation partiellement fausse.

Le mécanisme (`tests/conftest.py::_redirect_process_db`, appelé par les deux
fixtures d'URL, idempotent) :

1. `settings.database_url` ← URL de test (validée `PostgresDsn`) — les pools
   checkpointer/store se construisent dessus et leur `setup()` idempotent crée
   `checkpoints`/`store` dans la base de test ;
2. le moteur global est remplacé par un moteur **NullPool** sur l'URL de test
   (chaque test pytest-asyncio a sa propre event loop : des connexions asyncpg
   poolées seraient réutilisées cross-loop et planteraient) ;
3. les singletons LangGraph sont réinitialisés ; leurs pools ouverts pendant un
   test sont fermés **sur la loop du test** par la fixture autouse
   `tests/integration/conftest.py::_close_langgraph_pools_on_test_loop`.

**Garde anti-base-dev** : quand la stratégie Testcontainers est active, toute
connexion vers `loopback:5432` (la base de développement) lève
`DevDatabaseAccessError` — un point d'entrée qui échappe à la redirection
échoue bruyamment au lieu de valider silencieusement contre les données dev.
Sous stratégie externe (`TEST_DATABASE_URL`, légitimement sur 5432) la garde
est inerte. Contrats : `tests/integration/test_db_redirection_contract.py`.

**PIÈGE environnement du lanceur (`task` injecte le `.env` développeur)** :
`Taskfile.yml` déclare `dotenv: [.env]` — chaque task, tests inclus, tourne
avec **tout** le `.env` de dev exporté dans son environnement ; `.env.test` ne
surcharge que ses propres clés. Résultat historique : 12 échecs sous
`task test:backend:integration` (flag ships-dark
`SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED=true` reroutant l'expansion
sémantique ; `DEFAULT_CURRENCY=EUR` + `CURRENCY_API_URL` réel convertissant
les coûts au taux de change **live**) alors que pytest direct restait vert —
des verdicts dépendants du lanceur, faciles à confondre avec de la pollution
d'ordre. Remède : `tests/conftest.py` purge de `os.environ` toute clé déclarée
dans le `.env` racine avant de charger `.env.test` (no-op en CI/conteneur).
Contrat : `tests/integration/test_env_isolation_contract.py`. Règle : un test
ne doit jamais dépendre d'une valeur exclusive au `.env` développeur ; si une
valeur est nécessaire aux tests, la déclarer dans `.env.test`.

**Remise à zéro des états process-wide entre tests** (défense en profondeur,
défauts réels distincts du piège ci-dessus) : les caches de tarification
(`CurrencyRateService._rate_cache` — **attribut de classe**, partagé par
toutes les instances — et `pricing_cache._local_cache`, module-level) et les
singletons sémantiques (type registry / expansion service / query analyzer)
fuient entre tests. La fixture autouse `_reset_shared_pricing_and_semantic_state`
(`tests/integration/conftest.py`) remet ces états dans le **statut canonique
de boot** (core types rechargés) avant ET après chaque test. Contrat prouvé
rouge/vert : `tests/integration/test_state_reset_contract.py` (un test pollue
volontairement, le suivant exige l'état vierge). Règle générale : tout nouvel
état module-level ou attribut de classe consulté par les chemins de coût ou
d'analyse doit être couvert par cette fixture.

**PIÈGE `CREATE INDEX CONCURRENTLY` (deadlock gelant le run)** : les
migrations des savers LangGraph contiennent des `CREATE INDEX CONCURRENTLY`,
qui attendent la fin de **toutes** les transactions détenant un XID/snapshot
sur la base. Or l'isolation par test (`async_session`) garde UNE transaction
externe ouverte pendant tout le test : dès que le test a écrit, un premier
`setup()` checkpointer/store **en cours de test** attend la transaction du
test, qui attend le `setup()` — gel infini (aucun timeout applicatif ne peut
agir : l'attente est du DDL côté serveur). Le remède est structurel :
`_provision_langgraph_tables` (appelée par `_db_schema_ready`) applique les
migrations UNE fois par session via les savers **sync**, à un instant où
aucune transaction de test n'existe — les `setup()` en cours de test se
réduisent alors à une vérification de version (aucun DDL). Régression épinglée
par `test_checkpointer_init_during_written_test_transaction` (borné
`wait_for(30 s)` : toute récidive échoue bruyamment au lieu de geler le run).

### Event Loop (Windows Compatibility)

```python
@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create event loop for async tests.

    On Windows, psycopg v3 requires SelectorEventLoop instead of ProactorEventLoop.
    """
    import selectors
    import sys

    # Use SelectorEventLoop on Windows for psycopg v3 compatibility
    if sys.platform == "win32":
        selector = selectors.SelectSelector()
        loop = asyncio.SelectorEventLoop(selector)
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop_policy().new_event_loop()

    yield loop
    loop.close()
```

**Problème résolu** : psycopg v3 + asyncpg sur Windows nécessite `SelectorEventLoop`.

---

## Tests Unitaires

### Principes des Tests Unitaires

**Règles d'or** :
1. **Isolation complète** : aucune dépendance externe (DB, Redis, API)
2. **Rapides** : <10ms par test
3. **Déterministes** : même input = même output (pas de random, pas de datetime.now())
4. **Un concept testé** : une assertion logique par test
5. **Mocking systématique** : mock toutes les dépendances externes

### Exemple : Test de Service

**Code à tester** :

```python
# src/domains/agents/services/hitl_classifier.py
from typing import Literal
from pydantic import BaseModel

class HitlClassificationResult(BaseModel):
    decision: Literal["APPROVE", "REJECT", "EDIT", "AMBIGUOUS"]
    confidence: float
    reasoning: str
    edited_params: dict | None = None
    clarification_question: str | None = None

class HitlResponseClassifier:
    """Classifies natural language HITL responses into structured decisions."""

    def __init__(self, model: str = "gpt-4-1106-preview"):
        self.model = model

    async def classify(
        self,
        user_response: str,
        action_context: list[dict],
    ) -> HitlClassificationResult:
        """
        Classify user response into APPROVE/REJECT/EDIT/AMBIGUOUS.

        Args:
            user_response: User's natural language response (e.g., "oui", "non")
            action_context: List of action requests to approve

        Returns:
            HitlClassificationResult with decision and metadata
        """
        # LLM classification logic here...
        pass
```

**Test unitaire** :

```python
# tests/agents/services/test_hitl_classifier.py
import pytest
from src.domains.agents.services.hitl_classifier import (
    HitlResponseClassifier,
    HitlClassificationResult,
)

@pytest.fixture
def classifier():
    """Create classifier instance for tests."""
    return HitlResponseClassifier(model="gpt-4-1106-preview")

@pytest.fixture
def sample_action_context():
    """Sample action context for search contacts."""
    return [
        {
            "tool_name": "search_contacts_tool",
            "tool_args": {"query": "jean"},
            "tool_description": "Recherche contacts par nom",
        }
    ]

# ============================================================================
# APPROVE Classification Tests
# ============================================================================

@pytest.mark.asyncio
async def test_classify_approve_oui(classifier, sample_action_context):
    """Test classification of 'oui' as APPROVE."""
    result = await classifier.classify(
        user_response="oui",
        action_context=sample_action_context
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8  # High confidence for clear approval
    assert result.reasoning is not None
    assert result.edited_params is None
    assert result.clarification_question is None

@pytest.mark.asyncio
async def test_classify_approve_ok(classifier, sample_action_context):
    """Test classification of 'ok' as APPROVE."""
    result = await classifier.classify(
        user_response="ok",
        action_context=sample_action_context
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8

@pytest.mark.asyncio
async def test_classify_approve_daccord(classifier, sample_action_context):
    """Test classification of "d'accord" as APPROVE."""
    result = await classifier.classify(
        user_response="d'accord",
        action_context=sample_action_context
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8

# ============================================================================
# REJECT Classification Tests
# ============================================================================

@pytest.mark.asyncio
async def test_classify_reject_non(classifier, sample_action_context):
    """Test classification of 'non' as REJECT."""
    result = await classifier.classify(
        user_response="non",
        action_context=sample_action_context
    )

    assert result.decision == "REJECT"
    assert result.confidence >= 0.8
    assert result.reasoning is not None

@pytest.mark.asyncio
async def test_classify_reject_annule(classifier, sample_action_context):
    """Test classification of 'annule' as REJECT."""
    result = await classifier.classify(
        user_response="annule",
        action_context=sample_action_context
    )

    assert result.decision == "REJECT"
    assert result.confidence >= 0.7
```

**Best Practices démontrées** :
- **Fixtures** : `classifier` et `sample_action_context` réutilisables
- **Organisation** : sections commentées pour lisibilité
- **Nommage** : `test_classify_approve_oui` descriptif
- **Async** : `@pytest.mark.asyncio` pour tests async
- **Assertions multiples** : vérification complète du résultat

### Tests Paramétriques (Parametrize)

Pour **tester plusieurs cas similaires** sans dupliquer le code :

```python
@pytest.mark.parametrize(
    "user_response,expected_decision,min_confidence",
    [
        # APPROVE cases
        ("oui", "APPROVE", 0.8),
        ("ok", "APPROVE", 0.8),
        ("d'accord", "APPROVE", 0.8),
        ("vas-y", "APPROVE", 0.7),
        ("confirme", "APPROVE", 0.8),
        ("bien sûr", "APPROVE", 0.8),
        ("go", "APPROVE", 0.7),

        # REJECT cases
        ("non", "REJECT", 0.8),
        ("annule", "REJECT", 0.7),
        ("stop", "REJECT", 0.7),
        ("ne fais pas ça", "REJECT", 0.7),

        # AMBIGUOUS cases
        ("peut-être", "AMBIGUOUS", 0.5),
        ("je ne sais pas", "AMBIGUOUS", 0.6),
    ]
)
@pytest.mark.asyncio
async def test_classify_various_responses(
    classifier,
    sample_action_context,
    user_response,
    expected_decision,
    min_confidence
):
    """Test classification of various user responses."""
    result = await classifier.classify(
        user_response=user_response,
        action_context=sample_action_context
    )

    assert result.decision == expected_decision
    assert result.confidence >= min_confidence
```

**Avantages** :
- **13 tests générés** automatiquement à partir d'une seule fonction
- **Lisibilité** : tableau de cas de test clair
- **Maintenabilité** : ajout de nouveaux cas trivial

### Tests avec Mocking

**Scénario** : tester un service qui dépend d'un LLM externe.

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_classify_with_llm_mock():
    """Test classification with mocked LLM call."""
    # Arrange
    classifier = HitlResponseClassifier(model="gpt-4-1106-preview")

    # Mock LLM response
    mock_llm_response = HitlClassificationResult(
        decision="APPROVE",
        confidence=0.95,
        reasoning="User clearly approved with 'oui'",
        edited_params=None,
        clarification_question=None,
    )

    # Mock the LLM call method
    with patch.object(classifier, "_call_llm", return_value=mock_llm_response):
        # Act
        result = await classifier.classify(
            user_response="oui",
            action_context=[{"tool_name": "test_tool"}]
        )

    # Assert
    assert result.decision == "APPROVE"
    assert result.confidence == 0.95
```

---

## Tests d'Intégration

### Principes des Tests d'Intégration

**Différences avec Unit Tests** :
- **Dépendances réelles** : PostgreSQL, Redis, services externes
- **Scope** : plusieurs composants ensemble (service + repository + DB)
- **Performance** : <500ms acceptable (vs <10ms pour unit)
- **Setup/Teardown** : gestion de l'état de la DB/cache

### Fixtures de Base de Données

**Fixtures session-scoped** (partagées entre tests) :

```python
# conftest.py
@pytest.fixture(scope="session")
def test_database_url(postgres_container: PostgresContainer | None) -> str:
    """
    Get the async database URL (asyncpg driver).

    Uses external postgres if available (docker-compose), otherwise testcontainer.
    """
    is_docker, external_db = _detect_environment()

    if is_docker and external_db:
        # Use existing postgres from docker-compose
        url = external_db.replace("postgresql://", "postgresql+asyncpg://")
        return url
    elif postgres_container:
        # Use testcontainer with explicit asyncpg driver
        return postgres_container.get_connection_url().replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    else:
        pytest.skip("No database available for testing")
```

**Isolation par SAVEPOINT, PAS par re-création du schéma (audit F049)** :

Le schéma est créé **une seule fois par session** (via un engine SYNC, pas de boucle
d'event loop à gérer) ; chaque test est isolé par une **transaction externe +
SAVEPOINT** annulée en teardown. Recréer tout le schéma (`drop_all`/`create_all` sur
~100 tables) à chaque test coûtait ~20 s/test — l'isolation SAVEPOINT donne un état
propre pour ~0,2 s/test (mesuré : 11 tests 241 s → 2,9 s, ~80×). Une garde AST
(`test_db_fixture_isolation_guard.py`) gèle ce contrat.

```python
@pytest.fixture(scope="session")
def _db_schema_ready(test_database_url_sync: str):
    """Build the schema ONCE per session (sync engine — F049)."""
    sync_url = test_database_url_sync.replace("postgresql://", "postgresql+psycopg://")
    engine = create_engine(sync_url, poolclass=NullPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
    yield
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
    engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def async_engine(_db_schema_ready, test_database_url: str):
    """Per-test engine — NO DDL (schema already built); NullPool (real per-test conn)."""
    engine = create_async_engine(test_database_url, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """External transaction + SAVEPOINT rolled back at teardown (F049).

    join_transaction_mode="create_savepoint" ⇒ even a test that calls commit() is
    undone (commit releases the savepoint and opens a new one; the outer transaction
    is rolled back), so no per-test schema rebuild is needed.
    """
    connection = await async_engine.connect()
    trans = await connection.begin()
    session = AsyncSession(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await connection.close()
```

**Stratégie** :
- **`scope="session"`** : postgres_container, test_database_url, **`_db_schema_ready`** (schéma créé 1×).
- **`scope="function"`** : async_engine (sans DDL), async_session (isolation SAVEPOINT).
- **NullPool** : une vraie connexion par test pour la transaction externe (jamais StaticPool
  ici — sa connexion partagée bloque contre la transaction SAVEPOINT).
- ⚠️ **Local Windows** : mettre `TEST_DATABASE_URL` sur `127.0.0.1` (pas `localhost` → `::1`
  timeout lent avec asyncpg, comme pour Redis).

### Exemple : Test de Repository

**Code à tester** :

```python
# src/domains/conversations/repository.py
class ConversationRepository:
    """Repository for conversation persistence."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(
        self,
        user_id: uuid.UUID,
        title: str,
    ) -> Conversation:
        """Create new conversation."""
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title,
            created_at=datetime.now(UTC),
        )
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def get_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> Conversation | None:
        """Get conversation by ID."""
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list_user_conversations(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Conversation]:
        """List conversations for a user."""
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
```

**Test d'intégration** :

```python
# tests/domains/conversations/test_conversation_repository.py
import uuid
import pytest
from src.domains.conversations.repository import ConversationRepository
from src.domains.conversations.models import Conversation
from src.domains.users.models import User

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_conversation(async_session, test_user):
    """Test creating a conversation in the database."""
    # Arrange
    repo = ConversationRepository(db=async_session)

    # Act
    conversation = await repo.create_conversation(
        user_id=test_user.id,
        title="Test Conversation",
    )

    # Assert
    assert conversation.id is not None
    assert conversation.user_id == test_user.id
    assert conversation.title == "Test Conversation"
    assert conversation.created_at is not None

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_conversation(async_session, test_user):
    """Test retrieving a conversation by ID."""
    # Arrange
    repo = ConversationRepository(db=async_session)
    created = await repo.create_conversation(
        user_id=test_user.id,
        title="Test Conversation",
    )

    # Act
    retrieved = await repo.get_conversation(conversation_id=created.id)

    # Assert
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.title == created.title

@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_nonexistent_conversation(async_session):
    """Test retrieving a non-existent conversation returns None."""
    # Arrange
    repo = ConversationRepository(db=async_session)

    # Act
    result = await repo.get_conversation(conversation_id=uuid.uuid4())

    # Assert
    assert result is None

@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_user_conversations(async_session, test_user):
    """Test listing conversations for a user."""
    # Arrange
    repo = ConversationRepository(db=async_session)

    # Create 3 conversations
    conv1 = await repo.create_conversation(test_user.id, "Conversation 1")
    conv2 = await repo.create_conversation(test_user.id, "Conversation 2")
    conv3 = await repo.create_conversation(test_user.id, "Conversation 3")

    # Act
    conversations = await repo.list_user_conversations(user_id=test_user.id)

    # Assert
    assert len(conversations) == 3
    # Should be ordered by created_at DESC (newest first)
    assert conversations[0].id == conv3.id
    assert conversations[1].id == conv2.id
    assert conversations[2].id == conv1.id

@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_user_conversations_limit(async_session, test_user):
    """Test listing conversations with limit."""
    # Arrange
    repo = ConversationRepository(db=async_session)

    # Create 5 conversations
    for i in range(5):
        await repo.create_conversation(test_user.id, f"Conversation {i}")

    # Act
    conversations = await repo.list_user_conversations(user_id=test_user.id, limit=2)

    # Assert
    assert len(conversations) == 2  # Limited to 2 most recent
```

**Best Practices démontrées** :
- **Marker `@pytest.mark.integration`** : filtre tests lents
- **Fixtures** : `async_session`, `test_user` réutilisés
- **AAA Pattern** : Arrange/Act/Assert clair
- **Tests négatifs** : `test_get_nonexistent_conversation`
- **Edge cases** : limit parameter

### Fixtures Utilisateurs

```python
# conftest.py
@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession) -> User:
    """Create a test user for authentication tests."""
    from src.core.security import get_password_hash

    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("TestPassword123!"),
        full_name="Test User",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )

    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    return user

@pytest_asyncio.fixture
async def test_superuser(async_session: AsyncSession) -> User:
    """Create a test superuser for admin tests."""
    from src.core.security import get_password_hash

    user = User(
        email="admin@example.com",
        hashed_password=get_password_hash("AdminPassword123!"),
        full_name="Admin User",
        is_active=True,
        is_verified=True,
        is_superuser=True,
    )

    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    return user

@pytest.fixture
def test_user_credentials() -> dict[str, str]:
    """Test user credentials."""
    return {
        "email": "test@example.com",
        "password": "TestPassword123!",
    }
```

---

## Tests End-to-End (E2E)

### Principes des Tests E2E

**Objectif** : valider des **flux complets utilisateur** avec tous les composants réels.

**Caractéristiques** :
- **Scope maximal** : API → Service → Repository → DB → LangGraph → LLM
- **Scénarios utilisateur** : chat complet, HITL flow, SSE streaming
- **Performance** : <5s acceptable (mais lents)
- **Fréquence** : exécutés en CI/CD sur PR merge

### Exemple : Test E2E HITL Streaming

**Scénario** : flux complet de Human-in-the-Loop avec Server-Sent Events.

```python
# tests/agents/integration/test_hitl_streaming_e2e.py
"""
E2E Integration Tests for HITL Streaming.

Tests cover the complete SSE streaming flow:
- Full HTTP SSE connection lifecycle
- 3-chunk streaming protocol (metadata → tokens → complete)
- Integration with LangGraph state management
- Real HITL interrupt and resumption flow
- End-to-end TTFT measurement in production-like environment

Architecture Flow Tested:
1. POST /agents/chat/stream
2. AgentService.stream_chat_response()
3. Graph execution → HITL interrupt
4. HITLQuestionGenerator.generate_confirmation_question_stream()
5. SSE chunks: hitl_interrupt_metadata → hitl_question_token* → hitl_interrupt_complete
6. User response → handle_hitl_response()
7. Graph resumption → final response
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch
import pytest
from langchain_core.messages import AIMessageChunk

from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_authenticated_user():
    """Mock authenticated user for tests."""
    from src.domains.users.models import User

    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        username="testuser",
        hashed_password="hashed",
        is_active=True,
    )
    return user

@pytest.fixture
def mock_hitl_interrupt_event():
    """Mock HITL interrupt event from LangGraph."""
    return {
        "type": "approval",
        "content": "",
        "metadata": {
            "action_requests": [
                {
                    "name": "search_contacts_tool",
                    "args": {"query": "jean"},
                    "type": "tool_call",
                }
            ],
            "review_configs": [{"approval_type": "required"}],
            "interrupt_ts": 1699900000.123,
        },
    }

@pytest.fixture
def mock_question_tokens():
    """Mock streaming question tokens."""
    return [
        "Je ",
        "vais ",
        "rechercher ",
        "le ",
        "contact ",
        "'jean'. ",
        "Continuer",
        "?"
    ]

# ============================================================================
# E2E SSE Streaming Tests
# ============================================================================

class TestHITLStreamingE2E:
    """E2E tests for HITL streaming via SSE."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_full_sse_streaming_lifecycle(
        self,
        mock_authenticated_user,
        mock_hitl_interrupt_event,
        mock_question_tokens,
    ):
        """Test complete SSE streaming lifecycle from request to completion."""
        # Arrange
        agent_service = AgentService()

        # Mock graph execution that triggers HITL
        async def graph_events():
            # Simulate graph execution → HITL interrupt
            yield mock_hitl_interrupt_event
            # After interrupt, graph pauses (no more events until resumption)

        # Mock question generator streaming
        with patch.object(agent_service, "hitl_question_generator") as mock_question_gen:

            async def question_stream(*args, **kwargs):
                for token in mock_question_tokens:
                    await asyncio.sleep(0.01)  # Simulate streaming latency
                    yield token

            mock_question_gen.generate_confirmation_question_stream = question_stream

            # Mock graph build
            with patch.object(agent_service, "_ensure_graph_built"):
                with patch.object(agent_service.graph, "astream") as mock_astream:
                    mock_astream.return_value = graph_events()

                    # Act
                    chunks_received = []
                    async for chunk in agent_service._stream_graph_events(
                        graph_stream=graph_events(),
                        tracking_start_time=1699900000.0,
                    ):
                        chunks_received.append(chunk)

                    # Assert
                    assert len(chunks_received) > 0
                    # Verify chunk types
                    chunk_types = [c.type for c in chunks_received]
                    assert "tool_approval_request" in chunk_types

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_hitl_streaming_three_chunk_protocol(
        self,
        mock_authenticated_user,
        mock_hitl_interrupt_event,
        mock_question_tokens,
    ):
        """Test 3-chunk SSE protocol: metadata → tokens → complete."""
        # Arrange
        agent_service = AgentService()

        async def graph_events():
            yield mock_hitl_interrupt_event

        with patch.object(agent_service, "hitl_question_generator") as mock_question_gen:
            async def question_stream(*args, **kwargs):
                for token in mock_question_tokens:
                    yield AIMessageChunk(content=token)

            mock_question_gen.generate_confirmation_question_stream = question_stream

            with patch.object(agent_service, "_ensure_graph_built"):
                with patch.object(agent_service.graph, "astream", return_value=graph_events()):
                    # Act
                    chunks = []
                    async for chunk in agent_service._stream_graph_events(
                        graph_stream=graph_events(),
                        tracking_start_time=1699900000.0,
                    ):
                        chunks.append(chunk)

                    # Assert - Verify 3-chunk protocol
                    # Chunk 1: metadata (action_requests, review_configs)
                    metadata_chunks = [c for c in chunks if hasattr(c, "metadata")]
                    assert len(metadata_chunks) > 0

                    # Chunk 2: tokens (streaming question)
                    token_chunks = [c for c in chunks if c.type == "text"]
                    assert len(token_chunks) >= len(mock_question_tokens)

                    # Chunk 3: complete (interrupt_id for resumption)
                    complete_chunks = [c for c in chunks if hasattr(c, "interrupt_id")]
                    assert len(complete_chunks) > 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_hitl_resumption_after_approval(
        self,
        mock_authenticated_user,
        mock_hitl_interrupt_event,
    ):
        """Test graph resumption after user approval."""
        # Arrange
        agent_service = AgentService()
        interrupt_id = "test-interrupt-123"

        # Mock graph state retrieval
        mock_state = {
            "messages": [],
            "pending_actions": mock_hitl_interrupt_event["metadata"]["action_requests"],
        }

        with patch.object(agent_service, "_get_graph_state", return_value=mock_state):
            with patch.object(agent_service, "_resume_graph") as mock_resume:
                # Mock resumption
                async def resume_stream(*args, **kwargs):
                    yield {"type": "result", "content": "Contact trouvé: jean"}

                mock_resume.return_value = resume_stream()

                # Act
                response = await agent_service.handle_hitl_response(
                    interrupt_id=interrupt_id,
                    user_response="oui",
                    user=mock_authenticated_user,
                )

                # Assert
                assert response is not None
                mock_resume.assert_called_once()
```

**Best Practices démontrées** :
- **Marker `@pytest.mark.e2e`** : identification claire
- **Documentation exhaustive** : docstring explique flux complet
- **Mocking ciblé** : mock LLM/LangGraph mais pas DB/Redis
- **Assertions temporelles** : vérification de l'ordre des chunks
- **Tests de protocole** : validation SSE 3-chunk protocol

### HTTP Client Fixtures

```python
# conftest.py
@pytest_asyncio.fixture(scope="function")
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create async HTTP client for API tests.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def authenticated_client(
    async_client: AsyncClient,
    test_user: User,
    test_user_credentials: dict[str, str]
) -> AsyncGenerator[tuple[AsyncClient, User], None]:
    """
    Create authenticated HTTP client with session cookie (BFF Pattern).

    This fixture logs in the user and sets the session cookie on the client.
    """
    # Login to get session cookie
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json=test_user_credentials,
    )

    assert login_response.status_code == 200, f"Login failed: {login_response.json()}"

    # Cookie is automatically stored by AsyncClient
    yield async_client, test_user
```

**Usage** :

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chat_api_authenticated(authenticated_client):
    """Test chat API with authenticated user."""
    client, user = authenticated_client

    # Act
    response = await client.post(
        "/api/v1/agents/chat",
        json={"message": "Bonjour"},
    )

    # Assert
    assert response.status_code == 200
    assert "response" in response.json()
```

---

## Tests d'Agents LangGraph

### Principes des Tests d'Agents

**Challenges spécifiques** :
- **StateGraph** : état partagé entre nodes
- **Checkpointer** : persistance état pour HITL/interrupts
- **Async nodes** : tests async complexes
- **Mocking LLMs** : éviter coûts API en tests

### Exemple : Test de Agent Registry

**Code à tester** :

```python
# src/domains/agents/registry/agent_registry.py
class AgentRegistry:
    """Centralized registry for agent management with lazy initialization."""

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
        store: BaseStore | None = None,
    ):
        self._builders: dict[str, Callable[[], CompiledGraph]] = {}
        self._instances: dict[str, CompiledGraph] = {}
        self._checkpointer = checkpointer
        self._store = store
        self._lock = threading.Lock()

    def register_agent(
        self,
        agent_id: str,
        builder: Callable[[], CompiledGraph],
    ) -> None:
        """Register an agent builder."""
        if not agent_id or not isinstance(agent_id, str):
            raise ValueError(f"Invalid agent_id: {agent_id}")

        with self._lock:
            if agent_id in self._builders:
                raise AgentAlreadyRegisteredError(agent_id)

            self._builders[agent_id] = builder

    def get_agent(self, agent_id: str) -> CompiledGraph:
        """Get agent instance (lazy initialization)."""
        with self._lock:
            if agent_id not in self._builders:
                raise AgentNotFoundError(agent_id)

            # Lazy initialization
            if agent_id not in self._instances:
                self._instances[agent_id] = self._builders[agent_id]()

            return self._instances[agent_id]

    def is_registered(self, agent_id: str) -> bool:
        """Check if agent is registered."""
        return agent_id in self._builders

    def is_built(self, agent_id: str) -> bool:
        """Check if agent instance is built."""
        return agent_id in self._instances

    def list_agents(self) -> list[str]:
        """List all registered agent IDs."""
        return list(self._builders.keys())
```

**Tests unitaires** :

```python
# tests/agents/test_agent_registry.py
"""
Tests for Agent Registry.

Tests the centralized agent management system with:
- Registration and retrieval
- Lazy initialization
- Dependency injection (checkpointer, store)
- Thread safety
- Error handling
"""

from unittest.mock import Mock
import pytest

from src.domains.agents.registry import (
    AgentAlreadyRegisteredError,
    AgentNotFoundError,
    AgentRegistry,
    get_global_registry,
    reset_global_registry,
)

class TestAgentRegistryBasics:
    """Test basic registry operations."""

    def test_registry_initialization(self):
        """Test registry can be initialized."""
        registry = AgentRegistry()
        assert registry is not None
        assert registry.get_checkpointer() is None
        assert registry.get_store() is None

    def test_registry_with_dependencies(self):
        """Test registry initialization with checkpointer and store."""
        mock_checkpointer = Mock()
        mock_store = Mock()

        registry = AgentRegistry(checkpointer=mock_checkpointer, store=mock_store)

        assert registry.get_checkpointer() == mock_checkpointer
        assert registry.get_store() == mock_store

    def test_list_agents_empty(self):
        """Test listing agents when none registered."""
        registry = AgentRegistry()
        assert registry.list_agents() == []

    def test_is_registered_false(self):
        """Test is_registered returns False for unregistered agent."""
        registry = AgentRegistry()
        assert registry.is_registered("nonexistent") is False

class TestAgentRegistration:
    """Test agent registration."""

    def test_register_agent_success(self):
        """Test successful agent registration."""
        registry = AgentRegistry()

        def mock_builder():
            return Mock(name="TestAgent")

        registry.register_agent("test_agent", mock_builder)

        assert registry.is_registered("test_agent")
        assert "test_agent" in registry.list_agents()

    def test_register_multiple_agents(self):
        """Test registering multiple agents."""
        registry = AgentRegistry()

        def builder1():
            return Mock(name="Agent1")

        def builder2():
            return Mock(name="Agent2")

        registry.register_agent("agent1", builder1)
        registry.register_agent("agent2", builder2)

        assert registry.list_agents() == ["agent1", "agent2"]

    def test_register_agent_invalid_name(self):
        """Test registration fails with invalid agent name."""
        registry = AgentRegistry()

        def mock_builder():
            return Mock()

        with pytest.raises(ValueError, match="Invalid agent_id"):
            registry.register_agent("", mock_builder)

    def test_register_agent_duplicate(self):
        """Test registration fails for duplicate agent ID."""
        registry = AgentRegistry()

        def mock_builder():
            return Mock()

        registry.register_agent("test_agent", mock_builder)

        with pytest.raises(AgentAlreadyRegisteredError, match="test_agent"):
            registry.register_agent("test_agent", mock_builder)

class TestAgentRetrieval:
    """Test agent retrieval and lazy initialization."""

    def test_get_agent_success(self):
        """Test successful agent retrieval."""
        registry = AgentRegistry()
        mock_agent = Mock(name="TestAgent")

        def mock_builder():
            return mock_agent

        registry.register_agent("test_agent", mock_builder)

        # First retrieval builds instance
        agent = registry.get_agent("test_agent")

        assert agent == mock_agent
        assert registry.is_built("test_agent")

    def test_get_agent_lazy_initialization(self):
        """Test lazy initialization (builder not called until get_agent)."""
        registry = AgentRegistry()
        builder_called = False

        def mock_builder():
            nonlocal builder_called
            builder_called = True
            return Mock()

        registry.register_agent("test_agent", mock_builder)

        # Builder not called yet
        assert builder_called is False
        assert registry.is_built("test_agent") is False

        # Builder called on first get_agent
        registry.get_agent("test_agent")
        assert builder_called is True
        assert registry.is_built("test_agent") is True

    def test_get_agent_cached(self):
        """Test agent instance is cached (builder called only once)."""
        registry = AgentRegistry()
        builder_call_count = 0

        def mock_builder():
            nonlocal builder_call_count
            builder_call_count += 1
            return Mock()

        registry.register_agent("test_agent", mock_builder)

        # First call builds
        agent1 = registry.get_agent("test_agent")
        assert builder_call_count == 1

        # Second call returns cached instance
        agent2 = registry.get_agent("test_agent")
        assert builder_call_count == 1  # Not called again
        assert agent1 is agent2  # Same instance

    def test_get_agent_not_registered(self):
        """Test get_agent fails for unregistered agent."""
        registry = AgentRegistry()

        with pytest.raises(AgentNotFoundError, match="nonexistent"):
            registry.get_agent("nonexistent")

class TestGlobalRegistry:
    """Test global registry singleton."""

    def test_get_global_registry(self):
        """Test global registry access."""
        reset_global_registry()
        registry1 = get_global_registry()
        registry2 = get_global_registry()

        assert registry1 is registry2  # Singleton

    def test_reset_global_registry(self):
        """Test global registry reset."""
        reset_global_registry()
        registry1 = get_global_registry()

        reset_global_registry()
        registry2 = get_global_registry()

        assert registry1 is not registry2  # New instance
```

**Best Practices démontrées** :
- **Organisation par classe** : `TestAgentRegistryBasics`, `TestAgentRegistration`, etc.
- **Tests de thread safety** : lazy initialization, caching
- **Tests d'erreurs** : `AgentAlreadyRegisteredError`, `AgentNotFoundError`
- **Tests de comportement** : lazy init, caching, singleton

### Tests de StateGraph Nodes

**Scénario** : tester un node LangGraph isolément.

```python
# tests/agents/nodes/test_planner_node_v3.py
import pytest
from unittest.mock import AsyncMock, Mock
from src.domains.agents.nodes.planner_node import PlannerNode
from src.domains.agents.state import MessagesState

@pytest.mark.asyncio
async def test_planner_node_generates_plan():
    """Test planner node generates valid plan."""
    # Arrange
    planner = PlannerNode(llm=AsyncMock())

    # Mock LLM response
    planner.llm.ainvoke = AsyncMock(return_value={
        "steps": [
            {"action": "search_contacts", "args": {"query": "jean"}},
            {"action": "send_email", "args": {"to": "jean@example.com"}},
        ]
    })

    # Create initial state
    state: MessagesState = {
        "messages": [
            {"role": "user", "content": "Envoie un email à jean"}
        ],
        "plan": None,
    }

    # Act
    result = await planner.execute(state)

    # Assert
    assert result["plan"] is not None
    assert len(result["plan"]["steps"]) == 2
    assert result["plan"]["steps"][0]["action"] == "search_contacts"
    assert result["plan"]["steps"][1]["action"] == "send_email"

@pytest.mark.asyncio
async def test_planner_node_with_context():
    """Test planner node uses conversation context."""
    # Arrange
    planner = PlannerNode(llm=AsyncMock())

    state: MessagesState = {
        "messages": [
            {"role": "user", "content": "Qui est jean?"},
            {"role": "assistant", "content": "jean est votre collègue."},
            {"role": "user", "content": "Envoie-lui un email"},
        ],
        "plan": None,
    }

    # Mock LLM to verify context is passed
    planner.llm.ainvoke = AsyncMock(return_value={
        "steps": [{"action": "send_email", "args": {"to": "jean@example.com"}}]
    })

    # Act
    result = await planner.execute(state)

    # Assert
    # Verify LLM was called with full context
    call_args = planner.llm.ainvoke.call_args
    assert len(call_args[0][0]) == 3  # 3 messages passed
```

---

## Tests de Tools

### Principes des Tests de Tools

**Challenges** :
- **OAuth refresh** : mock token refresh
- **Rate limiting** : vérifier limites respectées
- **Caching** : vérifier hits/misses
- **API externes** : mock réponses HTTP

### Exemple : Test de ConnectorTool avec OAuth

**Code à tester** :

```python
# src/domains/agents/tools/google_contacts_tools.py
from src.domains.agents.tools.base import ConnectorTool, connector_tool

@connector_tool
class SearchContactsTool(ConnectorTool):
    """Search Google Contacts."""

    async def execute(self, query: str, max_results: int = 10) -> dict:
        """
        Search contacts by name/email.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            dict with contacts list
        """
        # self.client is auto-injected by ConnectorTool
        contacts = await self.client.search_contacts(query, max_results)

        return {
            "success": True,
            "data": {"contacts": contacts, "count": len(contacts)},
            "message": f"Trouvé {len(contacts)} contact(s)",
        }
```

**Test unitaire avec mocking** :

```python
# tests/agents/tools/test_google_contacts_tools.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.domains.agents.tools.google_contacts_tools import SearchContactsTool

@pytest.fixture
def mock_google_client():
    """Mock Google Contacts client."""
    client = AsyncMock()
    client.search_contacts = AsyncMock(return_value=[
        {"name": "jean Chen", "email": "jean@example.com"},
        {"name": "jean Li", "email": "huali@example.com"},
    ])
    return client

@pytest.mark.asyncio
async def test_search_contacts_success(mock_google_client):
    """Test successful contact search."""
    # Arrange
    tool = SearchContactsTool(client=mock_google_client)

    # Act
    result = await tool.execute(query="jean", max_results=10)

    # Assert
    assert result["success"] is True
    assert result["data"]["count"] == 2
    assert len(result["data"]["contacts"]) == 2
    assert result["message"] == "Trouvé 2 contact(s)"

    # Verify client was called correctly
    mock_google_client.search_contacts.assert_called_once_with("jean", 10)

@pytest.mark.asyncio
async def test_search_contacts_no_results(mock_google_client):
    """Test search with no results."""
    # Arrange
    mock_google_client.search_contacts = AsyncMock(return_value=[])
    tool = SearchContactsTool(client=mock_google_client)

    # Act
    result = await tool.execute(query="NonexistentName")

    # Assert
    assert result["success"] is True
    assert result["data"]["count"] == 0
    assert result["message"] == "Trouvé 0 contact(s)"

@pytest.mark.asyncio
async def test_search_contacts_oauth_refresh():
    """Test OAuth token auto-refresh on expiry."""
    # Arrange
    mock_client = AsyncMock()

    # First call: token expired (401)
    # Second call: success after refresh
    mock_client.search_contacts = AsyncMock(
        side_effect=[
            Exception("401 Unauthorized"),  # Trigger refresh
            [{"name": "jean", "email": "jean@example.com"}],  # After refresh
        ]
    )

    with patch("src.domains.agents.tools.decorators.oauth_refresh") as mock_oauth:
        # Mock OAuth refresh decorator
        async def mock_refresh_wrapper(func):
            async def wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if "401" in str(e):
                        # Simulate token refresh
                        await mock_client.refresh_token()
                        return await func(*args, **kwargs)
                    raise
            return wrapper

        mock_oauth.return_value = mock_refresh_wrapper

        tool = SearchContactsTool(client=mock_client)

        # Act
        result = await tool.execute(query="jean")

        # Assert
        assert result["success"] is True
        # Verify refresh was triggered
        assert mock_client.search_contacts.call_count == 2
```

### Tests de Rate Limiting

```python
# tests/agents/tools/test_rate_limiting.py
import pytest
import asyncio
from src.domains.agents.tools.decorators import rate_limit
from src.core.exceptions import RateLimitExceededError

@pytest.mark.asyncio
async def test_rate_limiting_within_limit():
    """Test rate limiting allows requests within limit."""
    # Arrange
    @rate_limit(max_calls=5, period=1.0)  # 5 calls per second
    async def dummy_tool():
        return "success"

    # Act - Make 5 calls (within limit)
    results = []
    for _ in range(5):
        results.append(await dummy_tool())

    # Assert
    assert len(results) == 5
    assert all(r == "success" for r in results)

@pytest.mark.asyncio
async def test_rate_limiting_exceeds_limit():
    """Test rate limiting blocks requests exceeding limit."""
    # Arrange
    @rate_limit(max_calls=3, period=1.0)  # 3 calls per second
    async def dummy_tool():
        return "success"

    # Act - Make 4 calls (exceeds limit)
    results = []
    for i in range(4):
        try:
            results.append(await dummy_tool())
        except RateLimitExceededError as e:
            results.append(f"error_{i}")

    # Assert
    assert len(results) == 4
    assert results[:3] == ["success", "success", "success"]
    assert "error" in results[3]  # 4th call blocked

@pytest.mark.asyncio
async def test_rate_limiting_resets_after_period():
    """Test rate limiting resets after time period."""
    # Arrange
    @rate_limit(max_calls=2, period=0.5)  # 2 calls per 0.5s
    async def dummy_tool():
        return "success"

    # Act
    # First 2 calls succeed
    result1 = await dummy_tool()
    result2 = await dummy_tool()

    # 3rd call fails
    with pytest.raises(RateLimitExceededError):
        await dummy_tool()

    # Wait for period to reset
    await asyncio.sleep(0.6)

    # 4th call succeeds (limit reset)
    result4 = await dummy_tool()

    # Assert
    assert result1 == "success"
    assert result2 == "success"
    assert result4 == "success"
```

### Tests de Caching

```python
# tests/agents/tools/test_caching.py
import pytest
from unittest.mock import AsyncMock
from src.domains.agents.tools.decorators import cache_result

@pytest.mark.asyncio
async def test_cache_hit():
    """Test cache returns cached result without calling function."""
    # Arrange
    call_count = 0

    @cache_result(ttl=60)
    async def expensive_tool(query: str):
        nonlocal call_count
        call_count += 1
        return f"result_{query}"

    # Act
    result1 = await expensive_tool("test")
    result2 = await expensive_tool("test")  # Should hit cache

    # Assert
    assert result1 == result2 == "result_test"
    assert call_count == 1  # Function called only once

@pytest.mark.asyncio
async def test_cache_miss_different_args():
    """Test cache miss with different arguments."""
    # Arrange
    call_count = 0

    @cache_result(ttl=60)
    async def expensive_tool(query: str):
        nonlocal call_count
        call_count += 1
        return f"result_{query}"

    # Act
    result1 = await expensive_tool("test1")
    result2 = await expensive_tool("test2")  # Different arg → cache miss

    # Assert
    assert result1 == "result_test1"
    assert result2 == "result_test2"
    assert call_count == 2  # Function called twice

@pytest.mark.asyncio
async def test_cache_expiry(monkeypatch):
    """Test cache expires after TTL."""
    # Arrange
    call_count = 0

    @cache_result(ttl=1)  # 1 second TTL
    async def expensive_tool(query: str):
        nonlocal call_count
        call_count += 1
        return f"result_{query}"

    # Act
    result1 = await expensive_tool("test")

    # Simulate time passing (mock time)
    import time
    with monkeypatch.context() as m:
        m.setattr(time, "time", lambda: time.time() + 2)  # +2 seconds
        result2 = await expensive_tool("test")  # Cache expired → miss

    # Assert
    assert result1 == result2 == "result_test"
    assert call_count == 2  # Function called twice (cache expired)
```

---

## Mocking et Fixtures

### Stratégies de Mocking

**Quand utiliser Mock vs MagicMock vs AsyncMock** :

| Type | Usage | Exemple |
|------|-------|---------|
| `Mock` | Objets synchrones simples | `mock_config = Mock(debug=True)` |
| `MagicMock` | Objets avec magic methods (`__getitem__`, etc.) | `mock_dict = MagicMock()` |
| `AsyncMock` | Fonctions/méthodes asynchrones | `mock_client.fetch = AsyncMock(return_value=data)` |

**Exemple complet** :

```python
from unittest.mock import Mock, MagicMock, AsyncMock, patch

# Mock simple object
mock_config = Mock()
mock_config.debug = True
mock_config.database_url = "postgresql://test"

# Mock dict-like object
mock_cache = MagicMock()
mock_cache["key"] = "value"
assert mock_cache["key"] == "value"

# Mock async function
mock_llm = AsyncMock()
mock_llm.ainvoke = AsyncMock(return_value={"response": "Hello"})

# Mock with side_effect (different responses)
mock_api = AsyncMock()
mock_api.fetch = AsyncMock(side_effect=[
    {"status": "pending"},
    {"status": "processing"},
    {"status": "complete"},
])

# First call
result1 = await mock_api.fetch()  # {"status": "pending"}
# Second call
result2 = await mock_api.fetch()  # {"status": "processing"}
# Third call
result3 = await mock_api.fetch()  # {"status": "complete"}
```

#### Piège : coroutine `AsyncMock` jamais attendue (garde F028)

Un `MagicMock(spec=UneClasse)` transforme automatiquement les méthodes `async` de
`UneClasse` en `AsyncMock` — **et la valeur de retour d'un `AsyncMock` est
elle-même un `AsyncMock`**. Conséquence : tout accès imbriqué du type
`(await mock.aget_state(...)).values.get("x")` renvoie une **coroutine** (le
`.get()` est traité comme asynchrone), que le code de production n'attend jamais.
CPython ne signale la coroutine non attendue qu'au ramasse-miettes — souvent
pendant un **autre** test, innocent : c'est le « faux vert » de l'audit (F028).

```python
# ❌ Fuite : aget_state renvoie un AsyncMock, .values.get(...) est une coroutine
graph = MagicMock(spec=CompiledStateGraph)

# ✅ Correct : configurer un snapshot dont .values est un vrai dict (sync)
snapshot = MagicMock()
snapshot.values = {"user_language": "fr", "user_timezone": "Europe/Paris"}
graph.aget_state = AsyncMock(return_value=snapshot)
```

Une garde autouse (`tests/_coroutine_leak_guard.py`, câblée dans les conftests
`tests/unit` et `tests/agents`) force une collecte génération-0 en teardown et
**fait échouer le test fautif** s'il a fait fuir une coroutine `AsyncMock`
(`_execute_mock_call`) — l'attribuant déterministiquement à son créateur au lieu
d'un test aléatoire. Elle est volontairement limitée à cette classe : les
coroutines internes de driver (ex. `Connection._cancel` d'asyncpg au teardown de
process) ne sont pas des bugs de code de test et sont ignorées explicitement dans
`pyproject.toml`. Le self-test de la garde vit dans `tests/unit/test_coroutine_leak_guard.py`.

### Fixtures Réutilisables

**Patron de conception** : scope approprié pour performance.

```python
# conftest.py

# ============================================================================
# Session-scoped (shared across all tests)
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Event loop for async tests (session-wide)."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def postgres_container():
    """PostgreSQL testcontainer (session-wide for performance)."""
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        yield postgres

# ============================================================================
# Function-scoped (fresh for each test)
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine):
    """Database session (function-scoped for isolation)."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session_maker() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def test_user(async_session):
    """Test user (function-scoped, created fresh each time)."""
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("TestPassword123!"),
        full_name="Test User",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user

# ============================================================================
# Module-scoped (shared within a test file)
# ============================================================================

@pytest.fixture(scope="module")
def llm_config():
    """LLM configuration (module-scoped, doesn't change)."""
    return {
        "model": "gpt-4-1106-preview",
        "temperature": 0.7,
        "max_tokens": 1000,
    }
```

### Patching avec Context Managers

```python
# Test avec patch temporaire
def test_with_mocked_datetime():
    """Test with mocked datetime.now()."""
    from datetime import datetime

    # Mock datetime.now() to return fixed time
    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2025, 1, 15, 12, 0, 0)

        # Code under test
        result = create_conversation(title="Test")

        # Assert timestamp is mocked value
        assert result.created_at == datetime(2025, 1, 15, 12, 0, 0)

# Test avec patch sur méthode de classe
@pytest.mark.asyncio
async def test_with_mocked_llm_call():
    """Test with mocked LLM call."""
    from src.domains.agents.services.planner import PlannerService

    planner = PlannerService()

    # Mock LLM invocation
    with patch.object(planner.llm, "ainvoke", new=AsyncMock(return_value={"plan": []})):
        result = await planner.generate_plan("Test message")

        assert result["plan"] == []
        planner.llm.ainvoke.assert_called_once()
```

---

## Coverage et Qualité

### Configuration Coverage

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "-ra -q --strict-markers --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=62"
```

**Rapports générés** :
- **Terminal** : `--cov-report=term-missing` → lignes non couvertes
- **HTML** : `--cov-report=html` → htmlcov/index.html

⚠️ Le gate `--cov-fail-under` étant dans `addopts`, il s'applique à **toute**
invocation pytest sans `--no-cov`. Pour lancer un sous-ensemble de tests
(un fichier, un dossier), ajoutez `--no-cov` — sinon la couverture du
sous-ensemble échoue mécaniquement sous le seuil global.

### Doctrine du seuil de couverture (ratchet)

Le seuil CI est un **cliquet** (ratchet) : il ne descend jamais, et on le
**relève après tout lot améliorant la couverture** (ainsi qu'à chaque release)
pour verrouiller les gains, tant que l'objectif de 75 % n'est pas atteint
(recommandation n°4 de l'audit 2026-07 : paliers 43→55→65→75). Verrouiller les
acquis est une règle systématique, pas un rituel de release.

Règles :
1. Le seuil a **une seule source de vérité** : `apps/api/pyproject.toml`
   (addopts). Il est répété une fois, dans la tâche `test:backend:unit:coverage`
   du `Taskfile.yml` — que la CI appelle telle quelle (ADR-151), donc il n'y a
   plus de valeur dans `ci.yml`. La garde
   `test_task_ci_pytest_parity_guard.py::test_coverage_threshold_has_a_single_source_of_truth`
   échoue si un `--cov-fail-under` divergent réapparaît quelque part.
2. On ne monte le seuil que si la couverture réelle mesurée en CI laisse
   **au moins 2 points de marge** (éviter les échecs de CI sur variance).
3. Baisser le seuil est interdit — si une PR fait chuter la couverture sous
   le gate, c'est la PR qu'on corrige, pas le gate.
4. Historique : 43 % (baseline audit) → 45 % (v1.21.22, couverture réelle
   mesurée : 52,3 %) → 58 % (2026-07-24, réel 62,5 % sur le sous-ensemble gated
   fast-unit) → 59 % (2026-07-24, réel 62,79 % — 13 016 tests) → 60 %
   (2026-07-25, réel 63,16 % — 13 422 tests) → 61 % (2026-07-25, réel 63,67 %
   — 13 737 tests) → **62 % (2026-07-26, réel 64,13 % — 14 058 tests dans le sous-ensemble gated)**.
   Re-mesuré le 2026-07-28 : réel 64,98 % (14 688 tests dans le sous-ensemble
   gated) — le plancher reste à 62 %, le passer à 63 % ne laisserait que 1,98 pt
   de marge. → **63 % (2026-07-30, réel 65,22 % — 14 938 tests dans le
   sous-ensemble gated, programme peers Lots 1-7)**. → **64 % (2026-08-01, réel
   66,09 % — 15 719 tests dans le sous-ensemble gated, programme Relations /
   Pairs / 360° + ADR-193)** : le seuil de déclenchement annoncé au palier
   précédent (~66 %) est atteint, la marge retombe à 2,09 pt. Palier suivant
   65 % dès que le réel dépasse ~67 %. → **65 % (2026-08-06, réel 68,16 % —
   17 026 tests dans le sous-ensemble gated, programme démonstrateur libre
   lots 1-6 / ADR-216→218)** : le déclencheur annoncé (~67 %) est franchi, la
   marge reste à 3,16 pt. Palier suivant 66 % dès que le réel dépasse ~70 %.

   La marge volontairement conservée (~4 pts) couvre l'écart entre la mesure
   locale (Windows) et le runner CI (Linux) : quelques branches dépendent de la
   plateforme, et un gate trop serré rougirait la CI sans régression réelle.

### Exécuter Coverage

```bash
# Coverage complète (applique le gate --cov-fail-under=62)
cd apps/api
pytest --cov=src --cov-report=term-missing --cov-report=html

# Coverage par module (--cov ciblé désactive le gate global de facto ;
# préférez --no-cov si vous ne voulez pas de rapport)
pytest tests/unit/domains/agents/ --cov=src/domains/agents --cov-report=term-missing --cov-fail-under=0

# Générer rapport XML pour CI/CD
pytest --cov=src --cov-report=xml
```

### Interpréter Coverage Report

```
---------- coverage: platform win32, python 3.12.0 -----------
Name                                      Stmts   Miss  Cover   Missing
-----------------------------------------------------------------------
src/core/config/                           45      2    96%   67-68
src/core/security/                         32      0   100%
src/domains/agents/registry/agent_registry.py               78      5    94%   123-127
src/domains/agents/services/hitl/         156     12    92%   89-91, 145-152
-----------------------------------------------------------------------
TOTAL                                       311     19    94%
```

**Analyse** :
- **Stmts** : nombre de lignes exécutables
- **Miss** : lignes non exécutées
- **Cover** : % couverture
- **Missing** : numéros de lignes non couvertes

**Objectifs** :
- **≥80% global** : minimum pour production
- **100% core modules** : config, security, auth
- **≥90% agents** : nodes, services, tools
- **≥70% intégration** : acceptable car coûteux

### Coverage en CI

Le rapport XML est uploadé vers Codecov par le job `test-backend`
(`codecov-action`, flag `backend`, non bloquant) ; le **gate bloquant** est le
`--cov-fail-under=62` porté par `task test:backend:unit:coverage`, que ce job
appelle (voir la doctrine ratchet ci-dessus). Pour le reproduire en local,
lancer cette tâche — et non `test:backend:unit:fast`, qui troque la couverture
contre le parallélisme.

---

## CI/CD Testing Workflow

### Jobs de test backend (.github/workflows/ci.yml)

Le workflow **appelle des tâches**, il ne réécrit pas les commandes (ADR-151) :
les périmètres ci-dessous sont définis une seule fois, dans `Taskfile.yml`.
Lancer la tâche en local, c'est exécuter littéralement ce que la CI exécute.

| Job CI | Tâche appelée | Sélection | Gate |
|---|---|---|---|
| `test-backend` | `task test:backend:unit:coverage` | `tests/unit/`, `-m "not integration and not slow and not e2e and not benchmark and not multiprocess"` | couverture ≥ 65 % |
| `test-backend` (step 2) | `task test:backend:agents` | `tests/agents/`, `-m "not slow and not e2e and not benchmark and not multiprocess"`, `--no-cov` | tests verts |
| `test-backend` (step 3) | `task test:markers` | tous les nodeids + leurs markers | aucun test ne tourne dans **zéro** job (F006) |
| `test-backend-integration` | `task test:backend:integration` | `tests/integration/`, **puis** les tests marqués `integration` sous `tests/unit`/`tests/agents` (F006), `--no-cov` | tests verts |
| `python-compat` | *(CI-only)* | `tests/unit/`, même sélection, sur Python 3.13 | tests verts (F041) |

Points structurants :

- **Services provisionnés** : les deux jobs déclarent PostgreSQL
  (`pgvector/pgvector:pg16`) et Redis (`redis:7-alpine`) en services.
- **`TEST_DATABASE_URL`** (job integration) : seule variable DB qui survit au
  `load_dotenv(.env.test, override=True)` du conftest — elle route les
  fixtures vers le service PostgreSQL au lieu de Testcontainers
  (voir `tests/conftest.py::_detect_environment`). Les credentials du service
  (`test:test@localhost:5432/test_db`) reproduisent volontairement
  `.env.test` pour que les tests qui lisent `settings.database_url`
  directement (checkpointer LangGraph) atteignent la même base.
- **`LIA_REQUIRE_DB=1`** (F019) : ce job *promet* une base, donc une base
  injoignable doit faire échouer le job plutôt que skipper silencieusement des
  groupes entiers. Un vert obtenu par skips massifs est le pire résultat
  possible — il ressemble à une preuve.
- **Aucune liste `--ignore`** : les tests nécessitant une vraie base portent
  le marker `integration` et vivent dans `tests/integration/` — la
  quarantaine par `--ignore` (supprimée en 2026-07, ADR-113) est interdite :
  un test exclu sans marker ni ticket est un test qui ne revient jamais.
- **e2e / benchmark / multiprocess** restent hors CI PR (exécution manuelle
  via `task test:backend:slow`).

### Exécution locale

Ce ne sont pas des « équivalents » : ce sont les mêmes commandes.

```bash
# Suite unit AVEC couverture et le plancher CI — ce que fait le job test-backend
task test:backend:unit:coverage

# Variante rapide du hook pre-commit : xdist, sans couverture.
# Utile pour itérer, MAIS elle ne reproduit pas le gate de couverture.
task test:backend:unit:fast

# Suite agents + gate de markers
task test:backend:agents
task test:markers

# Suite integration (job test-backend-integration).
# Nécessite PostgreSQL + Redis (task dev:detach) et une base JETABLE :
# les fixtures droppent et recréent toutes les tables à chaque test.
docker exec lia-postgres-dev psql -U <user> -d postgres -c "CREATE DATABASE lia_test"  # une fois
TEST_DATABASE_URL="postgresql+asyncpg://<user>:<pass>@127.0.0.1:5432/lia_test" task test:backend:integration
```

Sans `TEST_DATABASE_URL`, la suite integration retombe sur Testcontainers
(nécessite un socket Docker fonctionnel). Le preflight AC-001 classe la
stratégie disponible et échoue avec un diagnostic actionnable si aucune ne l'est
— il ne laisse plus la suite partir pour skipper en masse.

### Avant un push

```bash
task ci:fast    # ~10 min : tous les gates CI ne nécessitant aucun service
```

Le hook pre-commit est plus étroit par construction (budget ~5 min) : il saute
les ratchets, le gate de markers, les tests de déploiement et les seuils de
couverture frontend. Chacun a déjà fait rougir un build après un commit vert.

### Pre-commit Hook

Le hook réel est `.github/hooks/pre-commit` (installé via
`task setup:hooks`, `git config core.hooksPath`). Son étape pytest :

```bash
pytest tests/unit/ --tb=short --no-cov -q \
  -m "not integration and not slow and not e2e and not benchmark and not multiprocess" \
  -n auto --dist loadscope
```

Sélection **identique** à `task test:backend:unit:fast`, et c'est vérifié :
`test_task_ci_pytest_parity_guard.py::test_the_hook_selects_exactly_what_the_fast_task_selects`
échoue si les deux divergent. L'expression du hook s'arrêtait à
`not integration and not slow` jusqu'au 2026-07-25 — le même ensemble en
pratique (aucun test `e2e`/`benchmark`/`multiprocess` ne vit sous `tests/unit`,
mesuré), mais le premier ajouté aurait tourné dans le hook et dans **aucun** job
CI.

`-n auto --dist loadscope` (pytest-xdist) : workers parallèles, tests groupés par
module pour que les fixtures de portée module ne soient jamais réparties entre
workers. C'est ce qui tient le budget de 5 minutes — la baseline mono-processus
était mesurée à ~12 min.

---

## Best Practices

### 1. Nommage des Tests

**Convention** : `test_<fonction>_<scénario>`

```python
# ✅ GOOD
def test_classify_approve_oui():
    """Test classification of 'oui' as APPROVE."""
    pass

def test_get_conversation_not_found():
    """Test retrieving non-existent conversation returns None."""
    pass

# ❌ BAD
def test_classifier():
    """Test classifier."""  # Trop vague
    pass

def test1():
    """First test."""  # Numéro non descriptif
    pass
```

### 2. AAA Pattern (Arrange-Act-Assert)

**Toujours structurer** tests en 3 phases claires :

```python
@pytest.mark.asyncio
async def test_create_conversation():
    # ============================================================================
    # ARRANGE - Setup test data and dependencies
    # ============================================================================
    repo = ConversationRepository(db=async_session)
    user_id = uuid.uuid4()
    title = "Test Conversation"

    # ============================================================================
    # ACT - Execute the code under test
    # ============================================================================
    conversation = await repo.create_conversation(user_id=user_id, title=title)

    # ============================================================================
    # ASSERT - Verify the results
    # ============================================================================
    assert conversation.id is not None
    assert conversation.user_id == user_id
    assert conversation.title == title
```

### 3. Un Concept par Test

**Principe** : chaque test vérifie **une seule assertion logique**.

```python
# ✅ GOOD - Tests séparés pour chaque concept
def test_approve_classification_decision():
    """Test 'oui' is classified as APPROVE."""
    result = classifier.classify("oui")
    assert result.decision == "APPROVE"

def test_approve_classification_confidence():
    """Test 'oui' classification has high confidence."""
    result = classifier.classify("oui")
    assert result.confidence >= 0.8

# ❌ BAD - Teste trop de concepts
def test_classifier_everything():
    """Test classifier works."""
    result = classifier.classify("oui")
    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8
    assert result.reasoning is not None

    result2 = classifier.classify("non")
    assert result2.decision == "REJECT"
    # ... 20 more assertions
```

### 4. Tests Déterministes

**Éviter** : random, datetime.now(), dépendances réseau non mockées.

```python
# ❌ BAD - Non déterministe
def test_create_conversation():
    conversation = create_conversation(title="Test")
    assert conversation.created_at < datetime.now()  # Peut échouer si rapide

# ✅ GOOD - Déterministe
def test_create_conversation():
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 1, 15, 12, 0, 0)
        conversation = create_conversation(title="Test")
        assert conversation.created_at == datetime(2025, 1, 15, 12, 0, 0)
```

### 5. Fixtures pour Setup Répété

**Éviter duplication** avec fixtures.

```python
# ❌ BAD - Duplication
def test_approve():
    classifier = HitlResponseClassifier(model="gpt-4")
    context = [{"tool_name": "search"}]
    result = classifier.classify("oui", context)
    assert result.decision == "APPROVE"

def test_reject():
    classifier = HitlResponseClassifier(model="gpt-4")
    context = [{"tool_name": "search"}]
    result = classifier.classify("non", context)
    assert result.decision == "REJECT"

# ✅ GOOD - Fixtures
@pytest.fixture
def classifier():
    return HitlResponseClassifier(model="gpt-4")

@pytest.fixture
def action_context():
    return [{"tool_name": "search"}]

def test_approve(classifier, action_context):
    result = classifier.classify("oui", action_context)
    assert result.decision == "APPROVE"

def test_reject(classifier, action_context):
    result = classifier.classify("non", action_context)
    assert result.decision == "REJECT"
```

### 6. Documentation des Tests

**Docstring explicite** pour chaque test.

```python
@pytest.mark.asyncio
async def test_hitl_streaming_three_chunk_protocol():
    """
    Test 3-chunk SSE protocol: metadata → tokens → complete.

    Verifies that HITL streaming follows the expected protocol:
    1. Metadata chunk: action_requests, review_configs
    2. Token chunks: streaming question generation
    3. Complete chunk: interrupt_id for resumption

    This ensures frontend can correctly parse SSE events.
    """
    pass
```

### 7. Tests de Edge Cases

**Toujours tester** :
- Valeurs null/None
- Listes vides
- Chaînes vides
- Valeurs négatives
- Limites (0, max)

```python
def test_search_contacts_empty_query():
    """Test search with empty query."""
    result = tool.execute(query="")
    assert result["data"]["count"] == 0

def test_search_contacts_special_characters():
    """Test search with special characters."""
    result = tool.execute(query="O'Brien")
    assert result["success"] is True

def test_list_conversations_zero_limit():
    """Test list with limit=0."""
    conversations = await repo.list_user_conversations(user_id, limit=0)
    assert len(conversations) == 0

def test_list_conversations_negative_limit():
    """Test list with negative limit raises ValueError."""
    with pytest.raises(ValueError):
        await repo.list_user_conversations(user_id, limit=-1)
```

---

## Troubleshooting

### Problème 1 : Tests Async échouent avec "Event Loop Closed"

**Symptôme** :

```
RuntimeError: Event loop is closed
```

**Cause** : fixture `event_loop` non configurée correctement.

**Solution** :

```python
# conftest.py
@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    import asyncio
    import sys

    # Windows compatibility
    if sys.platform == "win32":
        import selectors
        selector = selectors.SelectSelector()
        loop = asyncio.SelectorEventLoop(selector)
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop_policy().new_event_loop()

    yield loop
    loop.close()
```

### Problème 2 : Testcontainers échoue "Docker not available"

**Symptôme** :

```
testcontainers.core.exceptions.DockerException: Docker not available
```

**Cause** : Docker daemon non accessible.

**Solutions** :

```python
# Option 1: Skip si Docker indisponible
@pytest.fixture(scope="session")
def postgres_container():
    try:
        with PostgresContainer("pgvector/pgvector:pg16") as postgres:
            yield postgres
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")

# Option 2: Utiliser DB externe
@pytest.fixture(scope="session")
def test_database_url():
    # Check for external DB URL from environment
    external_db = os.environ.get("TEST_DATABASE_URL")
    if external_db:
        return external_db

    # Fallback to testcontainer
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        return postgres.get_connection_url()
```

### Problème 3 : Coverage faux positifs/négatifs

**Symptôme** : lignes marquées non couvertes alors qu'elles sont testées.

**Cause** : configuration coverage incorrecte.

**Solution** :

```toml
# pyproject.toml
[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/migrations/*",
    "*/__pycache__/*",
    "*/site-packages/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

### Problème 4 : Tests lents (>30s)

**Symptôme** : suite de tests prend plusieurs minutes.

**Diagnostic** :

```bash
# Profiler tests lents
pytest --durations=10  # Top 10 tests les plus lents
```

**Solutions** :

1. **Utiliser markers** : skip E2E en local

```bash
pytest -m "not e2e"  # Skip tests E2E lents
```

2. **Paralléliser avec pytest-xdist** :

```bash
pip install pytest-xdist
pytest -n auto  # Utilise tous les CPU cores
```

3. **Optimiser fixtures** : scope=session pour setup coûteux

```python
@pytest.fixture(scope="session")  # Partagé entre tests
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        yield postgres
```

### Problème 5 : Fixtures non reconnues

**Symptôme** :

```
fixture 'async_session' not found
```

**Cause** : conftest.py mal placé ou non découvert.

**Solution** :

```
apps/api/tests/
├── conftest.py          # ✅ Fixtures globales ici
├── agents/
│   ├── conftest.py      # ✅ Fixtures spécifiques agents
│   └── test_registry.py
└── core/
    └── test_security.py
```

**Vérifier découverte** :

```bash
pytest --fixtures  # Liste toutes les fixtures disponibles
```

### Problème 6 : Mock ne fonctionne pas

**Symptôme** : mock ignoré, vrai code exécuté.

**Cause** : patch appliqué au mauvais import path.

**Solution** :

```python
# ❌ BAD - Patch wrong path
# Code: from datetime import datetime
with patch("datetime.datetime") as mock_dt:  # ✅
    ...

# ❌ BAD - Patch declaration instead of usage
# Code: from src.services import SomeService
with patch("src.services.SomeService") as mock:  # ❌
    ...

# ✅ GOOD - Patch where it's used
# Code in test_file.py: from src.services import SomeService
with patch("test_file.SomeService") as mock:  # ✅
    ...
```

**Règle** : patch **où le code est importé**, pas où il est déclaré.

---

## Tests MCP (Model Context Protocol)

### Tests unitaires MCP

Le domaine MCP est couvert par deux groupes de tests : les tests d'infrastructure (`infrastructure/mcp/`) et les tests du domaine utilisateur (`domains/user_mcp/`).

**Infrastructure MCP** — `tests/unit/infrastructure/mcp/` :

| Fichier | Composant testé |
|---------|-----------------|
| `test_client_manager.py` | `MCPClientManager` : connexion, déconnexion, listing des outils, `read_me` auto-fetch |
| `test_tool_adapter.py` | `MCP ToolAdapter` : conversion des outils MCP en `BaseTool` LangChain, coercion de types, `_prepare_excalidraw()` |
| `test_registration.py` | Enregistrement dynamique des serveurs MCP, génération auto-description LLM |
| `test_schemas.py` | Validation Pydantic des schémas MCP (config serveur, résultats) |
| `test_security.py` | Sécurité des connexions MCP, validation des URLs |
| `test_oauth_flow.py` | Flux OAuth pour serveurs MCP nécessitant une authentification |
| ~~`test_excalidraw_iterative_builder.py`~~ | **sans objet** : pas de builder Excalidraw côté LIA (rendu délégué au serveur MCP externe, cf. MCP_INTEGRATION.md) |

**Domaine User MCP** — `tests/unit/domains/user_mcp/` :

| Fichier | Composant testé |
|---------|-----------------|
| `test_user_pool.py` | `UserMCPClientPool` : connexions éphémères par appel, pool lifecycle |
| `test_user_tool_adapter.py` | `UserMCPToolAdapter` : parsing JSON structuré → N `RegistryItem`, fallback single wrapper |
| `test_auth.py` | Authentification utilisateur pour connexions MCP |
| `test_service.py` | Service CRUD des serveurs MCP utilisateur |
| `test_schemas.py` | Validation des schémas de requête/réponse |
| `test_models.py` | Modèles SQLAlchemy pour la persistance MCP |
| `test_user_context.py` | `UserMCPToolsContext` : isolation ContextVar par requête |
| `test_compute_embeddings.py` | Calcul d'embeddings pour la recherche sémantique d'outils |
| `test_per_server_domains.py` | Mapping serveur MCP → domaines d'agents |
| `test_mcp_result_card.py` | Rendu des résultats MCP en cartes d'affichage |
| `test_pipeline_integration.py` | Intégration MCP dans le pipeline d'orchestration |

**Tests additionnels liés au MCP** :

| Fichier | Composant testé |
|---------|-----------------|
| `tests/unit/domains/agents/services/test_smart_planner_mcp_reference.py` | Injection du contenu `read_me` dans le prompt du planner |
| `tests/unit/domains/agents/orchestration/test_coerce_args_to_schema.py` | Coercion des arguments MCP vers le schéma attendu |

### Fixtures spécifiques MCP

```python
@pytest.fixture
def mock_mcp_server():
    """Mock MCP server avec outils prédéfinis."""
    server = AsyncMock()
    server.list_tools = AsyncMock(return_value=[
        {"name": "search", "description": "Search items", "inputSchema": {...}},
    ])
    server.call_tool = AsyncMock(return_value={"content": [{"type": "text", "text": "result"}]})
    return server

@pytest.fixture
def mock_tool_result_json():
    """Mock résultat MCP structuré (JSON array → N RegistryItems)."""
    return '[{"title": "Item 1", "url": "..."}, {"title": "Item 2", "url": "..."}]'
```

### Tests MCP Apps

Les MCP Apps (widgets HTML interactifs en iframe) sont testés via :

- **`McpAppSentinel`** : placeholder server-rendered pour les iframes MCP Apps (`domains/agents/display/components/mcp_app_sentinel.py`)
- **`build_mcp_app_output`** : construction du `UnifiedToolOutput` pour les MCP Apps (`infrastructure/mcp/utils.py`)
- **`is_app_only`** : filtrage des outils iframe-only hors du catalogue LLM (`infrastructure/mcp/utils.py`)

### Tests d'intégration MCP

Les tests d'intégration vérifient :
- `test_connection` : connexion réelle à un serveur MCP (marker `@pytest.mark.integration`)
- Auto-description : génération de description de domaine par LLM au `test_connection()`
- Lifecycle complet : découverte d'outils → enregistrement → appel → résultat

```bash
# Exécuter les tests MCP unitaires
cd apps/api
pytest tests/unit/infrastructure/mcp/ tests/unit/domains/user_mcp/ -v

# Exécuter les tests MCP d'intégration
pytest tests/integration/ -k "mcp" -v -m integration
```

---

## Tests Telegram (Multi-Channel)

### Tests unitaires Channels

Le système multi-channel est couvert par deux groupes : le domaine channels et l'infrastructure Telegram.

**Domaine Channels** — `tests/unit/domains/channels/` :

| Fichier | Composant testé |
|---------|-----------------|
| `test_schemas.py` | Validation Pydantic des messages entrants/sortants |
| `test_models.py` | `UserChannelBinding` : modèle de liaison utilisateur-canal |
| `test_service.py` | Service de gestion des canaux (CRUD, binding OTP) |
| `test_message_router.py` | Routage des messages vers le bon canal |
| `test_inbound_handler.py` | Traitement des messages entrants (dispatch vers le pipeline agent) |

**Infrastructure Telegram** — `tests/unit/infrastructure/channels/telegram/` :

| Fichier | Composant testé |
|---------|-----------------|
| `test_webhook_handler.py` | Handler webhook Telegram : réception, validation, `asyncio.create_task()` |
| `test_formatter.py` | Formatage des messages pour l'API Telegram (Markdown → HTML Telegram) |
| `test_hitl_keyboard.py` | Inline keyboards pour HITL : boutons Approve/Reject, callbacks |
| `test_voice.py` | Réception et conversion audio Telegram (OGG → WAV via pydub/ffmpeg) |

**Infrastructure Proactive** (partagée avec Heartbeat) — `tests/unit/infrastructure/proactive/` :

| Fichier | Composant testé |
|---------|-----------------|
| `test_notification_channels.py` | `NotificationDispatcher` : dispatch multi-canal (archive + SSE + FCM + Telegram) |

### Fixtures Telegram

```python
@pytest.fixture
def mock_telegram_bot():
    """Mock Telegram Bot API."""
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value={"message_id": 123})
    bot.answer_callback_query = AsyncMock(return_value=True)
    return bot

@pytest.fixture
def mock_bot_token():
    """Token Telegram factice pour les tests."""
    return "123456789:ABCDefGhIjKlMnOpQrStUvWxYz"
```

### Tests OTP (One-Time Password)

Le binding Telegram utilise un flux OTP stocké dans Redis :

- **Génération** : code OTP à 6 chiffres, TTL 5 minutes dans Redis
- **Validation** : vérification code + association `user_id` ↔ `chat_id`
- **Expiration** : le code expire après le TTL Redis
- **Anti-brute-force** : rate limiting sur les tentatives de validation (config `ChannelsSettings`)

### Tests HITL Telegram

- **Inline keyboards** : construction des boutons Approve/Reject/Modify pour les 6 types HITL
- **Callbacks** : traitement des réponses utilisateur via `callback_query` Telegram
- **Intégration pipeline** : transmission de la décision HITL au `LangGraph checkpoint` pour reprise du graph

```bash
# Exécuter les tests Channels/Telegram
cd apps/api
pytest tests/unit/domains/channels/ tests/unit/infrastructure/channels/ -v
```

---

## Tests Heartbeat (Notifications Proactives)

### Tests unitaires Heartbeat

Le système de notifications proactives est couvert par les tests du domaine heartbeat et de l'infrastructure proactive.

**Domaine Heartbeat** — `tests/unit/domains/heartbeat/` :

| Fichier | Composant testé |
|---------|-----------------|
| `test_proactive_task.py` | `HeartbeatProactiveTask` : implémentation du protocole `ProactiveTask` (select_target → generate_content → on_notification_sent) |
| `test_context_aggregator.py` | `ContextAggregator` : agrégation parallèle de 9 sources de contexte via `asyncio.gather` |
| `test_schemas.py` | `HeartbeatDecision` : structured output LLM (skip/notify), validation Pydantic |

**Infrastructure Proactive** — `tests/unit/infrastructure/proactive/` :

| Fichier | Composant testé |
|---------|-----------------|
| `test_eligibility.py` | `EligibilityChecker` : fenêtres temporelles, quotas, cooldowns, dedup cross-type |
| `test_runner.py` | `ProactiveTaskRunner` : orchestration batch (select → generate → dispatch) |
| `test_notification_channels.py` | `NotificationDispatcher` : dispatch multi-canal conditionnel |

### Fixtures Heartbeat

```python
@pytest.fixture
def mock_weather_api():
    """Mock réponse API météo pour le ContextAggregator."""
    return {
        "temperature": 22.5,
        "condition": "rain_start",
        "wind_speed": 45,
        "forecast": [...]
    }

@pytest.fixture
def mock_context_sources():
    """Mock des 9 sources de contexte agrégées."""
    return {
        "weather": {"temperature": 22.5, "condition": "sunny"},
        "calendar": [{"title": "Réunion", "start": "14:00"}],
        "tasks": [{"title": "Rapport", "due": "today"}],
        "interests": [...],
        # ... autres sources
    }
```

### Tests cross-type dedup

L'`EligibilityChecker` gère la déduplication entre types de notifications proactives (heartbeat et interests) :

- **Dedup heartbeat ↔ interests** : un utilisateur ne reçoit pas deux notifications sur le même sujet
- **Cooldowns par type** : délai minimum entre deux notifications du même type
- **Quotas journaliers** : limite configurable par utilisateur et par type
- **Fenêtres temporelles** : `heartbeat_notify_start_hour` / `heartbeat_notify_end_hour` (indépendant des interests)

### Tests token tracking

- **Comptage tokens** : vérification du suivi des tokens consommés par les appels LLM (décision + message)
- **Troncature** : les notifications centres d'intérêt sont tronquées si elles dépassent la limite de tokens
- **Budget** : respect du budget token par notification autonome

```bash
# Exécuter les tests Heartbeat
cd apps/api
pytest tests/unit/domains/heartbeat/ tests/unit/infrastructure/proactive/ -v
```

---

## Tests Scheduled Actions

### Tests unitaires Scheduled Actions

Les actions programmées permettent aux utilisateurs de planifier l'exécution différée de requêtes.

**Domaine Scheduled Actions** — `tests/unit/domains/scheduled_actions/` :

| Fichier | Composant testé |
|---------|-----------------|
| `test_schemas.py` | Validation Pydantic : création, mise à jour, récurrence, payload |
| `test_schedule_helpers.py` | Helpers de planification : calcul du prochain déclenchement, parsing cron-like |

### Fixtures Scheduled Actions

```python
@pytest.fixture
def sample_scheduled_action():
    """Action programmée de test."""
    return {
        "user_id": "user-123",
        "query": "Envoie le rapport hebdomadaire par email",
        "scheduled_at": datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
        "recurrence": "weekly",
        "timezone": "Europe/Paris",
        "enabled": True,
    }
```

### Tests timezone

- **Conversion UTC/local** : les actions sont stockées en UTC, affichées en timezone utilisateur
- **DST (heure d'été)** : vérification du comportement lors des changements d'heure
- **Fuseaux horaires multiples** : `Europe/Paris`, `America/New_York`, `Asia/Tokyo`
- **Helpers** : `schedule_helpers.py` fournit les fonctions de conversion testées unitairement

### Tests création et exécution

- **Création** : validation du payload, calcul du prochain déclenchement
- **Exécution** : dispatch vers le pipeline agent, gestion des résultats
- **Retry logic** : nouvelles tentatives en cas d'échec transitoire (erreur réseau, service indisponible)
- **Idempotence** : une action ne s'exécute pas deux fois pour le même créneau

### Tests auto-disable

- **Après N échecs** : une action est automatiquement désactivée après N échecs consécutifs (configurable via `.env`)
- **Notification** : l'utilisateur est notifié de la désactivation
- **Réactivation** : l'utilisateur peut réactiver manuellement une action désactivée

```bash
# Exécuter les tests Scheduled Actions
cd apps/api
pytest tests/unit/domains/scheduled_actions/ -v
```

---

## Tests Frontend (Vitest)

### Organisation et commandes

Les tests frontend (Vitest + jsdom + Testing Library) sont co-localisés avec le code source dans des répertoires `__tests__/` :

```
apps/web/src/
├── __tests__/setup.ts              # Setup global (mocks next/navigation, react-i18next, matchMedia,
│                                   #  stubs Resize/IntersectionObserver, pointer-capture, scroll)
├── reducers/__tests__/             # Machine à états du chat (chat-reducer)
├── lib/sse-handlers/__tests__/     # Pipeline SSE (handlers, batching, symétrie contrat backend)
├── lib/__tests__/                  # Logique pure (format, hitl-utils, password-validation, utils, briefing-utils…)
├── utils/__tests__/                # Utilitaires purs (timezone…)
├── stores/__tests__/               # Stores zustand (psycheStore, voiceModeStore)
├── components/**/__tests__/        # Composants (RTL) + helpers purs (debug formatters/validators…)
└── hooks/__tests__/                # Hooks — socle (useApiQuery/useApiMutation) + métier (useInterests, useConnectorHealth…)
```

```bash
# Exécuter les tests frontend
cd apps/web
pnpm test                # vitest run
pnpm test:coverage       # avec couverture + application des seuils

# ⚠️ PIÈGE : `pnpm test -- --coverage` ne fonctionne PAS — pnpm transmet le
# `--` littéralement et vitest ignore silencieusement le flag (aucun rapport).
# Toujours utiliser le script dédié `pnpm test:coverage`.
```

### Seuils de couverture (doctrine ratchet)

Les seuils vivent dans `apps/web/vitest.config.ts` (`coverage.thresholds`) et suivent la même doctrine ratchet que le gate backend :

- **Seuils fixés juste sous la valeur mesurée** au moment du verrouillage — jamais à l'aveugle.
- **Ils ne montent que lorsque de nouveaux tests arrivent, et ne descendent jamais** : baisser un seuil pour faire passer la CI est une régression à corriger, pas un réglage.
- Les zones critiques (reducers, sse-handlers, stores) sont **verrouillées à 100 %** par des seuils par glob ; un plancher global bas protège le reste.
- **Plancher global courant** (re-mesuré 2026-07-28, 3 769 tests / 303 fichiers) : statements 64 / branches 58 / functions 58 / lines 65 (valeurs mesurées 66.64 / 60.44 / 60.81 / 67.18). À relever à chaque nouvelle vague de tests — le déclencheur inscrit dans `vitest.config.ts` est `statements ≥ 67 et lines ≥ 68`, pas encore atteint, afin de garder ≥ 2 points de marge après un relèvement.
- Note vérifiée empiriquement (vitest 4.1) : le plancher global est calculé sur **tout** l'ensemble `include` — les fichiers matchés par un glob n'en sont pas soustraits.
- **Mesurer le verrou sur SA population, jamais sur un sur-ensemble.** Le verrou `settings/connectors/**/*.tsx` avait été calé sur l'agrégat du répertoire entier, hooks `.ts` non couverts inclus : population mesurée ≠ population gardée, **14,7 points de jeu sur les fonctions**, soit une régression massive qui serait passée en silence. Après un lot, mesurer l'agrégat du glob lui-même (`coverage-final.json` filtré sur le glob) et vérifier que **chaque** verrou tient dans ~3 points du mesuré — au-delà, il ne garde plus rien.
- **Un verrou dont le glob ne matche rien passe vacuellement.** Après avoir ajouté ou resserré un seuil par glob, le **falsifier une fois** : le monter au-dessus du mesuré et vérifier que vitest échoue en nommant le glob. Un glob mal orthographié valide toujours, silencieusement.
- **`testTimeout` se calibre, il ne se lève pas pour faire taire un test lent.** Le défaut vitest (5 s) n'a jamais été examiné ici ; les gros formulaires de réglages pilotent une vraie frappe `userEvent` (~29 ms/touche mesuré) qui s'étire ~×5 sous parallélisme complet **avec instrumentation de couverture** — le test de création le plus lourd tournait en 1,0 s seul et dépassait 5 s dans la suite complète : un test juste rapporté en échec. Réglé à 15 s depuis le pire cas mesuré (~3,3 s), même traitement que `teardownTimeout`. Avant de toucher à cette valeur : mesurer la distribution (`vitest run --reporter=verbose`, trier les durées) et vérifier qu'aucun composant ne re-rend anormalement — un coût par frappe très supérieur à ~30 ms est un défaut de composant, pas un problème de timeout.
- Le reporter texte masque les fichiers à 100 % (`skipFull`) : pour vérifier une valeur exacte, utiliser `--coverage.reporter=json-summary` et lire `coverage/coverage-summary.json`.

### Patterns de test frontend

- **Mocks au niveau module** avec `vi.mock` + `vi.hoisted` pour l'état configurable par test — pas de MSW. Le client SSE custom (fetch-stream) se teste par un *driver de chunks scriptés* : chaque test décrit la séquence exacte de chunks que le backend émettrait et la rejoue à travers le vrai pipeline (`processSSEChunk` → reducer). Voir `hooks/__tests__/useChat.test.ts`.
- **Immutabilité prouvée** : les états d'entrée des reducers sont gelés en profondeur (`src/__tests__/deep-freeze.ts`) — toute mutation in-place lève une TypeError en mode strict.
- **Symétrie du contrat SSE** : `lib/sse-handlers/__tests__/sse-symmetry.test.ts` pinne la liste des types du `Literal` backend (`ChatStreamChunk`) et la re-parse depuis `apps/api` quand le fichier est accessible (hôte + CI). Tout nouveau type backend force une décision frontend explicite (handler ou entrée documentée dans `ACKNOWLEDGED_UNHANDLED`).
- **Audio sans audio** : `useVoiceMode` se teste avec des fakes `AudioContext`/`AudioWorkletNode`/`getUserMedia` et des mocks Sherpa/VAD dont les callbacks capturés pilotent la machine (wake word, fin de parole, transcription).
- **Branches SSR** : un fichier de test peut opter pour l'environnement node (`// @vitest-environment node` en première ligne) pour couvrir les gardes `typeof window === 'undefined'` — le setup global est gardé en conséquence.
- **Déterminisme** : pas de timers réels (`vi.useFakeTimers`), `Math.random` stubé, `requestAnimationFrame` stubé pour le batching de tokens.
- **Logique pure d'abord** : les modules déterministes (`lib/format`, `lib/hitl-utils`, `utils/timezone`, `components/debug/utils/formatters`…) se testent sans mock, en pinnant les sorties exactes (locale fr normalisée). Les fonctions i18n reçues en paramètre (`TFunction`) sont stubées par un *echo* `key {params-json}` pour prouver la branche ET l'interpolation. Le `logger` est mocké pour garder la sortie propre.
- **Hooks socle testés directement** : `useApiQuery`/`useApiMutation` se testent via `renderHook` + `waitFor`/`act` en mockant `@/lib/api-client` avec `vi.hoisted` (l'objet mock doit être créé par `vi.hoisted` pour être visible dans la factory `vi.mock` hoistée) ; on conserve la vraie classe `ApiError` via `importActual` pour que `instanceof` fonctionne. Piège : sur le chemin d'erreur d'une mutation, capturer le rejet **dans** l'`act()` (`.catch`) pour que les `setState` d'erreur soient flushés avant l'assertion.
- **Hooks métier (CRUD) testés par dérivation** : mocker `useApiQuery`/`useApiMutation` (router le mock de query par endpoint quand le hook en appelle plusieurs), puis prouver les mises à jour optimistes en **appliquant l'updater capturé** (`setData.mock.calls`) à un état précédent connu — imiter `hooks/__tests__/useSpaces.test.ts` et `useInterests.test.ts`.

### Tests de composants (RTL) — harnais partagé

Le chantier de couverture des composants (≈ 280 composants, livré par lots à risque ascendant : présentationnels → formulaires → admin → chat/voice) s'appuie sur un harnais commun. **N'importer que depuis `@/__tests__/test-utils`** dans un test de composant.

- **`renderWithProviders(ui, options?)`** (`src/__tests__/test-utils.tsx`) monte l'UI dans la pile de providers qui *throw* sans contexte (`ColorThemeProvider`, `FontProvider`) plus ceux couramment requis par les primitives (`TooltipProvider`, `QueryClientProvider` non-retry). Il **ne fournit délibérément ni auth ni couche API réelle** : les hooks de données (`useApiQuery`/`useApiMutation`/`useAuth`) se mockent par test. Retourne le `RenderResult` RTL augmenté de `{ user, queryClient }`. Le fichier ré-exporte toute la surface RTL + `userEvent`.
- **`userEvent` est le standard** des nouvelles interactions (plus fidèle que `fireEvent`) : `const { user } = renderWithProviders(<C/>); await user.click(...)`. Les tests `fireEvent` pré-existants ne sont pas réécrits.
- **Builders de mock de hooks** (`src/__tests__/api-mocks.ts`) : `dataQuery(data)` / `loadingQuery()` / `errorQuery(msg)` pour `useApiQuery` ; `mutationResult({ mutate })` pour `useApiMutation`. Couvrir systématiquement la matrice **loading / empty / error / data** des composants pilotés par la donnée.
- **Factories de données du domaine** (`src/__tests__/factories.ts`) : `makeUser(over)` / `makeConnector(over)` / `makeUsageLimitsUser(over)` construisent une entité **complète et typée** depuis un `Partial<T>`. Y ajouter une factory dès qu'un **second** test a besoin de la même forme.
- **Spies typés au contrat** (`api-mocks.ts`) : `mutateSpy()` et `setDataSpy<T>()` au lieu d'un `vi.fn()` nu — un `vi.fn()` sans implémentation s'élargit en `Mock<Procedure | Constructable>`, que `tsc` refuse face aux signatures de `useApiMutation`/`useApiQuery` (le test passe, le typage non). `takeUpdater(spy)` récupère l'updater fonctionnel remis à `setData` et **échoue bruyamment** si le composant a écrit une valeur brute : c'est le moyen de prouver un *optimistic update* sans cast (imiter `AdminConnectorsSection.test.tsx`, qui vérifie les deux branches du réducteur : patch d'une config existante vs création).
- **États post-transition** : après une mutation optimiste (`useOptimistic` + `useTransition`), le retour à l'état confirmé arrive **quand la transition se règle**, parfois après le toast. Assertez-le avec `findBy*`/`waitFor`, jamais avec un `getBy*` synchrone — sinon le test passe seul et casse sous charge parallèle.
- **Règle de contrat (F057) — les builders honorent le type public.** Tout builder de props/données prend un `Partial<T>` et retourne le type réel (`T`) ; les retours de hooks mockés se typent au contrat via `Partial<ReturnType<typeof useXxx>>`. **Jamais** `as never` / `as any` / `Record<string, unknown>` en surcharge : ils rouvrent la classe de bugs que le typage doit fermer (un override typé attrape une faute de frappe ou un type faux à la compilation — c'est ainsi que la remédiation a mis au jour un `previewUrl: null` non conforme et un `error` traité en booléen au lieu d'`Error`). Un cast d'échappement n'est admis qu'à une **frontière externe non constructible** (DOM `Window`, `Response` fetch, `MediaStream`, `TFunction` i18next) ou pour injecter délibérément une valeur invalide dans un test de garde.
- **i18n et thème sont mockés globalement** (`src/__tests__/setup.ts`) : `react-i18next` **et** `@/i18n/client` renvoient `t: key => key` (on **assertit sur la clé** de traduction, jamais sur le texte traduit) ; `next-themes` est un passthrough avec `useTheme` déterministe (`resolvedTheme: 'light'`). Un test peut surcharger l'un ou l'autre avec son propre `vi.mock` local.
- **Barre de qualité (Definition of Done)** — interdit les tests-alibi : un test de composant **assertit un comportement observable** (matrice de variantes qui changent le rendu · états conditionnels loading/empty/error/success · interactions → callback avec les bons arguments ou changement d'état observé · a11y quand c'est une vraie feature : combobox, dialog, listbox · garde-fous : stale-response, unmount-safety — imiter `ConsumptionExportSection.autocomplete.test.tsx`). **Interdit** : un test dont la seule assertion est « ça rend sans planter ».
- **Primitives shadcn triviales exclues de la mesure** : les re-exports Radix fins ou wrappers d'un seul élément HTML (`separator`, `slider`, `switch`, `label`, `tooltip`, `accordion`, `tabs`, `dialog`, `alert-dialog`, `dropdown-menu`, `input`, `textarea`, `skeleton`, `toaster`) sont dans `coverage.exclude` (`vitest.config.ts`) — les tester relève du théâtre de couverture. Les primitives à vraie logique/variants restent mesurées et testées.
- **Ratchet par lot** : à la fin d'un lot, mesurer (`pnpm test:coverage --coverage.reporter=json-summary`) puis **verrouiller la couverture acquise par un glob par-répertoire** (ex. `'src/components/ui/**': { statements: N, … }`) fixé juste sous la valeur mesurée. Les globs par-répertoire sont des clés additives (moins de collision avec le plancher global sous édition parallèle). Exemplars de référence : `ui/__tests__/pagination.test.tsx` (logique pure), `ui/__tests__/search-input.test.tsx` (interaction), `psyche/__tests__/PsycheLLMSummary.test.tsx` (data-driven).

### Pièges connus

- **Stabilité des mocks de hooks** : un mock dont les fonctions retournées changent d'identité à chaque render (ex. `withContext`) re-déclenche tous les effets qui en dépendent — mimer la mémoïsation du vrai hook (fonction définie une fois dans la factory du mock). **Cas vécu (2026-07-15)** : le mock global d'i18n renvoyait `{ t: key => key }` construit *à chaque appel* ; tout composant gardant `t` dans les dépendances d'un `useCallback`/`useEffect` (`AdminUsersSection`, `AdminUsageLimitsSection`, les sections de tarification…) partait en **boucle infinie render → fetch → render**, et le test *pendait* au lieu d'échouer. Le stub i18n de `setup.ts` est désormais construit une seule fois via `vi.hoisted` et partagé par les mocks `react-i18next` et `@/i18n/client` — ne jamais revenir à une fabrication par appel.
- **`vi.mock` de `sonner`** : mocker l'objet `toast` complet (`loading`, `success`, `warning`, `error`, `info`) — les handlers SSE l'utilisent pour la compaction et les limites d'usage.
- **`vi.mock` n'intercepte pas un `await import()` runtime** (piège coûteux, vécu sur `AdminRAGSpacesSection`). Un composant qui charge le client API *dans son handler* (`const { default: apiClient } = await import('@/lib/api-client')`) continue d'utiliser le **vrai** client si le module n'est pas dans le graphe résolu du test : les requêtes échouent alors sur une URL relative (`Failed to parse URL`) et disparaissent dans le `catch {}` du composant — le test ne casse pas, il observe juste un écran vide. Deux parades : (1) ajouter un **import statique** du module dans le fichier de test et épingler le câblage (`expect(apiClient.get).toBe(get)`) ; (2) quand cela ne suffit pas, ne pas mocker le client du tout et faire tourner le **vrai** `ApiClient` sur un `fetch` stubbé (`vi.stubGlobal('fetch', …)` renvoyant de vraies `Response`) — hermétique, et la construction d'URL comme le parsing de réponse restent testés. Modèle : `AdminRAGSpacesSection.test.tsx`.
- **Un bloc replié ne monte pas ses enfants** : au-delà du wrapper `<Accordion defaultValue={[value]}>`, beaucoup de sections cachent leur corps derrière un *toggle maître* (`JournalsSettings` : tout le panneau dépend de `settings.journals_enabled`). Une fixture « vide » ne rend alors que l'en-tête, et les requêtes par rôle échouent sans raison apparente — armer le flag dans la fixture.
- **Un état vide qui est aussi l'état initial ne prouve rien** : asserter en plus que la requête a bien eu lieu (`expect(get).toHaveBeenCalledWith(endpoint)`), sinon le test reste vert sur un fetch cassé.
- **Un module de hook exporte souvent plus que son hook** (constantes, tables d'icônes, types) que le composant importe aussi. Une factory `vi.mock` qui ne renvoie que le hook fait échouer le rendu (`No "X" export is defined on the mock`) — utiliser `importOriginal` et ne remplacer que le hook : `vi.mock('@/hooks/useX', async importOriginal => ({ ...(await importOriginal()), useX }))`.
- **Une fixture partielle peut casser le rendu, pas seulement l'assertion** : plusieurs sections lisent leurs réglages sans chaînage optionnel (`settings.interests_notify_start_hour.toString()`). Un `settings: {}` fait planter le composant avec un `TypeError` opaque — renseigner les champs réellement lus (les repérer par `grep 'settings\.'` sur le composant).
- **`userEvent.setup()` remplace `navigator.clipboard`** : installer son propre stub *avant* le rendu ne sert à rien, user-event l'écrase. Espionner **après** le rendu — `vi.spyOn(navigator.clipboard, 'writeText')` — et seulement là. Modèle : `ChatMessage.test.tsx`.

- **Un stub d'API navigateur doit accepter les arguments du vrai constructeur**, même s'il n'en fait rien. Le stub global d'`IntersectionObserver` n'avait qu'un constructeur par défaut : il *jetait* le callback, si bien qu'aucun test ne pouvait déclencher une intersection — `ChatMessageList.test.tsx` a dû embarquer son propre `FakeIntersectionObserver` complet pour tester la pagination. Effet de bord inattendu : CodeQL résolvait le global vers ce stub et signalait **7 fois** `js/superfluous-trailing-arguments` sur du code de production parfaitement correct (`new IntersectionObserver(cb, { rootMargin })`). Le stub implémente désormais l'interface (`root`, `rootMargin`, `scrollMargin`, `thresholds` dérivés des options), ce qui a permis de supprimer le double *cast* `as unknown as typeof IntersectionObserver` — un contournement de contrat qui masquait précisément ce trou.

  **Le callback est stocké, jamais appelé** : rien ne déclenche d'intersection tout seul. C'est la condition de non-régression — les composants qui n'agissent qu'au passage de leur sentinelle dans le viewport (`AnimatedCounter`, `FadeInOnScroll`, `ChapterRail`…) gardent exactement le comportement qu'ils avaient. Un test qui *veut* une intersection installe son propre double via `vi.stubGlobal`.
- **L'égalité structurelle sur un `File` est aveugle** : `name`/`type` ne sont pas des propriétés énumérables, donc deux `File` différents comparent égaux (`toHaveBeenCalledWith(file)` passe pour n'importe quel fichier, et `not.toHaveBeenCalledWith(autre)` échoue toujours). Asserter sur les noms extraits des appels (`mock.calls.map(([f]) => f.name)`), ce qui suppose un `vi.fn<Hook['uploadFile']>()` typé pour que la destructuration reste sûre. Modèle : `ChatInput.test.tsx`.
- **Agir dans le même tick que le montage fait courser l'effet de montage — et cette gêne de test est souvent un vrai défaut.** `useConnectorPreferences` (chargement initial) et `useBulkConnect` (reprise de file `localStorage`) écrasaient l'action déclenchée juste après `renderHook`. La tentation est d'attendre l'effet (`await act(async () => {})`) et de passer à autre chose ; c'est un **contournement** qui ne se justifie que si la fenêtre est réellement inaccessible en production. Ici elle ne l'était pas — un simple re-rendu du parent avec un nouveau tableau `connectors` (l'ajout/retrait optimiste de `UserConnectorsSection`) suffit à la rouvrir. Les deux hooks ont donc été corrigés à la source (revendication locale non écrasable + garde de requête en vol ; verrou d'exclusion entre reprise et démarrage utilisateur), et l'attente n'a été conservée que là où elle **documente** un comportement voulu (un run lancé pendant la reprise est ignoré). Règle : quand un test doit « attendre » pour être juste, se demander d'abord *qui* garantit cet ordre en production.
- **Un test de non-régression qui passe aussi *avant* le correctif ne prouve rien.** Après chaque correction de race, remettre temporairement l'ancienne logique et vérifier que les nouveaux tests **virent au rouge** (ici : écrasement de la valeur locale, double requête, chevauchement des files — dont un timeout révélateur). Sans cette vérification, on ne sait pas si l'on teste le correctif ou le hasard d'un ordonnancement.
- **Le `t` mocké absorbe ses options** : `toast.error(t('x.y', { max: 10 }))` n'envoie **qu'un seul** argument au toast (le retour de `t`). Attendre `toHaveBeenCalledWith(key)`, jamais `(key, expect.anything())`.
- **Vérifier la garde réelle avant d'asserter une absence** : l'`input[type=file]` de `ChatInput` est monté en permanence — seul le bouton trombone est derrière `attachmentsEnabled`. Une assertion « rien n'est rendu » construite sur une garde supposée échoue et, pire, aurait pu passer pour de mauvaises raisons.
- **Interagir avec un formulaire avant l'hydratation React échoue en SILENCE** (lane E2E). Une page rendue côté serveur est visible, remplissable et cliquable **avant** que React n'attache ses handlers : un `<form>` dont l'`onSubmit` n'est pas encore attaché part alors en **soumission GET native**. Le clic « marche », l'URL gagne un `?champ=valeur`, et la logique applicative n'a jamais tourné — aucune erreur, aucune requête. Mesuré le 2026-07-19 sur le serveur dev : la page de connexion n'était toujours pas hydratée après `networkidle`, seulement plusieurs secondes plus tard ; un build de production hydrate quasi instantanément, d'où un test **vert en CI et rouge en local** jusqu'au jour où un runner lent le fait flaker aussi. Parade : `waitForHydration(page)` (`e2e/fixtures/hydration.ts`) avant toute interaction avec un formulaire. Piège dans le piège : une `<input type="checkbox">` native bascule **sans** JavaScript — la voir réagir ne prouve donc rien sur l'hydratation.
- **`lia-web-dev` ne voit PAS vos éditions sans redémarrage** (bind-mount Windows → conteneur Linux : les événements inotify ne traversent pas, Fast Refresh ne se déclenche jamais). Le fichier source *est* bien à jour dans le conteneur (`docker exec lia-web-dev grep … /monorepo/apps/web/src/…`), mais Next sert un bundle compilé **avant** l'édition. Conséquence vécue : une validation Playwright a conclu que la sémantique modale ajoutée à `ImageLightbox` était absente du DOM — alors qu'elle l'était seulement du bundle. **Toujours `docker restart lia-web-dev` avant une validation navigateur**, et attendre la recompilation (60–120 s par page). Symptôme distinctif : le DOM ne contient pas ce que la source contient.
- **L'instantané d'échec de Playwright (`error-context.md`) est un instantané de l'arbre d'accessibilité, pas du DOM** : un élément présent dans le DOM peut y être élagué. Pour trancher, sonder le DOM (`page.evaluate(() => document.querySelectorAll('[role=dialog]').length)`) avant de conclure que le composant est en cause.
- **Un import `import type` vers un module inexistant ne casse pas les tests** : il est effacé à la compilation, donc la suite passe au vert alors que `tsc` échoue (`Cannot find module '@/types/rag'`). Corollaire : **une suite verte ne vaut pas typage vert** — `tsc --noEmit --incremental false` est un gate distinct, et c'est lui qui a révélé que la fixture `RAGDocument` inventait la moitié de ses champs (`filename`/`file_type` au lieu de `original_filename`/`content_type`).
- **Ne jamais coder en dur un intervalle/seuil dans un test** : `useSpaceDocuments` sonde toutes les **5 s** (j'avais supposé 3 s, le test échouait à juste titre). Exporter la constante et l'importer dans le test — une modification de cadence casse alors le code, pas silencieusement l'assertion. Appliqué à `STATUS_POLL_INTERVAL_MS`, `AUTO_REFRESH_INTERVAL_MS`, `EXECUTING_REFRESH_INTERVAL_MS`.
- **Un composant piloté par le contenu ne se teste pas avec le stub i18n global** : `FAQContent` lit `parseInt(t('faq.sections.X.count'))` ; avec un `t` qui renvoie la clé, tout vaut `NaN` et la page est vide — les tests seraient verts et vacants. Surcharger `@/i18n/client` **dans le fichier de test** avec un petit dictionnaire réaliste (accents + HTML) : la recherche, le *stripping* et le surlignage redeviennent observables sans coupler la suite au contenu éditorial.
- **Un effet qui déplace le focus ne doit JAMAIS dépendre d'un callback de props.** Presque tous les `onClose`/`onSelect` sont passés en flèche inline (`onClose={() => setOpen(false)}`) : leur identité change à chaque rendu du parent, donc un `useEffect(..., [isOpen, onClose])` se ré-exécute à chaque rendu. Tant que l'effet ne fait qu'ajouter/retirer un écouteur, c'est gratuit ; dès qu'il **prend ou rend le focus**, chaque rendu du parent arrache le focus au contrôle que l'utilisateur clavier venait d'atteindre. Vécu sur `ImageLightbox` (2026-07-19), et le parent y est un message de chat qui re-rend en continu pendant le streaming — donc en permanence. Parade : scinder en deux effets, le clavier sur `[isOpen, onClose]`, la propriété du focus sur `[isOpen]` seul. Corollaire de test : monter le composant isolément ne révèle jamais ce défaut — il faut un **hôte qui re-rend**, et le déclencher par `rerender()`, pas par un clic (un clic pointeur donne le focus au bouton cliqué et masque exactement ce qu'on mesure).
- **`aria-modal="true"` sans piège à focus est un docstring qui ment** : l'attribut annonce aux technologies d'assistance que le reste de la page est inerte, mais rien dans le DOM ne l'applique — la tabulation suivante sort vers un contenu qu'on vient de déclarer inexistant. Soit on implémente le piège (cycle sur les focusables du dialogue, plus un rattrapage quand le focus s'est échappé sur `body` — cas réel : le bouton se désactive sous les doigts de l'utilisateur), soit on n'écrit pas l'attribut. La vérification appartient au navigateur : `user-event` n'approxime l'ordre de tabulation que grossièrement sous jsdom, donc doubler l'assertion en E2E.
- **recharts ne peint pas sous jsdom** : un `ResponsiveContainer` a une taille nulle, ses internes ne sont jamais rendus. Épingler la logique autour (URL de requête par plage, états chargement/vide/graphé, exclusion des snapshots `reset_*`) plutôt que le contenu du graphe — le JSX déclaratif est de toute façon exécuté, donc couvert. Modèle : `PsycheHistory.test.tsx`.
- Les tests tournent sur l'hôte (et en CI) — dans le container `lia-web-dev`, le test de synchronisation du contrat SSE se skip proprement (seul `apps/web` y est monté).

---

## Gardes de contrat backend (campagne 2026-07-24)

Cinq gardes exécutables ont été ajoutées pour fermer des classes de bugs
**silencieux** — celles qui ne lèvent rien, ne loguent rien, et se manifestent
uniquement par une réponse fausse ou un widget absent.

| Garde | Ce qu'elle empêche |
|---|---|
| `tests/unit/test_langgraph_state_keys_guard.py` | Un nœud du graphe qui écrit une clé absente de `MessagesState` : LangGraph la **jette sans un mot** au checkpoint, le nœud aval lit `None` et prend la branche dégradée. |
| `tests/unit/test_locale_normalization_guard.py` | Toute normalisation de locale ad hoc (`locale.split("-")[0]`, `language[:2]`) hors de `normalize_language` : un `zh` brut du frontend rate les tables backend canoniques `zh-CN` et l'utilisateur chinois lit du français. |
| `tests/unit/domains/agents/analysis/test_query_intelligence_roundtrip_guard.py` | Un champ ajouté d'un seul côté de la paire `to_serializable_dict` / `reconstruct_query_intelligence` — il se réinitialise à son défaut après chaque reprise HITL. |
| `tests/unit/domains/connectors/clients/test_provider_parity_contract.py` | Une dérive de signature ou de contrat entre les providers d'une catégorie fonctionnelle (`protocols.py` n'était jamais importé à l'exécution : le contrat était décoratif). |
| `tests/unit/domains/agents/display/test_component_rendering_contract.py` | Une carte qui n'échappe pas ses données, qui émet une URI `javascript:`, ou qui lève sur un payload dégradé. |

### Leçons transférables

- **Le périmètre d'un `try/except` décide de la gravité.** `response_node` enveloppe *tout* le rendu des cartes dans un `except (ValueError, KeyError, TypeError, AttributeError, RuntimeError)` qui se contente d'un `logger.warning`. Une seule carte qui lève ne dégrade donc pas *sa* carte : elle supprime **toutes** les cartes de la réponse. D'où l'invariant testé « un composant ne lève jamais », vérifié sur des payloads que les producteurs émettent réellement (champs `null`, scalaire à la place d'une liste, nombre en chaîne).
- **Un `assert "onerror=" not in html` n'est pas un oracle.** Du contenu correctement échappé contient toujours la sous-chaîne. Seul un **parseur** distingue un attribut d'une chaîne qui y ressemble : le contrat de rendu utilise `html.parser` et assertit sur les *attributs* et les *valeurs d'URI* réellement parsés.
- **`html.escape` ne protège pas une URI.** `javascript:alert(1)` ne contient aucun caractère qu'`escape` touche. La liste blanche de schémas (`display/urls.py::safe_url`) est le seul rempart, et elle doit neutraliser les caractères de contrôle que le navigateur ignore *avant* de résoudre le schéma (`java	script:`).
- **Une garde doit porter son propre oracle.** Chaque garde AST embarque un test qui lui soumet le défaut historique et vérifie qu'elle le signale — sans quoi une garde verte peut simplement ne rien scanner.
- **Une exemption se justifie et se périme.** Les frontières qui parlent un autre vocabulaire (ElevenLabs en ISO-639-1, l'attribut `lang` d'une page web) sont exemptées avec leur raison écrite, et un test `shrink-only` supprime l'exemption dès que le code n'en a plus besoin.
- **Un test de round-trip n'est contraignant que si la fixture bouge chaque champ.** Deux champs de `QueryIntelligence` étaient laissés à leur valeur par défaut : l'identité `serialize → reconstruct → serialize` était **vacante** pour eux. Un test vérifie désormais que chaque champ sérialisé a une valeur distinguable du défaut.
- **`dict.get(clé, {})` ne défend pas contre une valeur `None` explicite.** Le défaut ne s'applique qu'à une clé *absente*. `data.get("displayName", {}).get("text")` levait dès que le provider renvoyait `displayName: null` — et coûtait toutes les cartes de la réponse.
- **Pydantic v2 n'inline jamais un modèle imbriqué** : il l'émet dans `$defs` et le référence par `$ref`. Un parcours de schéma qui ne suit pas les `$ref` mesure une profondeur de 1 sur un modèle imbriqué 7 fois.
- **L'attribut `style` est une surface XSS distincte de `href`/`src`, et le contrat de rendu ne l'exerçait pas.** `route_card` interpolait la couleur de ligne d'un transport (donnée Google Routes API) verbatim dans `style="background-color: {color}"` ; une couleur `#fff" onmouseover="alert(1)` fermait l'attribut et injectait un handler. `html.escape` ne protège pas ici — la valeur ne contient aucun caractère qu'il touche. Parade : une liste blanche de couleurs CSS (`display/urls.py::safe_css_color`, hex ou mot-clé, rien d'autre). Leçon de garde : le payload hostile du contrat inter-cartes ne peuplait aucune étape *transit*, donc la classe échappait à la garde générale — un contrat de sécurité ne couvre que les champs qu'il peuple réellement. Le payload hostile inclut désormais une étape transit à couleurs malveillantes.
- **Une couverture faible en scope `tests/unit` seul ne signifie pas « non testé »** : les modules d'orchestration/nœuds sont couverts par `tests/agents`, invisible dans un instantané `--cov` limité à `tests/unit`. Avant d'investir sur un module « à 19 % », mesurer sa couverture *union* (unit + agents) — sinon on réécrit des tests qui existent. Contre-exemple utile : le `ReferenceResolver` du plan était réellement à 19 % même union (55 tests agents n'exerçaient que `ConditionEvaluator`, pas le moteur de résolution `$steps`/`context`/`items`/wildcards/filtres JSONPath).

---

## Références

### Documentation Officielle

- **Pytest** : [https://docs.pytest.org](https://docs.pytest.org)
- **pytest-asyncio** : [https://pytest-asyncio.readthedocs.io](https://pytest-asyncio.readthedocs.io)
- **pytest-cov** : [https://pytest-cov.readthedocs.io](https://pytest-cov.readthedocs.io)
- **Testcontainers Python** : [https://testcontainers-python.readthedocs.io](https://testcontainers-python.readthedocs.io)
- **unittest.mock** : [https://docs.python.org/3/library/unittest.mock.html](https://docs.python.org/3/library/unittest.mock.html)

### Documentation Interne

- [CONTRIBUTING.md](../../CONTRIBUTING.md) : workflow de contribution avec tests
- [GUIDE_TOOL_CREATION.md](./GUIDE_TOOL_CREATION.md) : tests de tools ConnectorTool
- [GUIDE_PROMPTS.md](./GUIDE_PROMPTS.md) : tests de prompts LLM

### Outils Complémentaires

- **pytest-xdist** : exécution parallèle des tests
- **pytest-benchmark** : benchmarking de performance
- **pytest-mock** : simplification du mocking
- **hypothesis** : property-based testing

---

**Fin du Guide Pratique : Tests et Qualité**

Pour toute question, consulter :
- **Guide complet** : [GUIDE_TESTING.md](./GUIDE_TESTING.md) (ce document)
- **Issues GitHub** : signaler bugs/suggestions de tests
- **Équipe QA** : contact pour stratégies de test avancées
