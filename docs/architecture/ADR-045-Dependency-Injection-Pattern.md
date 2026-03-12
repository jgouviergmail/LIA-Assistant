# ADR-045: Dependency Injection Pattern

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: FastAPI Depends() patterns with Repository and Service layers
**Related ADRs**: ADR-008, ADR-040

---

## Context and Problem Statement

L'application nécessitait une architecture d'injection de dépendances robuste :

1. **Type Safety** : Injection typée avec validation statique
2. **Layered Architecture** : Repository → Service → Router
3. **Session Management** : Gestion cohérente des sessions DB
4. **Testability** : Mocking facilité pour les tests unitaires

**Question** : Comment structurer l'injection de dépendances pour une application FastAPI async avec SQLAlchemy ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **FastAPI Depends()** : Chaînes de dépendances type-safe
2. **Repository Pattern** : Abstraction CRUD générique
3. **Service Layer** : Logique métier isolée
4. **Session Lifecycle** : Commit/rollback automatique

### Nice-to-Have:

- Unit of Work pattern
- Lazy singleton initialization
- Thread-safe singletons

---

## Decision Outcome

**Chosen option**: "**FastAPI Depends() + Generic Repository + Service Layer + UoW**"

### Dependency Chain Architecture

```
Cookie (lia_session)
        ↓
get_session_store() → SessionStore (with Redis connection)
        ↓
get_db() → AsyncSession (PostgreSQL connection)
        ↓
get_current_session(cookie, session_store, db) → User
        ↓
    get_current_active_session(user) → User (verified is_active)
        ↓
    get_current_verified_session(user) → User (verified is_verified)
    get_current_superuser_session(user) → User (verified is_superuser)
```

### Authentication Dependency Chain

```python
# apps/api/src/core/session_dependencies.py

# Level 1: Session Store Provider
async def get_session_store() -> SessionStore:
    """Dependency to get SessionStore instance."""
    redis = await get_redis_session()
    return SessionStore(redis)

# Level 2: Current Session (requires session_store + db)
async def get_current_session(
    lia_session: Annotated[str | None, Cookie()] = None,
    session_store: SessionStore = Depends(get_session_store),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current user from session cookie."""
    if not lia_session:
        raise_user_not_authenticated()

    session = await session_store.get_session(lia_session)
    if not session:
        raise_session_invalid()

    user_repo = UserRepository(db)
    user = await user_repo.get_user_minimal_for_session(UUID(session.user_id))
    return user

# Level 3: Active Session (depends on get_current_session)
async def get_current_active_session(
    user: User = Depends(get_current_session),
) -> User:
    """Get current active user."""
    if not user.is_active:
        raise_user_inactive(user.id)
    return user

# Level 4: Verified Session (depends on active)
async def get_current_verified_session(
    user: User = Depends(get_current_active_session),
) -> User:
    """Get current verified user."""
    if not user.is_verified:
        raise_user_not_verified(user.id)
    return user

# Level 5: Superuser Session (depends on active)
async def get_current_superuser_session(
    user: User = Depends(get_current_active_session),
) -> User:
    """Get current superuser."""
    if not user.is_superuser:
        raise_admin_required(user.id)
    return user
```

### Route Handler Usage

```python
# apps/api/src/domains/users/router.py

@router.get("", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    is_active: bool | None = Query(None),
    user: User = Depends(get_current_superuser_session),  # Auth + Superuser
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """Get paginated list of users (admin only)."""
    service = UserService(db)
    return await service.get_all_users(page=page, page_size=page_size)

@router.patch("/{user_id}", response_model=UserProfile)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Update user profile."""
    check_user_ownership_or_superuser(user_id, current_user, "update this user")
    service = UserService(db)
    return await service.update_user(user_id, data)
```

### Generic Base Repository

