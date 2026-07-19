# ADR-134 : Erreurs d'outils actionnables — bandeau « Reconnecter » sur échec connecteur (Lot 3 P3)

**Statut** : Accepté — implémenté (backend + frontend), preuve runtime dev bout-en-bout.
**Date** : 2026-07-18
**Contexte produit** : P3 du chantier « UX cœur conversationnel », suit [ADR-132](ADR-132-HITL-Approval-Cards.md) et [ADR-133](ADR-133-Execution-Trace-Per-Message.md).

## Contexte

Quand un connecteur OAuth casse (token révoqué, 401/403 fournisseur), l'échec
de l'outil ne produit qu'une excuse générique du LLM — l'utilisateur ignore
que la réparation est à un clic (reconnecter dans les réglages). Le plan
initial (whitelister `ToolErrorCode.UNAUTHORIZED` dans les résultats d'outils)
a été **invalidé par l'investigation** : trois découvertes code-prouvées ont
reconfiguré le design.

1. **`ToolErrorCode.UNAUTHORIZED`/`FORBIDDEN` ne sont produits par aucun tool
   connecteur** (seul le validator les emploie, autre sémantique). Une
   whitelist sur ces codes aurait été une feature morte.
2. **`connectors/error_handlers.py` est décoratif** : `handle_oauth_error`
   n'est appelé nulle part, `RefreshError` n'est attrapé nulle part.
3. Les vrais signaux sont des **exceptions typées** : `ConnectorAPIError`
   (401/403/429 API directs, porte `connector_type` + statut upstream) et le
   chemin dominant — refresh rejeté `invalid_grant` — qui levait un
   `raise_invalid_input` générique **et** était ré-avalé par l'`except
   Exception` de `get_connector_credentials` (log mensonger
   « decryption_failed » sur un refresh rejeté).

## Décision

Classification par **types d'exceptions, jamais par message** (règle taxonomie).

- **`ConnectorTokenExpiredError(ValidationError)`** (nouvelle,
  `core/exceptions.py`) : levée par `_refreshoauth_token` sur refresh rejeté,
  porte `connector_type`. L'héritage préserve le contrat HTTP 400 et tous les
  `except ValidationError` existants. `get_connector_credentials` la re-lève
  telle quelle (fix de l'except avaleur). `ConnectorAPIError` expose désormais
  `connector_type`/`upstream_status_code` en attributs typés.
- **Module `services/connector_error_notice.py`** :
  `classify_connector_exception` (TokenExpired → reconnect ; API 401/403 →
  reconnect ; 429 → rate_limit ; tout le reste → None — un faux « Reconnecter »
  sur une panne transitoire est pire que rien) et
  `emit_connector_notice_for_exception` — événement custom LangGraph
  `execution_step` / `step_type: "tool_error"`, writer défensif (no-op hors
  run : skills, sub-agents, tests), métrique
  `connector_error_notices_total{connector_type, action}`.
- **Trois points d'émission** : le handler central `handle_tool_exception`
  (`runtime_helpers.py`) — le point PRINCIPAL, car `ConnectorToolBase`
  attrape toute exception à `base.py::except Exception` (elles n'atteignent
  jamais les exécuteurs pour les tools standard) ; il mappe aussi
  l'`error_code` du résultat vers UNAUTHORIZED/RATE_LIMIT_EXCEEDED (honnête
  pour le LLM). Plus deux filets : la boucle `return_exceptions` du
  `parallel_executor` (pipeline) et l'`except` de `react_execute_tools`
  (tools à coroutine directe).
- **Contrat SSE structuré** : `{connector_type, action, tool_name}` — les
  libellés sont résolus côté client (`CONNECTOR_LABELS`), le backend n'émet
  jamais de chaîne traduite.
- **Frontend** : interception `step_type === "tool_error"` avant
  l'accumulateur de progression (pattern compaction) → `CONNECTOR_NOTICE_ADD`
  (dedup par `(connectorType, action)` dans le reducer — le backend émet par
  step échoué) ; `ConnectorNoticeBanner` ambre au-dessus de l'input :
  message i18n ×6 (`chat.connector_notice.*`), lien « Reconnecter » →
  `/{lng}/dashboard/settings?section=connectors`, dismiss ✕ ; notices
  effacées au prochain envoi (nouveau tour, verdict frais).

## Périmètre et limites

- Le bandeau sort **au run qui casse**. Aux runs suivants, le connecteur est
  en `status=ERROR` et n'est plus résolu comme provider actif
  (`provider_resolver` exige ACTIVE) → l'outil répond « pas de connecteur »
  sans exception typée. **V2** : détecter un connecteur requis en statut
  ERROR au moment de la résolution et émettre la même notice.
- Le `raise_invalid_input` réseau du refresh (transient) reste volontairement
  générique — pas de « Reconnecter » sur une panne réseau.
- 429 : les clients retentent en interne ; un 429 forwardé est rare — l'encart
  rate_limit existe mais sera peu vu (informatif, sans bouton).

## Preuves

- Backend : 15 tests unitaires (classification, émission, writer indisponible,
  contrat d'héritage, handler central) ; 51 tests d'intégration connecteurs
  verts sans modification (compat héritage prouvée) ; unit fast 10 435 verts ;
  ratchet tailles 9/9 (marges serrées tenues : service 1560/1562,
  runtime_helpers 672/674).
- Frontend : reducer 5 tests (dedup, dismiss, clear on send), interception 4
  tests, bandeau 5 tests ; suite complète 1 371 verts ; tsc/eslint/prettier
  propres ; ratchets a11y/hooks/CC tenus ; parité i18n ×6.
- Runtime dev bout-en-bout : token Gmail corrompu de façon réversible
  (credentials rechiffrées via les utilitaires de l'app, backup préalable) →
  `oauth_token_refresh_rejected` (invalid_grant) → `ConnectorTokenExpiredError`
  propagée → `connector_error_notice_emitted` → chunk SSE
  `{connector_type: "google_gmail", action: "reconnect",
  tool_name: "get_emails_tool", step_type: "tool_error"}` observé dans le flux
  → bandeau « Reconnecter » vérifié en navigateur réel. État restauré
  (credentials + status + session temporaire supprimée).
