# ADR-224 : conformité MCP 2026-07-28 — client dual-era (SDK v2) et OAuth lié à l'issuer

**Statut**: ✅ IMPLEMENTED (2026-08-17)
**Date**: 2026-08-17
**Origine**: analyse de conformité à la spécification MCP 2026-07-28 (demande propriétaire)

## Contexte

La révision 2026-07-28 du Model Context Protocol est une refonte majeure :
protocole **sans état** (suppression du handshake `initialize` et de
`Mcp-Session-Id`, version et capacités portées par le `_meta` de chaque
requête, `server/discover` obligatoire côté serveur), et durcissement du
volet autorisation (validation `iss` RFC 9207, credentials liés à l'issuer,
`application_type` exigé en Dynamic Client Registration — lui-même déprécié
au profit des Client ID Metadata Documents).

LIA était un client « legacy » au sens de la matrice de compatibilité
normative de la spec : le SDK 1.28.1 (épinglé `<2.0.0`) parle au plus
2025-11-25 via `initialize`, et la matrice est explicite — *Legacy client →
Modern server: Fails, legacy clients have no fall-forward mechanism*.
Simulation à l'appui : face à un serveur modern-only répondant 400 au
handshake (comportement normatif), LIA échouait sur un
`HTTPStatusError: 400` brut, enfoui dans un `ExceptionGroup` imbriqué que le
dépliage à un seul niveau de `user_pool.py` ne perçait pas. Trois MUST du
volet OAuth étaient par ailleurs violés (aucune lecture du paramètre `iss`
au callback, credentials DCR sans liaison à l'issuer, `application_type`
absent), et le client s'annonçait `mcp/0.1.0` (défaut du SDK).

## Décision

**Trois lots, livrés dans l'ordre, chacun sans régression sur l'existant.**

1. **Conformité OAuth (indépendante du SDK)** — l'issuer découvert est
   enregistré à l'initiation du flux (state Redis + `oauth_metadata` JSONB,
   aucune migration) ; un `iss` présent au callback est comparé à l'issuer
   enregistré AVANT tout échange du code (mismatch → rejet loggé hosts-only,
   absent d'un côté ou de l'autre → flux inchangé, ce qui préserve GitHub et
   les states hérités) ; l'issuer voyage dans le blob de credentials chiffré,
   et une initiation ultérieure qui découvre un issuer **différent** jette le
   `client_id` mémorisé et re-registre (pas de DCR disponible → erreur
   explicite ; issuer simplement inconnu → aucune invalidation — tolérance
   pour l'existant) ; la DCR déclare `application_type` dérivé de l'hôte du
   callback (loopback → `native`, sinon `web`). Le callback devient un vrai
   cible de redirection navigateur : paramètres optionnels, refus utilisateur
   (`error=access_denied`) → marqueur `mcp_oauth=denied` et toast informatif
   dédié (i18n ×6), erreur fournisseur jamais réfléchie dans l'URL
   (allowlist RFC 6749 partagée `safe_oauth_error_code_value`), fini le 422.

2. **Robustesse et identité** — `unwrap_exception_group` (récursif) et
   `is_modern_only_rejection` (HTTP 400 au handshake, JSON-RPC `-32022`)
   factorisés dans `infrastructure/mcp/utils.py` ; le chemin éphémère
   utilisateur passe par un unique `_surface_root_cause` (trois duplications
   supprimées) qui fait remonter la cause racine ou un
   `MCPModernOnlyServerError` au message actionnable — la spec note que ce
   diagnostic est le seul signal que l'utilisateur verra jamais ;
   `clientInfo` devient `LIA/<settings.app_version>` sur tous les chemins.

3. **Migration SDK v2 (`mcp>=2.0.0,<2.1.0`)** — le client devient
   **dual-era** : `Client` en `mode="auto"` (défaut) parle 2026-07-28 ET
   retombe automatiquement sur `initialize` face aux serveurs 2025-11-25 et
   antérieurs. Les transports v2 tournent sur **httpx2** (lignée httpx 2.x
   sous un nouveau nom d'import, coexistant avec `httpx` 0.x) : les classes
   d'auth MCP subclassent `httpx2.Auth` (interface identique, y compris le
   retry 401→refresh d'`async_auth_flow`), le POST de refresh token reste sur
   `httpx`. Le pattern éphémère est conservé et factorisé
   (`_ephemeral_client` : httpx2.AsyncClient aux timeouts recommandés MCP
   30 s/300 s-read + `Client`, un scope async par opération) ; le
   `client_manager` admin garde ses sessions lifespan via `AsyncExitStack`.
   Renames v2 absorbés (`is_error`, `input_schema`, `read_resource(str)`).

## Preuves (exécutées, pas supposées)

- Dual-era : client v2 `mode="auto"` contre un serveur réel 1.28.1 — stdio et
  Streamable HTTP — sonde `server/discover` rejetée puis fallback `initialize`,
  outils découverts et appelés ; sanity moderne↔moderne.
- E2E sur le code LIA migré : `UserMCPClientPool.get_or_connect` +
  `call_tool` (auth httpx2 incluse, auto-fetch `read_me`) contre un serveur
  legacy 1.28.1 **et** un serveur moderne 2.0.0.
- Runtime Docker dev : conteneur `lia-api-dev` healthy, serveur admin
  excalidraw connecté en streamable_http (5 outils) via le client v2.
- Graphe de dépendances : toutes les contraintes transitives de mcp v2 déjà
  satisfaites par le lock (starlette 1.3.1, anyio 4.12.1, opentelemetry-api
  1.42.1…) ; seuls `httpx2`/`mcp-types` sont nouveaux ; `task deps:lock`
  sans conflit.
- Suites : 17 279 tests unitaires backend, 5 510 frontend, tous verts ;
  MyPy strict sans écart ; ratchets shrink-only tenus (le hotspot CC introduit
  sur la page settings a été résorbé par table de correspondance — CC final
  inférieur à l'original).

## Conséquences

- Tout serveur MCP fonctionnant avec LIA avant migration continue de
  fonctionner (legacy et dual-era) ; les serveurs modern-only deviennent
  accessibles. Aucune donnée utilisateur ne migre, aucune ré-authentification
  n'est déclenchée par la migration elle-même — seule un changement réel
  d'authorization server force la re-registration, ce qui est précisément
  l'exigence de sécurité de la spec.
- Rollback atomique : revert du couple manifeste + lockfiles (ADR-112).
- Non retenu à ce stade (opportunités documentées) : consommation de
  `structured_content`, cache `ttl_ms`/`cache_scope` natif du SDK
  (SEP-2549), Client ID Metadata Documents (nécessite d'héberger un
  document de métadonnées public), callbacks MRTR. La détection d'issuer ne
  se déclenche qu'aux initiations avec découverte fraîche (le cache
  `oauth_metadata` court-circuite la découverte — limite documentée).
