# Plan d'implémentation — F7. Browser Control (Playwright)

## Context

LIA est un assistant IA multi-agents. L'utilisateur souhaite offrir à l'assistant la capacité d'interagir avec le web (naviguer, cliquer, remplir des formulaires, extraire du contenu). Cela ouvre des cas d'usage comme : remplir un formulaire en ligne, extraire des données structurées d'un site, vérifier visuellement une page, etc.

**Architecture choisie : Connecteur complet** (même pattern que Wikipedia).
Le browser est un **connecteur à part entière** avec node dédié dans le graph, tool manifests, et activation utilisateur. Le pattern suivi est celui de `wikipedia_agent` :
- Infrastructure dans `src/infrastructure/browser/` (pool, session, sécurité, a11y)
- Tools dans `src/domains/agents/tools/browser_tools.py`
- Tool manifests dans `src/domains/agents/browser/catalogue_manifests.py`
- Agent builder dans `src/domains/agents/graphs/browser_agent_builder.py`
- Prompt dans `src/domains/agents/prompts/v1/browser_agent_prompt.txt`
- **Node dédié dans le graph** (`graph.add_node(AGENT_BROWSER, ...)`) — conditionnel sur `browser_enabled`
- Enregistrement dans le registry (main.py) + graph wiring
- Domain config dans `domain_taxonomy.py`
- Agent manifest dans `catalogue_loader.py`
- Intention-to-agent mapping dans `orchestrator.py`
- L'utilisateur peut activer/désactiver le browser comme n'importe quel autre connecteur

**Contrainte prod** : RPi5 16GB RAM — max 1 session browser simultanée par défaut (configurable), gestion mémoire stricte. Coordination globale cross-workers via Redis.

**Décisions architecturales validées :**
1. **Sessions keyées par `user_id`** — 1 session browser max par user. Coordination globale cross-workers via comptage Redis (4 workers uvicorn en prod, mémoire non partagée). Voir ADR-056.
2. **CDP direct pour l'arbre a11y** — `await page.context.new_cdp_session(page)` + `await cdp.send("Accessibility.getFullAXTree")`. API standard Chrome DevTools Protocol, stable et non-deprecated (contrairement à `page.accessibility.snapshot()` deprecated depuis Playwright 1.41).
3. **HITL au niveau plan (V1)** — Confirmation utilisateur via l'`approval_gate` existant (plan-level HITL). Le planner génère un plan décrivant les actions browser (navigation, remplissage, soumission) et l'utilisateur approuve le plan avant exécution. Pas de HITL action-par-action en V1 — le browser agent exécute le plan approuvé en autonomie. **Raison** : le mécanisme `pending_tool_confirmation` fonctionne au niveau du parallel_executor (post-exécution du subgraph agent), pas au milieu du ReAct loop. Implémenter un HITL mid-loop nécessiterait un middleware HITL custom pour le browser, ce qui est de la sur-ingénierie pour V1. Le plan-level HITL est suffisant et cohérent avec l'architecture existante. V2 pourra ajouter un middleware HITL browser pour les actions sensibles si le besoin est avéré.
4. **LLM par défaut : gpt-4.1-mini** — Temperature 0.2, config ajoutée dans `LLM_DEFAULTS` **et** `LLM_TYPES_REGISTRY` de `llm_config/constants.py`. Choix de `gpt-4.1-mini` plutôt que `gpt-5-nano` (utilisé par web_fetch) car les arbres a11y sont plus complexes que du texte web extrait et requièrent un raisonnement multi-step pour la sélection d'éléments.
5. **Recovery transparent cross-workers** — Sessions Playwright process-local (non sérialisables). Métadonnées minimales (URL, title) dans Redis avec TTL = session timeout. Si un follow-up atterrit sur un autre worker, l'agent re-navigue transparentement vers l'URL stockée. Zéro impact checkpoint LangGraph.
6. **`--no-sandbox`** — Nécessaire dans Docker (pas de user namespace disponible dans le container). L'isolation est assurée par le container Docker lui-même. Décision documentée dans ADR-056.

---

## Phase A — Configuration & Constantes

### A1. `src/core/config/browser.py` (NEW)

Créer `BrowserSettings(BaseSettings)` suivant le pattern de `channels.py` / `mcp.py` :

```python
class BrowserSettings(BaseSettings):
    """Browser automation settings for Playwright-based web interaction."""

    browser_enabled: bool = Field(
        default=False,
        description="Enable headless browser automation (Playwright/Chromium).",
    )
    browser_max_concurrent_sessions: int = Field(
        default=1, ge=1, le=10,
        description="Maximum concurrent browser sessions globally (coordinated via Redis).",
    )
    browser_session_timeout_seconds: int = Field(
        default=300, ge=30, le=1800,
        description="Idle timeout before a browser session is automatically closed.",
    )
    browser_page_load_timeout_seconds: int = Field(
        default=30, ge=5, le=120,
        description="Maximum wait time for page load completion.",
    )
    browser_action_timeout_seconds: int = Field(
        default=10, ge=3, le=60,
        description="Maximum wait time for individual browser actions (click, fill).",
    )
    browser_max_pages_per_session: int = Field(
        default=5, ge=1, le=20,
        description="Maximum pages per browser session.",
    )
    browser_max_navigations_per_session: int = Field(
        default=30, ge=5, le=100,
        description="Maximum navigations per session before forced close.",
    )
    browser_screenshot_enabled: bool = Field(
        default=False,
        description="Enable screenshot tool (off by default, high token cost).",
    )
    browser_accessibility_max_depth: int = Field(
        default=8, ge=3, le=15,
        description="Maximum depth for accessibility tree extraction.",
    )
    browser_ax_tree_max_tokens: int = Field(
        default=5000, ge=500, le=50000,
        description="Maximum tokens for accessibility tree output. Hard-truncated if exceeded.",
    )
    browser_memory_limit_mb: int = Field(
        default=512, ge=128, le=2048,
        description="Memory limit per browser instance (MB). Navigation refused if exceeded.",
    )
    browser_blocked_domains: str = Field(
        default="",
        description="Additional blocked domains (CSV). Combined with SSRF protection.",
    )
    browser_user_agent: str = Field(
        default="Mozilla/5.0 (compatible; LIA-Bot/1.0)",
        description="User-Agent string for browser requests.",
    )
    # Rate limiting (configurable per environment)
    browser_rate_limit_read_calls: int = Field(
        default=20, ge=5, le=100,
        description="Max read tool calls (navigate, snapshot) per window.",
    )
    browser_rate_limit_read_window: int = Field(
        default=60, ge=10, le=300,
        description="Rate limit window (seconds) for read tools.",
    )
    browser_rate_limit_write_calls: int = Field(
        default=20, ge=5, le=100,
        description="Max write tool calls (click, fill, press_key) per window.",
    )
    browser_rate_limit_write_window: int = Field(
        default=60, ge=10, le=300,
        description="Rate limit window (seconds) for write tools.",
    )
    browser_rate_limit_expensive_calls: int = Field(
        default=2, ge=1, le=10,
        description="Max expensive tool calls (screenshot) per window.",
    )
    browser_rate_limit_expensive_window: int = Field(
        default=300, ge=60, le=1800,
        description="Rate limit window (seconds) for expensive tools.",
    )
```

