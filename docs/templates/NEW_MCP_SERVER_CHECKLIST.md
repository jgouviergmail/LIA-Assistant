# Checklist: Integrer un Nouveau Serveur MCP

**Nom du Serveur MCP**: _________________________
**Type**: Admin / Per-User
**Developpeur**: _________________________
**Date**: _________________________
**Temps estime**: 2-4h

---

## Pre-requis

- [ ] `MCP_ENABLED=true` dans `.env`
- [ ] `MCP_USER_ENABLED=true` dans `.env` (si per-user)
- [ ] Le serveur MCP est accessible via HTTP/HTTPS (Streamable HTTP)
- [ ] Documentation du serveur MCP disponible (liste des tools)

---

## Phase 1: Configuration du Serveur (30 min)

### 1.1 Admin MCP (via API admin)

- [ ] **Appeler l'endpoint de creation** :
  ```bash
  POST /api/v1/admin/mcp/servers
  {
    "name": "nom-du-serveur",
    "url": "https://serveur-mcp.example.com/mcp",
    "auth_type": "none|api_key|bearer|oauth",
    "auth_config": { ... },
    "enabled": true
  }
  ```

- [ ] **Tester la connexion** :
  ```bash
  POST /api/v1/admin/mcp/servers/{server_id}/test
  ```

- [ ] **Verifier les tools decouverts** (reponse du test_connection)
  - Tool 1: _________________________ (description: _________________________ )
  - Tool 2: _________________________ (description: _________________________ )
  - Tool 3: _________________________ (description: _________________________ )

### 1.2 Per-User MCP (via Settings utilisateur)

- [ ] **L'utilisateur configure son serveur** dans Settings > MCP Servers
- [ ] **Verifier que le test_connection fonctionne** depuis l'UI

---

## Phase 2: Description de Domaine (15 min)

### 2.1 Auto-generation LLM

- [ ] **Verifier la description auto-generee** apres test_connection
  - Description generee: _________________________
  - Est-elle pertinente pour le routing semantique ? ☐ Oui ☐ Non

- [ ] **Si description insuffisante**, fournir manuellement :
  ```bash
  PATCH /api/v1/admin/mcp/servers/{server_id}
  {
    "domain_description": "Description optimisee pour le routing"
  }
  ```

### 2.2 Convention `read_me`

- [ ] **Le serveur expose-t-il un outil `read_me` ?** ☐ Oui ☐ Non
  - Si oui : le contenu sera auto-injecte dans le prompt planner
  - Verifier que le contenu `read_me` ne depasse pas `MCP_REFERENCE_CONTENT_MAX_CHARS` (defaut: 30000)

---

## Phase 3: Configuration des Tools (30 min)

### 3.1 Visibilite

- [ ] **Configurer la visibilite de chaque tool** :
  | Tool | Visibilite | Notes |
  |------|-----------|-------|
  | _________________________ | `["llm"]` / `["app"]` / `["llm", "app"]` | _________________________ |
  | _________________________ | `["llm"]` / `["app"]` / `["llm", "app"]` | _________________________ |
  | _________________________ | `["llm"]` / `["app"]` / `["llm", "app"]` | _________________________ |

  - `["llm"]` : outil disponible dans le catalogue LLM (classique)
  - `["app"]` : outil app-only, rendu uniquement en iframe (filtre du catalogue LLM via `is_app_only()`)
  - `["llm", "app"]` : outil disponible dans les deux modes

### 3.2 MCP Apps (si applicable)

- [ ] **Le serveur fournit-il des outils avec `meta.ui.resourceUri` ?** ☐ Oui ☐ Non
  - Si oui : les resultats seront rendus en iframes sandboxees via `McpAppWidget`
  - Verifier que le HTML ne depasse pas `MCP_APPS_MAX_HTML_SIZE` (defaut: 500KB)

### 3.3 Excalidraw (si applicable)

- [ ] **Le serveur est-il un serveur Excalidraw ?** ☐ Oui ☐ Non
  - Si oui : l'outil `create_view` sera intercepte par `_prepare_excalidraw()`
  - Configurer `MCP_EXCALIDRAW_LLM_PROVIDER` et `MCP_EXCALIDRAW_LLM_MODEL`

---

## Phase 4: Securite (15 min)

- [ ] **Verifier HTTPS** : le serveur est accessible en HTTPS (obligatoire en production)
- [ ] **Verifier SSRF** : l'URL ne pointe pas vers une IP privee (validation automatique)
- [ ] **Credentials chiffrees** : si auth_type != none, les credentials sont chiffrees avec Fernet
- [ ] **Rate limiting** : configurer les limites par serveur/tool si necessaire
- [ ] **COEP headers** (si MCP Apps) : verifier que `Cross-Origin-Embedder-Policy: credentialless` est present

---

## Phase 5: Tests (30 min)

### 5.1 Tests manuels

- [ ] **Requete via chat** : envoyer une requete utilisateur qui devrait router vers ce serveur MCP
- [ ] **Verifier le routing** : le planner inclut-il les tools MCP dans le plan ?
- [ ] **Verifier l'execution** : le tool s'execute-t-il correctement ?
- [ ] **Verifier le rendu** : les resultats s'affichent-ils correctement (cards, iframes) ?

### 5.2 Tests unitaires

- [ ] **Test tool adapter** : verifier le parsing des resultats JSON
  ```python
  # tests/unit/infrastructure/mcp/test_tool_adapter.py
  async def test_mcp_tool_result_parsing():
      # ...
  ```

- [ ] **Test connexion** : verifier test_connection
  ```python
  async def test_mcp_server_connection():
      # ...
  ```

---

## Phase 6: Documentation (15 min)

- [ ] **Documenter le serveur** dans les notes internes (Wiki, Confluence, etc.)
  - Nom et URL du serveur
  - Liste des tools avec descriptions
  - Authentification requise
  - Cas d'usage principaux

- [ ] **Mettre a jour `CLAUDE.md`** si le serveur est utilise globalement (admin MCP)

---

## Phase 7: Monitoring (15 min)

- [ ] **Verifier les metriques Prometheus** :
  - `mcp_tool_call_duration_seconds` : latence des appels
  - `mcp_tool_call_total` : nombre total d'appels (labels: server, tool, status)
  - `mcp_connection_errors_total` : erreurs de connexion

- [ ] **Ajouter une alerte** si le serveur est critique :
  ```yaml
  - alert: MCPServerDown
    expr: rate(mcp_connection_errors_total{server="nom-du-serveur"}[5m]) > 0.5
    for: 5m
    labels:
      severity: warning
  ```

---

## Validation Finale

- [ ] Serveur MCP accessible et fonctionnel
- [ ] Tools decouverts et disponibles dans le catalogue
- [ ] Description de domaine pertinente pour le routing
- [ ] Securite validee (HTTPS, SSRF, credentials)
- [ ] Tests manuels reussis
- [ ] Monitoring en place

**Date de completion**: _________________________
**Notes**: _________________________