```python
# apps/api/src/core/repository.py

class BaseRepository[ModelType: DeclarativeBase]:
    """Generic repository for common CRUD operations."""

    def __init__(self, db: AsyncSession, model: type[ModelType]) -> None:
        self.db = db
        self.model = model
        self.model_name = model.__name__

    async def get_by_id(
        self,
        id: UUID,
        include_inactive: bool = False,
    ) -> ModelType | None:
        """Get model by ID with soft-delete awareness."""
        query = select(self.model).where(self.model.id == id)

        if not include_inactive and hasattr(self.model, "is_active"):
            query = query.where(self.model.is_active)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> ModelType:
        """Create a new model instance."""
        instance = self.model(**data)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def update(
        self,
        instance: ModelType,
        data: dict[str, Any],
    ) -> ModelType:
        """Update a model instance."""
        for key, value in data.items():
            setattr(instance, key, value)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def soft_delete(self, instance: ModelType) -> ModelType:
        """Soft delete by setting is_active=False."""
        if not hasattr(instance, "is_active"):
            raise AttributeError(f"{self.model_name} does not support soft delete")
        return await self.update(instance, {FIELD_IS_ACTIVE: False})

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        include_inactive: bool = False,
        **filters: Any,
    ) -> PaginationResult[ModelType]:
        """Get paginated results with filtering."""
        # Implementation...
        return PaginationResult(items=items, total=total, page=page, ...)
```

### Domain Repository Extension

```python
# apps/api/src/domains/users/repository.py

class UserRepository(BaseRepository[User]):
    """Repository for user management with domain-specific overrides."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, User)

    async def get_by_id(
        self,
        user_id: UUID,
        include_inactive: bool = False,
    ) -> User | None:
        """Get user by ID with connectors eagerly loaded."""
        query = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.connectors))
        )
        if not include_inactive:
            query = query.where(User.is_active)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_minimal_for_session(self, user_id: UUID) -> User | None:
        """Get user with minimal fields for session authentication."""
        query = select(User).where(User.id == user_id).where(User.is_active)
        # No selectinload - minimal query for performance
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
```

### Service Layer Pattern

```python
# apps/api/src/domains/users/service.py

class UserService:
    """Service for user management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UserRepository(db)

    async def get_user_by_id(self, user_id: UUID) -> UserProfile:
        """Get user by ID."""
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise_user_not_found(user_id)
        return self._build_user_profile(user)

    async def update_user(self, user_id: UUID, data: UserUpdate) -> UserProfile:
        """Update user profile."""
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise_user_not_found(user_id)

        updated_user = await self.repository.update(
            user, data.model_dump(exclude_unset=True)
        )
        await self.db.commit()
        return self._build_user_profile(updated_user)
```

### Database Session Provider

```python
# apps/api/src/infrastructure/database/session.py

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(
    str(settings.database_url),
    echo=settings.log_level_sqlalchemy.upper() in ("DEBUG", "INFO"),
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session with automatic lifecycle."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("database_session_error", error=str(exc))
            raise
        finally:
            await session.close()

# For non-FastAPI code (background tasks)
@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Database session context manager for non-FastAPI code."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### Unit of Work Pattern

```python
# apps/api/src/core/unit_of_work.py

class UnitOfWork:
    """Manages transaction lifecycle with explicit commit/rollback."""

    def __init__(self, db: AsyncSession, is_nested: bool = False):
        self.db = db
        self._committed = False
        self._rolled_back = False
        self._is_nested = is_nested
        self._savepoint: AsyncSessionTransaction | None = None

    async def __aenter__(self) -> UnitOfWork:
        if self._is_nested:
            self._savepoint = await self.db.begin_nested()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
            return False
        if not self._committed and not self._rolled_back:
            await self.rollback()
        return None

    async def commit(self) -> None:
        if self._is_nested and self._savepoint:
            await self._savepoint.commit()
        else:
            await self.db.commit()
        self._committed = True

    async def rollback(self) -> None:
        if self._is_nested and self._savepoint:
            await self._savepoint.rollback()
        else:
            await self.db.rollback()
        self._rolled_back = True

    @asynccontextmanager
    async def nested(self) -> AsyncGenerator[UnitOfWork, None]:
        """Create nested transaction (savepoint)."""
        nested_uow = UnitOfWork(self.db, is_nested=True)
        async with nested_uow:
            yield nested_uow