### A2. `src/core/config/__init__.py` (MODIFY)

Ajouter `BrowserSettings` au MRO de `Settings` (avant `BaseSettings`).

### A3. `src/core/constants.py` (MODIFY)

Ajouter les constantes browser (non paramétrables uniquement) :
```python
# Browser Control (F7)
SCHEDULER_JOB_BROWSER_CLEANUP = "browser_session_cleanup"
BROWSER_DEFAULT_TIMEOUT_MS = 30_000
REDIS_KEY_BROWSER_SESSION_PREFIX = "browser:session:"
BROWSER_INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "listbox", "menuitem", "tab", "switch", "searchbox", "slider",
    "spinbutton", "option", "menuitemcheckbox", "menuitemradio",
})
BROWSER_CONTENT_ROLES = frozenset({
    "heading", "paragraph", "listitem", "cell", "img", "figure",
})
BROWSER_BLOCKED_SCHEMES = frozenset({"file", "javascript", "data", "chrome", "about", "blob"})
```

Note : les valeurs paramétrables (rate limits, token budget, timeouts) sont dans `BrowserSettings` (Phase A1).

**Fichiers de référence** : [constants.py](apps/api/src/core/constants.py), [config/__init__.py](apps/api/src/core/config/__init__.py)

---

## Phase B — Infrastructure Browser

### B1. `src/infrastructure/browser/__init__.py` (NEW)

Exports : `get_browser_pool`, `close_browser_pool`, `BrowserSession`, `PageSnapshot`.

### B2. `src/infrastructure/browser/models.py` (NEW)

Modèles Pydantic pour les données browser :

```python
class PageSnapshot(BaseModel):
    """Snapshot of a browser page with accessibility tree."""

    url: str = Field(..., description="Current page URL.")
    title: str = Field(..., description="Page title.")
    accessibility_tree: str = Field(..., description="Formatted AX tree with [EN] refs.")
    interactive_count: int = Field(..., description="Number of interactive elements.")
    total_count: int = Field(..., description="Total AX tree nodes.")

class BrowserAction(BaseModel):
    """Represents a single browser action."""

    action_type: Literal["navigate", "click", "fill", "press_key", "screenshot", "snapshot"] = Field(
        ..., description="Type of browser action.",
    )
    ref: str | None = Field(default=None, description="Element reference (e.g., 'E3').")
    value: str | None = Field(default=None, description="Value for fill actions.")
    key: str | None = Field(default=None, description="Key name for press_key actions.")

class BrowserSessionInfo(BaseModel):
    """Metadata for a browser session (stored in Redis for cross-worker recovery)."""

    session_id: str = Field(..., description="Unique session identifier.")
    user_id: str = Field(..., description="User who owns this session.")
    created_at: datetime = Field(..., description="Session creation timestamp.")
    current_url: str | None = Field(default=None, description="Last navigated URL.")
    page_title: str | None = Field(default=None, description="Last page title.")
    worker_pid: int = Field(..., description="PID of the worker process owning this session.")
    navigation_count: int = Field(default=0, description="Number of navigations in this session.")
```

### B3. `src/infrastructure/browser/security.py` (NEW)

Politique de sécurité browser, **réutilisant** `validate_url()` de `src/domains/agents/web_fetch/url_validator.py` :

- `BrowserSecurityPolicy` :
  - `validate_navigation_url(url) → tuple[bool, str]` : appelle `validate_url()` existant + vérifie schemes bloqués (`BROWSER_BLOCKED_SCHEMES`) + domaines bloqués additionnels (settings)
  - `create_request_interceptor(page)` : enregistre `page.route("**/*", handler)` pour bloquer les requêtes vers IPs privées, schemes dangereux, téléchargements. Note : le handler ne doit pas bloquer la requête de navigation initiale elle-même.
  - `validate_key(key) → bool` : whitelist de touches autorisées (Enter, Tab, Escape, ArrowUp/Down/Left/Right, Backspace, Delete, Space, Home, End, PageUp, PageDown)
  - `sanitize_fill_value(value) → str` : empêche l'injection via fill (max length, strip control chars)

**Réutilisation directe** : `validate_url()`, `check_ip_safety()` de [url_validator.py](apps/api/src/domains/agents/web_fetch/url_validator.py)

### B4. `src/infrastructure/browser/accessibility.py` (NEW)

Extraction et formatage de l'arbre d'accessibilité :

