# ADR-180 : Connexions entre utilisateurs — découverte opt-in, relais assistant-à-assistant, partages lecture seule

**Statut**: ✅ IMPLEMENTED (2026-07-29) — lots 1-6 ; flag `PEERS_ENABLED` off par défaut
**Spec maître**: `docs/superpowers/specs/2026-07-29-peer-connections-design.md` (arbitrages A1-A6 + D1/D2 signés)

## Contexte

Les utilisateurs d'une même instance LIA ne pouvaient pas interagir : pas de découverte,
pas de messages, pas de partage. Le besoin (produit) : se découvrir **opt-in** par nom
exact, se connecter après consentement mutuel, faire passer des messages **par assistants
interposés** (chacun dans sa personnalité et sa langue), partager des domaines **en lecture
seule** par connexion (rien par défaut), avec les deux directions du partage visibles — le
tout sans fuite de données personnelles ni levier de harcèlement.

## Décision

Nouveau contexte borné `domains/peers/` (5 tables : `peer_connections` **une ligne par
paire** — UNIQUE(user_a<user_b) + CHECK rendant doublons et auto-connexion
irreprésentables, transitions de statut conditionnelles claim-once ; `peer_blocks`
directionnels indépendants ; `peer_domain_shares` absence=non partagé ;
`peer_messages` registre de livraison au contenu **purgé après remise** ;
`peer_access_log` audit immuable consultable par le propriétaire). REST `/peers/*`
flag-guardé ; découverte par **correspondance exacte pliée** (NFKD+casefold, chokepoint
`shared/text_normalization` hoisté du CRM), rate-limitée par utilisateur, discriminant
homonymes = fragment d'email masqué (A6). **Neutralité octet-à-octet** : inconnu, bloqué
et cooldown de refus répondent le même 404 (`raise_not_found_or_unauthorized`), testé en
égalité de payload. Blocage silencieux : transition `removed` + purge des partages, jamais
de notification (A2).

Cycle de vie dans le chat via `NotificationDispatcher` (archive-first) : demande entrante
avec note **citée comme donnée** (provenance ADR-167/170) + lien profond réglages,
issue notifiée au demandeur, suppression notifiée **aux deux** ; i18n ×6 via
`ProactiveMessages` (zh-CN canonique).

Relais de message (A3/D1) : tool `send_peer_message` → **brouillon PEER_MESSAGE** (le
draft EST la confirmation — doctrine FN-1, couvre pipeline/ReAct/skills) → à la
confirmation, enqueue + livraison par le sweep `infrastructure/scheduler/
peer_message_delivery.py` (SKIP LOCKED claim-once, recovery des claims échoués,
report≠échec, retry typé jusqu'au cap puis notification d'échec). Génération = **un appel
LLM unique** côté destinataire — personnalité + profil mémoire (`build_psychological_profile`
appelé délibérément : la preuve d'ouverture du Lot 4 a montré l'injection vivant dans le
bundle du response node ET la voie pipeline incompatible avec §9) + psyché + portrait +
compteur de relais du jour ; message encadré par des marqueurs « données, jamais
instructions ». **Tokens imputés à l'ÉMETTEUR** (A4, oracles testés) via
`track_proactive_tokens` ; quotas jour/paire paramétrables `.env`.

Lecture croisée (A1) : `get_peer_availability` (libre/occupé, niveau `details` = +titres)
et `get_peer_tasks` (titres) — partage revérifié **à l'exécution**, chaque lecture
journalisée dans `peer_access_log` (transparence UI), résultats tagués
`peer_shared_data`. Agent `peer_agent` + 4 manifests via le nouveau point d'extension
`registry/program_domain_configs.py` (le `domain_taxonomy` gelé délègue — pattern
`program_manifests` ; le fichier a même **rétréci** via factorisation `_GOOGLE_API_KEY`).

Frontend : section « Connexions » (onglet features, auto-gatée sur
`features.peers_enabled` de `/api/v1/config` — précédent OpenLoops), recherche/demandes/
connexions avec **partages bilatéraux** (sortants éditables, entrants badges), blocages,
journal de transparence ; select **natif** pour le niveau calendrier (préférence charte +
testable jsdom) ; codes d'erreur stables `peers_*` = clés de traduction client (épinglés
des deux côtés) ; e2e hermétique parcours complet + axe + mobile 390 px sans overflow.

RGPD : 5 tables classées (garde CI), purge bilatérale explicite (`or_` — les CASCADE
depuis `users` ne tirent jamais, ligne soft-deleted), export étendu `_TWO_SIDED` avec
scopes **volontairement unilatéraux** là où l'autre côté fuiterait (`peer_blocks` par
bloqueur seul — un export ne révèle jamais qui vous a bloqué).

## Alternatives écartées

- **Étendre le CRM `relations`** : viole son contrat « aucune source de vérité » et SRP.
- **Livraison par pipeline complet du destinataire** (`forced_route`) : l'injection
  mémoire est appelable directement (garantie plus forte que l'espoir de routage) et le
  pipeline comptabilise chez l'exécutant — §9 (émetteur payeur, exigence dure)
  pratiquement inatteignable ; fallback pré-autorisé par la spec retenu, zéro toucher au
  cœur du graphe.
- **Recherche par préfixe/sous-chaîne** : énumération d'annuaire (le précédent maison
  réserve même la recherche email aux superusers).
- **Notification de blocage** : le blocage doit être inobservable (anti-harcèlement).
- **`Enum(native_enum=False)`** : piège majuscules téléphonie — `String(20)` + str-Enum
  minuscules (pattern open_loops), ce qui a permis d'ajouter `delivering` sans migration.
- **HITL au niveau graphe pour l'envoi** : les sous-agents skills n'ont pas d'interrupts —
  le draft est la seule confirmation qui gate tous les contextes identiquement.