```

### Transactional Decorator

```python
def transactional[T](func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator to mark a function as transactional."""
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        db = kwargs.get("db") or (args[0] if args else None)

        if not isinstance(db, AsyncSession):
            raise ValueError("@transactional requires 'db' to be AsyncSession")

        async with UnitOfWork(db) as uow:
            result = await func(*args, **kwargs)
            await uow.commit()
            return result

    return wrapper

# Usage
@transactional
async def create_user_with_connector(
    db: AsyncSession,
    user_data: dict,
    connector_data: dict,
) -> tuple[User, Connector]:
    """Auto-commits on success, auto-rollbacks on exception."""
    user = await user_service.create_user(db, user_data)
    connector = await connector_service.create_connector(db, user.id, connector_data)
    return user, connector
```

### Redis/Cache Injection

```python
# apps/api/src/infrastructure/cache/redis.py

# Module-level singleton instances
_redis_cache: aioredis.Redis | None = None
_redis_session: aioredis.Redis | None = None

async def get_redis_cache() -> aioredis.Redis:
    """Get Redis client for caching (lazy initialization)."""
    global _redis_cache

    if _redis_cache is None:
        redis_url = str(settings.redis_url)
        base_url = redis_url.rsplit("/", 1)[0]
        cache_url = f"{base_url}/{settings.redis_cache_db}"

        _redis_cache = aioredis.from_url(
            cache_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("redis_cache_connected", db=settings.redis_cache_db)

    return _redis_cache

async def get_redis_session() -> aioredis.Redis:
    """Get Redis client for session management."""
    global _redis_session

    if _redis_session is None:
        # Similar initialization...
        pass

    return _redis_session
```

### Thread-Safe Singleton Service

```python
# apps/api/src/domains/agents/api/router.py

_agent_service: AgentService | None = None
_agent_service_lock = threading.Lock()

def get_agent_service() -> AgentService:
    """Get or create agent service singleton (thread-safe)."""
    global _agent_service

    # First check (unlocked) - fast path
    if _agent_service is not None:
        return _agent_service

    # Second check (locked) - ensure only one thread initializes
    with _agent_service_lock:
        if _agent_service is None:
            _agent_service = AgentService()

    return _agent_service

@router.post("/agents/chat")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    service = get_agent_service()
    return await service.stream_chat(request)
```

### Summary of Patterns

| Pattern | Use Case | Example |
|---------|----------|---------|
| **FastAPI Depends()** | Route handler dependencies | `Depends(get_current_superuser_session)` |
| **Dependency Chain** | Progressive refinement | Session → User → Active → Verified |
| **Repository Pattern** | Type-safe CRUD | `BaseRepository[User]` |
| **Service Layer** | Business logic | `UserService(db)` |
| **Module Singletons** | Redis, LLM clients | `_redis_cache`, `_tool_context_store` |
| **Session Factory** | DB lifecycle | `get_db_session()` |
| **Unit of Work** | Transaction boundaries | `async with UnitOfWork(db)` |
| **Thread-safe Singleton** | Shared services | Double-check locking |

### Consequences

**Positive**:
- ✅ **Type Safety** : Validation statique des dépendances
- ✅ **Testability** : Mocking facilité via Depends()
- ✅ **Clean Architecture** : Séparation Router/Service/Repository
- ✅ **Transaction Management** : UoW avec commit/rollback automatique
- ✅ **Lazy Initialization** : Singletons initialisés à la demande

**Negative**:
- ⚠️ Verbosité des chaînes de dépendances
- ⚠️ Debugging des injections imbriquées

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Dependency chain pour authentification
- [x] ✅ BaseRepository générique avec soft-delete
- [x] ✅ Service layer avec injection de repository
- [x] ✅ Unit of Work avec nested transactions
- [x] ✅ Module-level singletons pour Redis
- [x] ✅ Thread-safe singleton pour AgentService

---

## References

### Source Code
- **Dependencies**: `apps/api/src/core/dependencies.py`
- **Session Dependencies**: `apps/api/src/core/session_dependencies.py`
- **Repository Base**: `apps/api/src/core/repository.py`
- **Unit of Work**: `apps/api/src/core/unit_of_work.py`
- **Database Session**: `apps/api/src/infrastructure/database/session.py`

---

**Fin de ADR-045** - Dependency Injection Pattern Decision Record.