- `AccessibilityTreeExtractor` :
  - `extract(page) → list[AXNode]` : utilise **CDP direct** via `cdp = await page.context.new_cdp_session(page)` puis `await cdp.send("Accessibility.getFullAXTree")`. API standard Chrome DevTools Protocol, stable et non-deprecated. Retourne un arbre JSON complet avec roles, names, values, states. Appels CDP wrappés dans `get_circuit_breaker("browser_cdp")` de [circuit_breaker.py](apps/api/src/infrastructure/resilience/circuit_breaker.py).
  - `assign_refs(nodes) → list[AXNode]` : assigne `[E1]`, `[E2]`... aux éléments interactifs (`BROWSER_INTERACTIVE_ROLES`) et contenus nommés (`BROWSER_CONTENT_ROLES`)
  - `compact_tree(nodes, max_depth) → list[AXNode]` : supprime branches structurelles sans ref (~60% réduction tokens)
  - `format_for_llm(nodes) → str` : texte indenté lisible par le LLM. **Hard truncation** : si le résultat dépasse `settings.browser_ax_tree_max_tokens`, tronquer les branches les plus profondes en priorité et ajouter `[... N additional elements truncated]`. Format :
    ```
    [E1] link "Sign In"
    [E2] textbox "Email" required
    [E3] textbox "Password" required
    [E4] button "Log In"
    heading "Welcome" level=1
      paragraph "Please sign in to continue."
    ```
  - `find_element_by_ref(page, ref) → Locator | None` : résout `[E3]` vers un Playwright `Locator`. Re-extrait l'arbre CDP (snapshot frais pour éviter les stale refs), retrouve le `backendDOMNodeId` du node matchant, puis utilise `cdp.send("DOM.resolveNode", {"backendNodeId": ...})` pour obtenir un `objectId` et enfin `page.locator()` avec le sélecteur CSS correspondant ou `page.get_by_role()` selon le contexte.

**Imports Playwright lazy** : tous les `import playwright` sont à l'intérieur des méthodes, jamais au top level du module — évite `ModuleNotFoundError` si Playwright non installé avec `browser_enabled=False`.

### B5. `src/infrastructure/browser/pool.py` (NEW)

Singleton pool suivant le pattern `get_redis_cache()` de [redis.py](apps/api/src/infrastructure/cache/redis.py) :

```python
_browser_pool: BrowserPool | None = None

async def get_browser_pool() -> BrowserPool | None:
    """Return the browser pool singleton, or None if browser is disabled.

    Returns:
        BrowserPool instance if browser_enabled=True and healthy, None otherwise.
    """
    global _browser_pool
    if not settings.browser_enabled:
        return None
    if _browser_pool is None:
        _browser_pool = BrowserPool()
        await _browser_pool.initialize()
    return _browser_pool

async def close_browser_pool() -> None:
    """Shut down the browser pool and release all resources."""
    global _browser_pool
    if _browser_pool:
        await _browser_pool.close()
        _browser_pool = None
```

`BrowserPool` :
- `_playwright: Playwright` — instance Playwright (import lazy dans `initialize()`)
- `_browser: Browser` — instance Chromium unique avec args : `--disable-gpu`, `--disable-dev-shm-usage`, `--no-sandbox`, `--disable-extensions`. Note : `--no-sandbox` est nécessaire dans Docker ; l'isolation est assurée par le container (voir ADR-056).
- `_sessions: dict[str, BrowserSession]` — sessions process-local par user_id
- `_lock: asyncio.Lock()` — pour création/suppression thread-safe
- `initialize()` : import lazy de `playwright.async_api`, lance Playwright + Chromium. **Health check** : si binaire absent, log WARNING et set `_healthy = False` (ne crash pas)
- `acquire_session(user_id) → BrowserSession` : **coordination globale via Redis** — avant création, compter les clés `REDIS_KEY_BROWSER_SESSION_PREFIX + *` dans Redis. Si count >= `settings.browser_max_concurrent_sessions`, raise `ValidationError("Maximum concurrent browser sessions reached")`. Si une session locale existe pour ce user, la réutiliser. Sinon, vérifier Redis pour une session existante sur un autre worker (recovery path, voir C1 dans la revue).
- `release_session(user_id)` : ferme le BrowserContext, supprime la clé Redis correspondante
- `cleanup_expired()` : ferme sessions idle > timeout + supprime les clés Redis correspondantes. Appelé par job APScheduler (`AsyncIOScheduler`) toutes les 60s.
- `get_memory_usage_mb() → float | None` : tente la lecture de `/proc/{pid}/status` (Linux, prod RPi5). Si indisponible (Windows, macOS), retourne `None`. Pas de dépendance `psutil`. Le monitoring mémoire est informatif, pas bloquant. Si la valeur est disponible et > 80% de `settings.browser_memory_limit_mb`, la navigation est refusée.
- `close()` : ferme tout (sessions, browser, playwright) + supprime les clés Redis

**Recovery cross-workers** (décision #5) :
- Après chaque navigation réussie, stocker dans Redis :
  ```
  REDIS_KEY_BROWSER_SESSION_PREFIX + user_id → BrowserSessionInfo.model_dump() (JSON)
  TTL = settings.browser_session_timeout_seconds
  ```
- Lors de `acquire_session()`, si pas de session locale mais Redis a une entrée pour ce user :
  - Créer une nouvelle session locale
  - Auto-naviguer vers l'URL stockée dans Redis
  - Retourner un snapshot frais (recovery transparent)

**Fichiers de référence** : [redis.py](apps/api/src/infrastructure/cache/redis.py) pour le singleton pattern, [circuit_breaker.py](apps/api/src/infrastructure/resilience/circuit_breaker.py) pour le pattern async

### B6. `src/infrastructure/browser/session.py` (NEW)

`BrowserSession` — wrapper autour d'un `BrowserContext` Playwright :

```python
class BrowserSession:
    """Manages a single user's browser session within a BrowserContext.

    Each session wraps a Playwright BrowserContext and provides high-level
    browser interaction methods (navigate, click, fill) with security checks,
    accessibility tree extraction, and content wrapping.

    Args:
        user_id: The user who owns this session.
        context: The Playwright BrowserContext for this session.
        security: Security policy for URL validation and input sanitization.
    """

    def __init__(self, user_id: str, context: BrowserContext, security: BrowserSecurityPolicy):
        self.user_id = user_id
        self.context = context
        self.page: Page | None = None
        self.created_at = time.monotonic()
        self.last_activity = time.monotonic()
        self.navigation_count = 0
        self._extractor = AccessibilityTreeExtractor()
        self._security = security

    async def navigate(self, url: str) -> PageSnapshot:
        """Navigate to URL with SSRF check and request interception.

        Args:
            url: The URL to navigate to.

        Returns:
            PageSnapshot with accessibility tree of the loaded page.

        Raises:
            ValueError: If URL fails SSRF validation.
            TimeoutError: If page load exceeds timeout.
        """

    async def get_snapshot(self) -> PageSnapshot:
        """Get current page accessibility tree (observe page state before acting)."""

    async def click(self, ref: str) -> PageSnapshot:
        """Click an interactive element by its [EN] reference and return post-action snapshot."""

    async def fill(self, ref: str, value: str) -> PageSnapshot:
        """Fill a form field by its [EN] reference with a sanitized value."""

    async def press_key(self, key: str) -> PageSnapshot:
        """Press a validated keyboard key and return post-action snapshot."""

    async def screenshot(self) -> bytes:
        """Take a JPEG screenshot of the current page (max 1280px wide).

        Uses page.screenshot(type="jpeg", quality=80) for token-efficient output.
        """

    async def close(self) -> None:
        """Close the page and browser context, releasing all resources."""
```

Chaque action met à jour `last_activity` et vérifie les limites (max_pages, max_navigations).

**Gestion des nouvelles tabs** : intercepter `context.on("page", handler)` pour gérer les popups. Si un clic ouvre un nouvel onglet, le session reste focalisée sur la page active. Les tabs supplémentaires sont fermées automatiquement.

---

## Phase C — Tools Browser

### C1. `src/domains/agents/tools/browser_tools.py` (NEW)

6 tools suivant le pattern exact de [web_fetch_tools.py](apps/api/src/domains/agents/tools/web_fetch_tools.py) — même stacking de decorators `@tool` + `@track_tool_metrics` + `@rate_limit`, même return type `UnifiedToolOutput`, même pattern `validate_runtime_config()` en première ligne.

```python
# Note : les browser tools n'utilisent PAS @connector_tool (pas de context domain, pas d'OAuth).
# Ils suivent le pattern de web_fetch_tools.py : raw decorator stacking.
# Note : le pattern conditionnel d'import suit sub_agent_tools (try/except + settings check),
# pas Wikipedia (qui est inconditionnel), car le browser est feature-flaggé.

@tool
@track_tool_metrics(
    tool_name="browser_navigate",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_read_calls,
    window_seconds=lambda: settings.browser_rate_limit_read_window,
    scope="user",
)
async def browser_navigate_tool(
    url: Annotated[str, "The URL to navigate to"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """Navigate to a web page and return its accessibility tree structure."""
    # 1. validate_runtime_config(runtime, "browser_navigate")
    # 2. Get browser pool (None → failure)
    # 3. Acquire session for user (Redis coordination for global max)
    # 4. SSRF validation via BrowserSecurityPolicy.validate_navigation_url()
    # 5. Navigate + wait for load (circuit breaker)
    # 6. Extract AX tree via AccessibilityTreeExtractor (CDP, circuit breaker)
    # 7. Wrap content via wrap_external_content(content, url, source_type="browser_page")
    # 8. Update Redis session metadata
    # 9. Return UnifiedToolOutput.data_success() with registry_updates
    # Each failure path: logger.error("browser_navigate_error", ...) THEN UnifiedToolOutput.failure()

@tool
@track_tool_metrics(
    tool_name="browser_snapshot",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_read_calls,
    window_seconds=lambda: settings.browser_rate_limit_read_window,
    scope="user",
)
async def browser_snapshot_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """Get current page accessibility tree (observe page state before acting)."""

@tool
@track_tool_metrics(
    tool_name="browser_click",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_write_calls,
    window_seconds=lambda: settings.browser_rate_limit_write_window,
    scope="user",
)
async def browser_click_tool(
    ref: Annotated[str, "Element reference from accessibility tree (e.g., 'E3')"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """Click an interactive element by its reference from the accessibility tree."""

@tool
@track_tool_metrics(
    tool_name="browser_fill",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_write_calls,
    window_seconds=lambda: settings.browser_rate_limit_write_window,
    scope="user",
)
async def browser_fill_tool(
    ref: Annotated[str, "Element reference for the form field (e.g., 'E2')"],
    value: Annotated[str, "The value to fill into the form field"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """Fill a form field by its reference with the given value."""

@tool
@track_tool_metrics(
    tool_name="browser_press_key",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_write_calls,
    window_seconds=lambda: settings.browser_rate_limit_write_window,
    scope="user",
)
async def browser_press_key_tool(
    key: Annotated[str, "Keyboard key to press (e.g., 'Enter', 'Tab', 'Escape')"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """Press a keyboard key (Enter, Tab, Escape, Arrow keys, etc.)."""

@tool
@track_tool_metrics(
    tool_name="browser_screenshot",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_expensive_calls,
    window_seconds=lambda: settings.browser_rate_limit_expensive_window,
    scope="user",
)
async def browser_screenshot_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """Take a screenshot of the current page (requires browser_screenshot_enabled)."""
    # Feature-flaggé : retourne failure si settings.browser_screenshot_enabled=False
```

**Pattern de gestion d'erreur** : chaque tool (1) log via `logger.error("browser_<action>_error", ...)` avec metadata structlog, puis (2) retourne `UnifiedToolOutput.failure()`. Pattern identique à `web_fetch_tools.py` :

| Exception Playwright | `error_code` | Message |
|---|---|---|
| Pool `None` (disabled) | `CONFIGURATION_ERROR` | "Browser not enabled" |
| Global max sessions reached (Redis count) | `RATE_LIMIT_EXCEEDED` | "Max concurrent sessions reached" |
| SSRF blocked | `INVALID_INPUT` | "URL blocked: {reason}" |
| `TimeoutError` (page load) | `TIMEOUT` | "Page load timeout after {N}s" |
| `Error` (navigation failed) | `EXTERNAL_API_ERROR` | "Navigation failed: {details}" |
| Element ref not found | `NOT_FOUND` | "Element [E{N}] not found on page" |
| Invalid key | `INVALID_INPUT` | "Key '{key}' not allowed" |
| Max navigations exceeded | `RATE_LIMIT_EXCEEDED` | "Max navigations per session reached" |
| Screenshot disabled | `CONFIGURATION_ERROR` | "Screenshot feature is disabled" |
| Session expired | `DEPENDENCY_ERROR` | "Browser session expired, navigate again" |
| Recovery navigation failed | `EXTERNAL_API_ERROR` | "Could not reconnect to previous page: {details}" |
| Memory limit exceeded | `RATE_LIMIT_EXCEEDED` | "Browser memory limit exceeded, try again later" |

**Content wrapping** : tout contenu extrait de page est wrappé via `wrap_external_content(content, url, source_type="browser_page")` de [content_wrapper.py](apps/api/src/domains/agents/utils/content_wrapper.py) avant injection dans le contexte LLM.

### C2. `src/domains/agents/tools/__init__.py` (MODIFY)

Ajout conditionnel (pattern identique aux `sub_agent_tools` existants — PAS le pattern Wikipedia qui est inconditionnel, car le browser est feature-flaggé) :

```python
# Browser tools (F7 - feature-flagged)
try:
    from src.core.config import settings as _settings
    if getattr(_settings, "browser_enabled", False):
        from src.domains.agents.tools.browser_tools import (
            browser_navigate_tool,
            browser_snapshot_tool,
            browser_click_tool,
            browser_fill_tool,
            browser_press_key_tool,
            browser_screenshot_tool,
        )
        # Add to __all__
except Exception:
    pass
```

---

## Phase D — Agent Builder & Catalogue

### D0. `src/domains/agents/browser/catalogue_manifests.py` (NEW)

Tool manifests pour le catalogue du planner (pattern [wikipedia/catalogue_manifests.py](apps/api/src/domains/agents/wikipedia/catalogue_manifests.py)) :

6 `ToolManifest` entries avec les champs requis :
- `name`, `agent`, `description` (user-facing)
- `semantic_keywords` en anglais : "browse website", "navigate page", "click button", "fill form", "interact with web page", "screenshot page". **Exhaustifs** pour assurer le routing correct.
- `parameters` (list[ParameterSchema]) et `outputs` (list[OutputFieldSchema])
- `cost` : `CostProfile(est_tokens_in=200, est_tokens_out=2000, est_cost_usd=0.005, est_latency_ms=3000)` — browser est expensive (page load + AX tree extraction)
- `permissions` : `PermissionProfile(required_scopes=[], hitl_required=False, data_classification="PUBLIC")`
- `context_key="browsers"` (match `result_key` de DomainConfig)
- `display` : `DisplayMetadata(emoji="🌐", i18n_key="browser_navigate", visible=True, category="tool")`
- `version="1.0.0"`, `maintainer="Team AI"`
- **RESTRICTIVE** : ne déclencher que sur des demandes explicites d'interaction web (pas pour de la simple lecture de page → c'est web_fetch)

### D0b. `src/domains/agents/browser/__init__.py` (NEW)

Minimal — exports des manifests.

### D1. `src/domains/agents/graphs/browser_agent_builder.py` (NEW)

Pattern [wikipedia_agent_builder.py](apps/api/src/domains/agents/graphs/wikipedia_agent_builder.py) :

```python
def build_browser_agent() -> Any:
    """Build the browser agent using the generic agent template.

    Returns:
        Compiled LangGraph agent for browser interaction.
    """
    logger.info("building_browser_agent_with_generic_template")

    tools = [
        browser_navigate_tool,
        browser_snapshot_tool,
        browser_click_tool,
        browser_fill_tool,
        browser_press_key_tool,
    ]
    if settings.browser_screenshot_enabled:
        tools.append(browser_screenshot_tool)

    system_prompt_template = load_prompt("browser_agent_prompt", version="v1")
    system_prompt = system_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",
    )

    config = create_agent_config_from_settings(
        agent_name="browser_agent",
        tools=tools,
        system_prompt=system_prompt,
        datetime_generator=get_prompt_datetime_formatted,
    )
    return build_generic_agent(config)
```

### D2. `src/domains/agents/prompts/v1/browser_agent_prompt.txt` (NEW)

Prompt système du browser agent, suivant la structure standard des 52 prompts existants :

```
<Role>
You are the Browser specialist agent.
Always respond in the user's language as indicated in <Context>.
You interact with web pages using accessibility tree references [EN].
</Role>

<StrictLogic>
### 1. Always snapshot before acting
### 2. Navigation-first: navigate before interacting
### 3. Form workflow: snapshot → identify fields → fill → snapshot → verify → submit
### 4. Security: never enter credentials not provided by the user
### 5. Recovery: if element not found, re-snapshot and retry
### 6. Read-only for sensitive data: extract but never submit without explicit user intent
### 7. Cookie consent: if a consent banner blocks interaction, click accept/dismiss to proceed
</StrictLogic>

<Strategies>
Input: "Go to example.com"
Action: browser_navigate_tool(url="https://example.com")

Input: "Click the login button"
Action: browser_snapshot_tool() → find button ref → browser_click_tool(ref="E4")

Input: "Fill the contact form with name=John"
Action: browser_snapshot_tool() → find field → browser_fill_tool(ref="E2", value="John")
</Strategies>

<Context>
{context_instructions}

Date: {current_datetime}
</Context>
```

### D2b. Data Registry Integration (dans `browser_tools.py`)

**`src/domains/agents/data_registry/models.py` (MODIFY)** — Ajouter :
```python
BROWSER_PAGE = "BROWSER_PAGE"  # Browser page snapshot
```
à `RegistryItemType` enum (pattern `WIKIPEDIA_ARTICLE`, `WEB_PAGE`).

**Dans `browser_tools.py`** — Enregistrer le context type (pattern [wikipedia_tools.py:65-75](apps/api/src/domains/agents/tools/wikipedia_tools.py#L65-L75)) :
```python
class BrowserPageItem(BaseModel):
    """Schema for browser page data in context registry."""

    url: str = Field(..., description="Page URL.")
    title: str = Field(..., description="Page title.")
    interactive_count: int = Field(default=0, description="Number of interactive elements.")
    content_summary: str = Field(default="", description="Brief content summary.")

ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_BROWSERS,  # "browsers"
        agent_name=AGENT_BROWSER,
        item_schema=BrowserPageItem,
        primary_id_field="url",
        display_name_field="title",
        reference_fields=["title", "url"],
        icon="🌐",
    )
)
```
Cela permet les références contextuelles : "la page précédente", "le 2ème site".

### D2c. `src/domains/agents/graphs/base_agent_builder.py` (MODIFY)

Ajouter `"browser_agent": "browser_agent"` dans le `llm_type_map` (ligne ~244). Sans cela, le browser agent se verrait attribuer le fallback `"contact_agent"` comme LLMType.

### D3. `src/domains/agents/constants.py` (MODIFY)

Ajouter :
```python
# Browser agent (F7)
NODE_BROWSER_AGENT = "browser_agent"
AGENT_BROWSER = "browser_agent"
INTENTION_BROWSER = "browser"
INTENTION_BROWSER_NAVIGATE = "browser_navigate"
INTENTION_BROWSER_INTERACT = "browser_interact"
CONTEXT_DOMAIN_BROWSERS = "browsers"  # domain + "s" pattern (cf. CONTEXT_DOMAIN_CONTACTS)
```

Ajouter `AGENT_BROWSER` à `ALL_AGENTS`.
Ajouter les exports à `__all__`.

### D4. `src/infrastructure/llm/factory.py` (MODIFY)

Ajouter `"browser_agent"` au `LLMType` Literal (ligne ~67).

### D4b. `src/domains/llm_config/constants.py` (MODIFY)

Ajouter dans **`LLM_DEFAULTS`** :
```python
"browser_agent": LLMAgentConfig(
    provider="openai",
    model="gpt-4.1-mini",
    temperature=0.2,  # Precision for element selection
    max_tokens=8000,
    top_p=0.9,
),
```

**ET** dans **`LLM_TYPES_REGISTRY`** (obligatoire — un `assert` vérifie l'égalité des clés) :
```python
"browser_agent": LLMTypeMetadata(
    llm_type="browser_agent",
    display_name="Browser Agent",
    category=CATEGORY_DOMAIN_AGENTS,
    description_key="settings.admin.llmConfig.types.browser_agent",
    required_capabilities=["tools"],
),
```

### D5. `src/domains/agents/registry/domain_taxonomy.py` (MODIFY)

Ajouter l'entrée browser au `DOMAIN_REGISTRY` :

```python
"browser": DomainConfig(
    name="browser",
    display_name="Browser",
    description=(
        "Interactive web browsing: navigate pages, click elements, fill forms, "
        "extract structured content. Use for tasks requiring direct web interaction "
        "beyond simple page fetching."
    ),
    agent_names=["browser_agent"],
    result_key="browsers",
    related_domains=["web_fetch", "web_search"],
    priority=5,
    is_routable=True,
    metadata={
        "provider": "internal",
        "requires_oauth": False,
        "requires_api_key": False,
        "feature_flag": "browser_enabled",
    },
),
```

### D6. `src/domains/agents/registry/catalogue_loader.py` (MODIFY)

Ajouter le manifest browser agent (suivant le pattern des autres agents) :

```python
BROWSER_AGENT_MANIFEST = AgentManifest(
    name="browser_agent",
    description="Agent for interactive web browsing: navigate, click, fill forms, extract content",
    tools=[
        "browser_navigate_tool",
        "browser_snapshot_tool",
        "browser_click_tool",
        "browser_fill_tool",
        "browser_press_key_tool",
        "browser_screenshot_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=BROWSER_DEFAULT_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
```

Enregistrer dans `initialize_catalogue()` de manière conditionnelle (`browser_enabled`).

### D7. `src/domains/agents/orchestration/orchestrator.py` (MODIFY)

Ajouter les mappings browser dans le dict `intention_to_agents` :

```python
INTENTION_BROWSER: [AGENT_BROWSER],
INTENTION_BROWSER_NAVIGATE: [AGENT_BROWSER],
INTENTION_BROWSER_INTERACT: [AGENT_BROWSER],
```

Sans cela, le planner ne peut pas dispatcher de tâches vers le browser agent.

---

## Phase E — Lifecycle & Wiring

### E1. `src/main.py` (MODIFY)

**Startup** (dans `lifespan()`, après l'agent registry, pattern identique à Wikipedia) :
```python
# Browser (F7) - conditional initialization
if getattr(settings, "browser_enabled", False):
    from src.infrastructure.browser.pool import get_browser_pool
    browser_pool = await get_browser_pool()
    if browser_pool and browser_pool.is_healthy:
        from src.domains.agents.graphs.browser_agent_builder import build_browser_agent
        registry.register_agent("browser_agent", build_browser_agent)
        # APScheduler (AsyncIOScheduler): cleanup sessions expirées toutes les 60s
        scheduler.add_job(
            browser_pool.cleanup_expired,
            "interval", seconds=60,
            id=SCHEDULER_JOB_BROWSER_CLEANUP,
            replace_existing=True,
        )
        logger.info("browser_agent_initialized")
    else:
        logger.warning("browser_agent_disabled_chromium_not_available")
```

**Shutdown** :
```python
if getattr(settings, "browser_enabled", False):
    from src.infrastructure.browser.pool import close_browser_pool
    await close_browser_pool()
```

### E1b. `src/domains/agents/graph.py` (MODIFY)

Ajouter le **node browser dans le graph** (conditionnel sur `browser_enabled`), pattern Wikipedia :

```python
# Browser agent (F7 - feature-flagged)
_browser_registered = False
if getattr(settings, "browser_enabled", False):
    try:
        browser_agent_runnable = registry_for_wrapper.get_agent("browser_agent")
        browser_agent_node = build_agent_wrapper(
            agent_runnable=browser_agent_runnable,
            agent_name="browser_agent",
            agent_constant=AGENT_BROWSER,
        )
        graph.add_node(AGENT_BROWSER, browser_agent_node)
        _browser_registered = True
    except Exception:
        logger.warning("browser_agent_node_not_registered")
```

Ajouter `AGENT_BROWSER` au dict existant de `add_conditional_edges` (une seule ligne, pas de refactoring dynamique) :
```python
# Dans le dict existant des orchestrator routes, ajouter :
AGENT_BROWSER: AGENT_BROWSER,  # Browser agent (F7 - conditionnel)
```

Edge vers response (conditionnel) :
```python
if _browser_registered:
    graph.add_edge(AGENT_BROWSER, NODE_RESPONSE)
```

### E2. `src/api/v1/routes.py` — Pas de modification nécessaire

Le browser agent est un tool interne, pas une API REST exposée. L'interaction passe par le chat SSE existant.

### E3. `apps/api/requirements.txt` (MODIFY)

Ajouter : `playwright==1.51.0`

### E4. `apps/api/Dockerfile.dev` (MODIFY)

Ajouter après l'installation des dépendances :
```dockerfile
RUN playwright install --with-deps chromium
```

### E5. `.env.example` (MODIFY — racine projet)

Ajouter une section browser :
```env
# ============================================================================
# BROWSER CONTROL & AUTOMATION
# ============================================================================
# Enable headless browser automation (Playwright/Chromium)
# WARNING: Requires Playwright + Chromium installed. See docs/technical/BROWSER_CONTROL.md
BROWSER_ENABLED=false
BROWSER_MAX_CONCURRENT_SESSIONS=1
BROWSER_SESSION_TIMEOUT_SECONDS=300
BROWSER_PAGE_LOAD_TIMEOUT_SECONDS=30
BROWSER_ACTION_TIMEOUT_SECONDS=10
BROWSER_MAX_NAVIGATIONS_PER_SESSION=30
BROWSER_SCREENSHOT_ENABLED=false
BROWSER_AX_TREE_MAX_TOKENS=5000
BROWSER_MEMORY_LIMIT_MB=512
BROWSER_RATE_LIMIT_READ_CALLS=20
BROWSER_RATE_LIMIT_WRITE_CALLS=20
```

---

## Phase F — Métriques & Observabilité

### F1. `src/infrastructure/observability/metrics_browser.py` (NEW)

Métriques Prometheus dédiées :
```python
browser_sessions_active = Gauge("browser_sessions_active", "Active browser sessions")
browser_actions_total = Counter("browser_actions_total", "Browser actions", ["action_type", "status"])
browser_navigation_duration_seconds = Histogram("browser_navigation_duration_seconds", "Navigation duration")
browser_snapshot_tokens = Histogram("browser_snapshot_tokens", "AX tree size in estimated tokens")
browser_errors_total = Counter("browser_errors_total", "Browser errors", ["error_type"])
browser_memory_bytes = Gauge("browser_memory_bytes", "Browser process memory usage")
```

---

## Phase G — i18n

### G1. `apps/web/locales/{lang}/translation.json` (MODIFY × 6)

Ajouter clés **frontend UI uniquement** pour les 6 langues (en, fr, de, es, it, zh). Les erreurs tools ne sont PAS i18n-isées — elles sont en anglais, consommées par le LLM, et le response node synthétise la réponse finale dans la langue de l'utilisateur.

```json
"browser": {
    "navigate": "Navigate to page",
    "snapshot": "Read page content",
    "click": "Click element",
    "fill": "Fill form field",
    "press_key": "Press key",
    "screenshot": "Take screenshot"
}
```

Ces clés correspondent aux `DisplayMetadata.i18n_key` des catalogue manifests (Phase D0).

---

## Phase H — Tests

### H0. `tests/unit/infrastructure/browser/__init__.py` (NEW)

Fichier vide requis pour que pytest découvre les modules de test.

### H1. `tests/unit/infrastructure/browser/test_security.py` (NEW)

- SSRF : URLs bloquées (file://, IPs privées, metadata endpoints)
- Schemes bloqués (javascript:, data:, chrome:)
- Domaines bloqués additionnels (settings)
- Whitelist touches clavier
- Sanitization fill value

### H2. `tests/unit/infrastructure/browser/test_accessibility.py` (NEW)

- Extraction arbre : nodes interactifs détectés
- Assignation refs [E1], [E2]...
- Compaction : branches sans ref supprimées
- Format LLM : indentation correcte
- Hard truncation si > max tokens
- Résolution ref → locator

### H3. `tests/unit/infrastructure/browser/test_pool.py` (NEW)

- Singleton init/close
- Global max sessions via Redis coordination
- Cleanup expired sessions + Redis keys
- Health check si Chromium absent → `is_healthy = False`
- Release session libère Redis key
- Recovery cross-worker (Redis metadata → re-navigation)
- Memory check before navigation

### H4. `tests/unit/domains/agents/tools/test_browser_tools.py` (NEW)

- 6 tools : success path avec session mockée
- Browser disabled → failure output
- Session inexistante → failure
- SSRF → failure
- Content wrapping appliqué avec `source_type="browser_page"` sur navigate/snapshot
- Screenshot disabled → failure
- Rate limiting respecté (via decorators)
- Recovery path : session on different worker → re-navigate
- structlog logging before each failure return

### H5. `tests/unit/domains/agents/graphs/test_browser_agent_builder.py` (NEW)

- Agent construit avec les bons tools
- Screenshot conditionnel
- Prompt chargé correctement

**Marker** : `@pytest.mark.browser` pour skip quand Playwright non installé.
Ajouter dans `pyproject.toml` section `[tool.pytest.ini_options]` markers : `"browser: tests requiring Playwright browser"`.

### H6. Gestion de fin de session

La session browser se ferme dans 3 cas :
1. **Timeout idle** : APScheduler job `cleanup_expired()` toutes les 60s ferme les sessions > `browser_session_timeout_seconds` (300s) + supprime les clés Redis
2. **Limite max_navigations** : La session retourne une erreur et se ferme automatiquement après `browser_max_navigations_per_session` navigations
3. **Erreur critique** : Si Playwright crash (OOM, segfault), la session est marquée erreur et nettoyée au prochain `cleanup_expired()`

Pas de `browser_close_tool` en V1 — la fermeture est automatique. Si le browser agent termine sa tâche (plus d'itérations ReAct), la session reste ouverte jusqu'au timeout idle. C'est acceptable car le timeout est court (5min) et ça permet à l'utilisateur de faire des requêtes de suivi ("maintenant clique sur le 3ème lien") sans relancer une session (recovery transparent si autre worker).

**V2** : envisager un `browser_close_tool` pour permettre la fermeture explicite par l'utilisateur (cas d'une page bloquée ou d'un download infini).

---

## Phase I — Documentation

### I1. `docs/architecture/ADR-056-Browser-Control.md` (NEW)

ADR documentant les décisions architecturales :
- Architecture connecteur complet (même pattern que Wikipedia)
- `--no-sandbox` dans Docker (isolation par container)
- CDP direct pour l'arbre a11y (vs Playwright snapshot deprecated)
- Sessions process-local avec recovery Redis cross-workers
- Coordination globale des sessions via comptage Redis
- HITL plan-level (pas action-level en V1)
- Choix LLM gpt-4.1-mini vs gpt-5-nano

### I2. `docs/technical/BROWSER_CONTROL.md` (NEW)

Documentation technique :
- Architecture (pool, session, security, accessibility)
- Paramètres configurables (.env)
- Sécurité (SSRF, sandbox, interception, sanitization)
- Recovery cross-workers
- Tunables mémoire / rate limiting
- Troubleshooting

### I3. `docs/technical/SECURITY.md` (MODIFY)

Ajouter section "Browser Automation Security" :
- Sandbox handling (`--no-sandbox` + Docker isolation)
- Per-user context isolation
- Credential handling (never persist)
- Browser as attack vector (redirect phishing, injections)
- Resource management (memory/CPU limits)

### I4. `docs/INDEX.md` (MODIFY)

Ajouter les références vers ADR-056, BROWSER_CONTROL.md et la section SECURITY.md.

---

## Récapitulatif des fichiers

| Action | Fichier | Phase |
|--------|---------|-------|
| CREATE | `src/core/config/browser.py` | A |
| MODIFY | `src/core/config/__init__.py` | A |
| MODIFY | `src/core/constants.py` | A |
| CREATE | `src/infrastructure/browser/__init__.py` | B |
| CREATE | `src/infrastructure/browser/models.py` | B |
| CREATE | `src/infrastructure/browser/security.py` | B |
| CREATE | `src/infrastructure/browser/accessibility.py` | B |
| CREATE | `src/infrastructure/browser/pool.py` | B |
| CREATE | `src/infrastructure/browser/session.py` | B |
| CREATE | `src/domains/agents/tools/browser_tools.py` | C |
| MODIFY | `src/domains/agents/tools/__init__.py` | C |
| CREATE | `src/domains/agents/browser/__init__.py` | D |
| CREATE | `src/domains/agents/browser/catalogue_manifests.py` | D |
| CREATE | `src/domains/agents/graphs/browser_agent_builder.py` | D |
| CREATE | `src/domains/agents/prompts/v1/browser_agent_prompt.txt` | D |
| MODIFY | `src/domains/agents/data_registry/models.py` | D |
| MODIFY | `src/domains/agents/graphs/base_agent_builder.py` | D |
| MODIFY | `src/domains/agents/constants.py` | D |
| MODIFY | `src/infrastructure/llm/factory.py` | D |
| MODIFY | `src/domains/llm_config/constants.py` | D |
| MODIFY | `src/domains/agents/registry/domain_taxonomy.py` | D |
| MODIFY | `src/domains/agents/registry/catalogue_loader.py` | D |
| MODIFY | `src/domains/agents/orchestration/orchestrator.py` | D |
| MODIFY | `src/main.py` | E |
| MODIFY | `src/domains/agents/graph.py` | E |
| MODIFY | `apps/api/requirements.txt` | E |
| MODIFY | `apps/api/Dockerfile.dev` | E |
| MODIFY | `.env.example` | E |
| CREATE | `src/infrastructure/observability/metrics_browser.py` | F |
| MODIFY | `apps/web/locales/*/translation.json` (×6) | G |
| CREATE | `tests/unit/infrastructure/browser/__init__.py` | H |
| CREATE | `tests/unit/infrastructure/browser/test_security.py` | H |
| CREATE | `tests/unit/infrastructure/browser/test_accessibility.py` | H |
| CREATE | `tests/unit/infrastructure/browser/test_pool.py` | H |
| CREATE | `tests/unit/domains/agents/tools/test_browser_tools.py` | H |
| CREATE | `tests/unit/domains/agents/graphs/test_browser_agent_builder.py` | H |
| CREATE | `docs/architecture/ADR-056-Browser-Control.md` | I |
| CREATE | `docs/technical/BROWSER_CONTROL.md` | I |
| MODIFY | `docs/technical/SECURITY.md` | I |
| MODIFY | `docs/INDEX.md` | I |
| MODIFY | `apps/api/pyproject.toml` | H |

**Total** : ~20 fichiers créés, ~21 fichiers modifiés

---

## Ordre de livraison

```
Phase A (Config)     → aucune dépendance
Phase B (Infra)      → dépend de A
Phase C (Tools)      → dépend de B
Phase D (Agent)      → dépend de C
Phase E (Wiring)     → dépend de B + D
Phase F (Métriques)  → dépend de B
Phase G (i18n)       → indépendant
Phase H (Tests)      → dépend de A-F
Phase I (Docs)       → indépendant (parallélisable)
```

Phases parallélisables : F + G + I peuvent être faites en parallèle avec D-E.

---

## Vérification end-to-end

1. `BROWSER_ENABLED=true` → `task dev:api` démarre sans erreur, browser agent enregistré, node dans le graph
2. `BROWSER_ENABLED=false` → aucun impact, node absent du graph, tools absents du catalogue, pas de `ModuleNotFoundError` Playwright
3. Chat : "Va sur example.com et dis-moi ce qu'il y a" → plan-level HITL (approval_gate) → navigate + snapshot + réponse
4. Chat : "Clique sur le lien E2" → click + snapshot post-action
5. Chat (follow-up, potentiellement autre worker) : "Maintenant clique sur E3" → recovery Redis transparent → re-navigate → click → snapshot
6. Chat : "Remplis le formulaire de contact" → plan approuvé → fill fields + submit → snapshot
7. URL privée (192.168.x.x) → SSRF bloqué, message d'erreur clair
8. Session expire après 5min d'inactivité → cleanup automatique + clé Redis supprimée
9. 2ème session simultanée (avec `max_concurrent_sessions=1`) → erreur "max sessions reached" (coordination Redis globale)
10. Chromium non installé → health check échoue, browser_agent non enregistré, log WARNING
11. Arbre a11y extrait via CDP (`Accessibility.getFullAXTree`) → refs [E1]-[EN] assignés correctement, hard-truncated si > max tokens
12. `task test:backend:unit:fast` → tous les tests browser passent
13. `task lint:backend` → zéro erreur ruff/mypy/black
