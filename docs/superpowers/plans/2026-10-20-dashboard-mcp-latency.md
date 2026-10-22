# Dashboard et MCP — plan d'implémentation TDD

> **For agentic workers:** utiliser `superpowers:executing-plans`, tâche par
> tâche, **strictement inline, sans sous-agent**, conformément à la demande de
> l'utilisateur. Ce plan ne constitue pas un ordre d'implémentation.

**Goal:** réduire le délai jusqu'au premier résultat utile sans perte de
capacités, de confidentialité ou de maîtrise des dépenses.

**Architecture:** catalogue MCP personnel persistant et vérifié, préparation
parallèle bornée et contexte assemblé dans le parent ; notices avant graphe.
Dashboard progressif dans le domaine briefing, lectures indépendantes liées à
un contexte éphémère, puis génération commune sur ces mêmes résultats.

**Tech Stack:** FastAPI, asyncio, PostgreSQL/JSONB, Redis, Next.js/React,
schemas Python et TypeScript stricts, Vitest et Playwright existants.

**Spec:** [Analyse systémique](../specs/2026-10-20-dashboard-mcp-latency-systemic-analysis.md).
Les IDs de tests renvoient à sa matrice. Tous les chemins de code ci-dessous
sont relatifs à la racine du dépôt ; « nouveau » désigne un fichier à créer,
pas une capacité déjà disponible.

## Contraintes globales

- Aucun code métier pendant l'étude ; aucun commit, push ou déploiement de cette
  analyse. À l'exécution autorisée, préserver le travail concurrent et isoler
  les seuls changements du lot, sans reset ni formatage global.
- Avertissement **informatif seulement**, sans action de désactivation. Aucune
  suspension persistée, migration de suspension ou commande HITL supplémentaire.
- Quatre préparations réseau MCP simultanées **par processus**, sémaphore commun
  au pool. Avertissement initial après dix secondes. TTL existants de découverte
  et timeouts d'outils conservés ; ces deux valeurs nouvelles sont configurables.
- Lecture dashboard proposée : expiration dix minutes après création, quatre
  lectures actives et seize manifestes retenus maximum par compte. Éviction
  des seuls manifestes terminés, jamais d'une opération payante en cours.
  Consultations d'attente : au plus trois
  reprises, sans relance fournisseur. Les bornes sont publiées par le contrat.
- Une seule déclaration canonique des sections et de leurs politiques ; aucun
  partage d'`AsyncSession` ni transaction ouverte pendant une attente réseau.
- Aucune génération ou dépense d'embeddings automatique si quota bloqué ou
  coordination payante incertaine. Pas de retry automatique de mutation MCP.
- Contrôles frais de droits et preuves SMS avant restitution, y compris cache.
  État de progression absent des messages, checkpoints et mémoires applicatives.
- Réutiliser les templates, garde de compte, toaster, projections et portes de
  facturation. Pas de nouvelle dépendance pour cette architecture.
- Ne relever ni baselines ni seuils de qualité pour faire passer un lot.
  Découper les fichiers existants seulement aux responsabilités touchées.
  Typage Python/TypeScript strict, schemas Pydantic documentés, UTC conscient
  pour la persistance, erreurs centrales et aucun contournement `as any`.

## Ordre et frontières de livraison

`00 → 00 bis` vérifie puis corrige en priorité la régression SMS déployée.
La mesure après ce correctif réévalue la nécessité et le périmètre des lots
structurels suivants. `01 → 02 → 03 → 04` forme le sous-projet MCP autonome.
`05 → 06 → 07 → 08 → 09` forme le sous-projet dashboard progressif proposé.
Exécuter ces lots successivement en inline ; l'indépendance architecturale
n'est pas une autorisation de déléguer. `10` optimise les fetchers après mesure.
`11` qualifie les changements réunis. `12` traite séparément le réseau cible.

Chaque lot suit le même cycle : test comportemental RED, vérification du motif
d'échec, minimum de production, GREEN ciblé, contrôle des contrats voisins,
revue inline du diff. Un environnement qui ne lance pas les tests ne constitue
pas un RED valide. Les commits éventuels font partie d'une livraison autorisée
ultérieure ; ne jamais inclure les autres changements du répertoire partagé.

## Points de revue prioritaires

1. Révocation ou changement de compte pendant une lecture : aucune donnée de
   l'ancien contexte ne peut être restituée ; tests D07/D08/M08.
2. Perte de bail après envoi facturé : ne pas confondre absence de résultat et
   absence de dépense ; tests D04/D09.
3. Catalogue MCP connu seulement par un autre worker : hydrater le pool sans
   inventer une session connectée ni changer les outils ; tests M03/M05/M07.
4. Notice produite avant graphe et replay SSE : ni retard artificiel jusqu'au
   premier token ni notification historique répétée ; tests N01/N02/N04.
5. Invalidation alors qu'un writer travaille encore : supprimer un cache ne
   suffit pas ; clôturer sa publication et sa révision front ; tests D06/M04.

## Lot 00 — figer les contrats et rendre le harnais observable

**Fichiers existants à relire :** `CLAUDE.md`, `apps/web/CLAUDE.md`,
`Taskfile.yml`, configurations pytest/Vitest/Playwright, tests listés ci-dessous.
**Artefacts :** dossier ignoré `.tmp/prod-latency-20261020/` ; ne pas y écrire de
credentials ou contenu personnel.

**Entrée :** état Git indexé/non indexé et contexte Docker courant.
**Sortie :** baseline datée, compteurs d'appels et harnais ciblé fonctionnel.

- [ ] Inventorier index, worktree et nouveaux fichiers, enregistrer les empreintes
  des fichiers touchés ; distinguer les modifications déjà présentes.
- [ ] Rejouer d'abord un seul test existant sans réseau externe, avec logs de
  collecte et borne de durée ; l'exécution ciblée tentée pendant l'analyse a
  été interrompue sans résultat et ne valide rien.
- [ ] Qualifier les fixtures de dépenses/Redis/DB si elles empêchent ce test de
  terminer ; corriger seulement une cause démontrée du harnais, sans skip ou
  désactivation globale des contrôles de dépense.
- [ ] Rejouer les sentinelles briefing (`test_page_load_single_flight.py`,
  `test_cache_key_contract.py`, `test_sms_card_preview.py`,
  `test_hidden_sections.py` dans `apps/api/tests/unit/domains/briefing/`) et MCP
  (`test_user_context_vectors.py`, `test_failure_pause.py`,
  `test_mutation_policy_derivation.py`, `test_reserved_arguments.py` dans
  `apps/api/tests/unit/infrastructure/mcp/`). Rapporter nombre, skips et durée.
- [ ] Préparer les doubles de transport avec `asyncio.Event`, horloge injectée,
  compteurs de tentatives physiques et deux producteurs réels pour Redis.
  Garder les tests d'API et de frontend attachés aux mêmes discriminants.

**Commande ciblée type, depuis `apps/api/` :**

```powershell
.venv/Scripts/python -m pytest tests/unit/domains/briefing/test_cache_key_contract.py -q --no-cov -o addopts=''
```

Ne pas transformer un lancement bloqué en succès présumé ; conserver le log et
résoudre la cause avant les cycles RED/GREEN concernés.

## Lot 00 bis — retirer les aperçus SMS du polling incomplet

**Fichiers existants :** `apps/api/src/domains/briefing/service.py`,
`cached_cards.py`, `sms_context.py` et
`apps/api/tests/unit/domains/briefing/test_sms_card_preview.py` ; tests de
coordination partagée dans les suites `single_flight` existantes.

**Constat vérifié :** la production contient la modification non commitée
`_published_bundle → _read_cached_bundle(sms_previews=True)`. Chaque vérification
peut ouvrir les aperçus puis les contacts. Le probe A/B isolé donne six lectures
d'aperçus sur six vérifications, contre aucune dans HEAD. Les 16 tests existants
SMS/MCP relancés passent mais ne testent pas cette amplification.

- [ ] RED : plusieurs vérifications d'un bundle encore incomplet ne doivent
  appeler ni les aperçus ni les contacts. Compter les appels avec une barrière
  sur une autre source ; ne pas se contenter d'un délai simulé plus court.
- [ ] Vérifier d'abord la disponibilité des seules sections cachables, en
  réutilisant le lecteur existant avec exclusion SMS. Lire les SMS vivants
  une fois le bundle publiable, avec la politique de masquage et les contrôles
  de révocation existants. Ne pas supprimer ces contrôles pour gagner du temps.
- [ ] GREEN : bundle prêt avec aperçu, bundle incomplet sans aperçu, SMS masqué,
  source en erreur, révocation pendant attente, plusieurs workers/waiters.
- [ ] Mesurer lectures et délai résiduels dans Docker dev ; réévaluer les lots
  structurels du dashboard à partir de ces résultats avant leur implémentation.

Ce préalable est une proposition de correction ; aucune écriture métier n'est
autorisée par la seule demande de vérification. Son résultat attendu est une
correction ciblée, sans nouveau protocole HTTP ni changement de modèle.

## Lot 01 — catalogue MCP vérifiable et accès runtime

**Nouveaux :**

- `apps/api/src/infrastructure/mcp/catalogue_snapshot.py` : DTO strict,
  parseur de versions, validation de fraîcheur et configuration.
- `apps/api/src/domains/user_mcp/catalogue_gateway.py` : lecture/publication CAS
  en sessions courtes, politique de données dérivées pour l'export.
- `apps/api/src/domains/user_mcp/runtime_access.py` : contrôle frais d'exécution,
  indépendant de l'autorisation de gérer les applications.
- `apps/api/tests/unit/infrastructure/mcp/test_catalogue_snapshot.py`.
- `apps/api/tests/unit/domains/user_mcp/test_catalogue_gateway.py`.
- `apps/api/tests/unit/domains/user_mcp/test_runtime_access.py`.

**Modifier :** `user_mcp/models.py`, `service.py`, `projection.py`,
`repository.py`, `infrastructure/mcp/user_pool.py`, `user_tool_adapter.py`,
`catalogue_fingerprint.py` seulement si son contrat exige une extension ;
`domains/account_export/builder.py` et tests associés pour les champs dérivés.

**Interfaces :**

- `parse_catalogue_snapshot(raw: object) -> CatalogueSnapshotRead`, union
  discriminée `valid/legacy/invalid`, sans `Any` propagé aux lecteurs.
- `catalogue_matches(snapshot: CatalogueSnapshot, spec: MCPServerSpec, now:
  datetime, ttl_seconds: int) -> bool` ; empreintes natives réutilisées.
- `publish_catalogue_if_current(user_id: UUID, server_id: UUID,
  expected_configuration: str, snapshot: CatalogueSnapshot) -> bool`.
- `require_user_mcp_runtime_access(user_id: UUID, server_id: UUID,
  expected_configuration: str, expected_runtime_policy: str) ->
  MCPRuntimeAccessDecision` ; activation/statut/capacité/mode/HITL contrôlés
  séparément de l'empreinte de transport, aucune réactivation automatique.
- `UserMCPClientPool.hydrate_catalogue(spec: MCPServerSpec, snapshot:
  CatalogueSnapshot) -> PoolEntry` ; ne réalise aucune I/O fournisseur.

- [ ] RED M03/M04/M08 : anciens formats liste/dict lisibles par l'UI mais pas
  réputés frais ; `NULL`, mauvaise version, entrées malformées, outils trop
  nombreux, changement URL/scopes/credentials, rotation access token et
  découverte terminée après suppression.
- [ ] Exécuter ces tests et constater le manque d'enveloppe/CAS/garde runtime.
- [ ] Implémenter le parseur, l'enveloppe JSONB, la publication CAS et l'hydratation
  sans réseau. Conserver la représentation native des schemas et métadonnées.
- [ ] Brancher la même publication dans `test_connection` et le chemin de
  découverte, sans appeler toute la procédure de test depuis le chat.
  Invalider les empreintes/LRU concernés sur les changements de configuration.
- [ ] Brancher le contrôle runtime à toutes les portes d'exécution personnelles ;
  conserver le contrôle frais partagé. Une ancienne approbation avec une
  nouvelle configuration ne permet pas l'appel.
- [ ] Vérifier aussi changement de HITL ou de mode à URL inchangée : le digest
  complet des commandes de gestion n'est jamais remplacé par le fingerprint
  transport ; le témoin d'exécution ne donne pas de droit de gestion.
- [ ] GREEN M03/M04/M08, tests de projection/description, arguments réservés,
  round-trip PostgreSQL JSONB, export sans secrets/référence privée ajoutée.

**Résultat livré :** catalogue exploitable à chaud sans découverte réseau, aucun
changement de capacité ou de statut par simple présence du cache. Pas de
migration nécessaire tant que seule la colonne JSONB existante change de format.

## Lot 02 — préparation MCP parallèle, bornée et transaction courte

**Nouveaux :**

- `apps/api/src/infrastructure/mcp/user_preparation.py` : préparation d'un
  serveur, ownership/déduplication et résultats immuables.
- `apps/api/tests/unit/infrastructure/mcp/test_user_preparation.py`.
- `apps/api/tests/integration/infrastructure/mcp/test_shared_preparation.py`.

**Modifier :** `user_context.py`, `user_pool.py`, `tool_vectors.py`,
`domains/user_mcp/connection_embeddings.py`, `domains/agents/api/service.py`,
`core/config/mcp.py` et les surfaces d'environnement déclarées pertinentes.
Conserver les signatures publiques de setup/cleanup pour les autres appelants.

**Interfaces :**

- `MCPServerSpec` : DTO immuable de configuration, propriétaire et préfixe
  réservé ; credentials uniquement dans le transport approprié.
- `PreparedUserServer` : union `ready/failed/skipped`, catalogue, vecteurs
  admissibles et phase/durée ; pas de mutation de `UserMCPToolsContext` enfant.
- `prepare_user_server(spec: MCPServerSpec, emit: MCPProgressSink) ->
  PreparedUserServer` ; le sink asynchrone reçoit des événements typés.
- `assemble_user_context(results: Sequence[PreparedUserServer]) ->
  UserMCPToolsContext` ; ordre initial déterministe, installation parent unique.

- [ ] RED M01/M02 : deux serveurs bloqués sur des Events doivent être entrés
  simultanément ; cinq préparations prouvent la borne commune ; un échec ne
  supprime pas les résultats sains. Aucune assertion fondée seulement sur le
  temps total.
- [ ] RED M05/M06/M09/X01 : deux workers même serveur, Redis perdu, quota
  embeddings nul, active call non évincé, annulation d'un waiter puis du dernier
  owner, scope AnyIO fermé par sa tâche propriétaire.
- [ ] Sortir les données DB en DTO, terminer les écritures nécessaires de
  conversation/composition avant réseau, ne pas déplacer un commit à l'aveugle.
  Ouvrir une session indépendante pour chaque éventuelle écriture de résultat.
- [ ] Préparer sous sémaphore commun au processus, réclamation compte/serveur/
  configuration et contrôle de publication. Redis défaillant : borne locale,
  comportement explicitement dégradé ; pas de recalcul payant non coordonné.
- [ ] Assembler et installer le contexte dans le parent, cleanup en `finally` ;
  préserver les préfixes et le catalogue figé consommé par `turn_catalogue.py`.
- [ ] Coalescer les embeddings avec leur fingerprint et leur modèle ; conserver
  les gates de dépenses, les coûts physiques et le fallback existant.
- [ ] GREEN M01–M09, PostgreSQL `pg_stat_activity` pendant la barrière réseau,
  tests standard/itératif/MCP Apps, pipeline/ReAct et ressources.

**Résultat livré :** gain autonome sur le chemin froid personnel ; chemin chaud
sans découverte, aucune parallélisation du manager partagé de startup.

## Lot 03 — notices MCP émises pendant la préparation

**Nouveaux :**

- `apps/api/src/domains/agents/services/streaming/mcp_initialization.py` :
  adaptateur des progrès vers les chunks, timer et déduplication serveur/tour.
- `apps/api/tests/unit/domains/agents/services/test_mcp_initialization.py`.

**Modifier :** `domains/agents/api/service.py`, `api/schemas.py`,
`domains/agents/api/background_runner.py`, `core/config/mcp.py`,
tests de replay/producteur et marqueurs CI correspondants.

**Interfaces :**

- `MCPPreparationEvent` : serveur, nom public, phase
  `queued/discovering/embeddings/ready/failed`, instant monotone.
- `MCPInitializationNotice` : métadonnées strictes de `execution_step`,
  discriminant `mcp_initialization`, run/serveur/révision/durée/état.
- `iter_preparation_with_notices(...) -> AsyncIterator[PreparationEmission]` :
  union discriminée d'un chunk non terminal ou du résultat final
  `PreparedUserCatalogues`. Le parent diffuse les notices puis assemble et
  installe le contexte après le résultat final ; les enfants n'installent
  jamais un ContextVar. Le producteur est alimenté avant le démarrage du graphe.

- [ ] RED N01 : tenir la préparation, avancer l'horloge au seuil, exiger un chunk
  avant libération et avant tout appel graphe ; distinguer attente en file et
  découverte. Cache chaud/sous seuil/travail autonome ne notifient pas.
- [ ] RED N02/N04 : producteur détaché, reconnexion, cancel, shutdown, HITL/resume,
  routine/canal/voice ; notices absentes des messages et du premier token utile.
- [ ] Créer la file avant préparation, faire produire les enfants et drainer dans
  le parent qui conserve le contexte du tour ; annuler proprement timers et
  tâches. Limiter les mises à jour au changement de phase pertinent.
- [ ] Publier des chunks non terminaux avec identifiant stable ; ne transporter
  ni URL privée, ni texte serveur, ni secret dans la notice.
- [ ] GREEN N01/N02/N04 et tests existants du runner et du streaming.

**Résultat livré :** signal informatif réellement reçu pendant l'attente.

## Lot 04 — notification UI, sans action de désactivation

**Nouveaux :**

- `apps/web/src/lib/sse-handlers/mcp-initialization.ts`.
- `apps/web/src/lib/sse-handlers/__tests__/mcp-initialization.test.ts`.
- `apps/web/e2e/smoke/chat-mcp-initialization.spec.ts`.

**Modifier :** `sse-handlers/types.ts`, `handlers.ts`, `index.ts` selon leurs
exports réels, ressources i18n des langues existantes. Réutiliser
`components/ui/toaster.tsx` ; ne pas ajouter une autre pile de notifications.

**Interface :** handler de `MCPInitializationNotice`, toast stable par
run/serveur, regroupement des serveurs au-delà de la capacité visible, état de
clôture/retour normal, suppression au changement de compte.

- [ ] RED N02/N03 : notices répétées/rejouées, toast fermé, multiples serveurs,
  nom hostile/Unicode/RTL, retour normal et erreur, nouveau compte.
- [ ] Implémenter le message explicatif validé par la spec, sans bouton d'action,
  sans appel d'API de mutation et sans message automatique au chat.
- [ ] Vérifier annonce polie, fermeture au clavier, focus, wraps et safe areas ;
  ne pas utiliser la durée de toast par défaut pour une alerte encore active.
- [ ] GREEN TU, axe et E2E étroit/desktop, thèmes, zoom, mouvement réduit,
  parité i18n stricte ; validation visuelle dans Docker dev.

**Résultat livré :** sous-projet MCP utilisable indépendamment du dashboard.

## Lot 05 — lecture de section et provenance de cache sûres

**Nouveaux :**

- `apps/api/src/domains/briefing/section_reads.py` : porte de lecture isolée.
- `apps/api/src/domains/briefing/section_context.py` : contexte et éligibilité
  issus des règles natives, pas un registre de politiques concurrent.
- `apps/api/tests/unit/domains/briefing/test_section_reads.py`.
- `apps/api/tests/unit/domains/briefing/test_section_context.py`.

**Modifier :** `service.py`, `schemas.py`, `cache_state.py`, `cache_keys.py`,
`fetchers.py`, `constants.py`, `domains/push_channels/cache_invalidation.py`.
Les lecteurs `selected_cards.py` et `cached_cards.py` gardent leur sémantique
pour leurs autres consommateurs.

**Interfaces :**

- `BriefingSectionName` : alias issu de la déclaration exhaustive des sections,
  réutilisé par les schemas de refresh et le frontend.
- `BriefingReadContext` : propriétaire, langue, fuseau, fenêtres, préférences,
  localisation et témoins de sources/consentements, immuable pour une lecture.
- `read_dashboard_section(context: BriefingReadContext, section:
  BriefingSectionName, force: bool, expected_source_generation: int,
  read_act_id: str) -> SectionReadResult` ; distinction provenance/contenu,
  contrôle final de droits.
- `read_admissible_cached_sections(context: BriefingReadContext) ->
  dict[BriefingSectionName, CardSection]` ; zéro réseau fournisseur.
- La lecture owner reçoit aussi `read_act_id` du manifeste ; elle ouvre les
  collecteurs natifs et `out_of_turn_spend` avant un fetch vivant. Le wrapper
  ne se réduit pas à appeler `_section` en perdant les portes de comptabilité.

- [ ] RED D01/D02/D05 : cache absent distinct du non-configuré, carte masquée sans
  I/O, cache d'une autre localisation/fuseau refusé, SMS/local toujours vivants.
- [ ] RED D06/X01 : source invalidée durant lecture et transaction DB retenue.
- [ ] RED X04 : cache hit/waiter n'écrit rien, source réellement ouverte écrit sa
  consultation et sa dépense, annulation clôturée, décisions non multipliées.
- [ ] Réutiliser `_build_plan` et `_section`, factoriser sans recopier les règles
  de provider/consentement des fetchers ; conserver les normalizers et bornes.
- [ ] Versionner les valeurs cache avec contexte/provenance ; anciens formats
  sans témoin deviennent miss. Corriger la classification par âge en utilisant
  l'origine explicite. Poser `generated_at` à la sémantique définie du résultat.
- [ ] Centraliser réservation de génération et publication conditionnelle pour
  refresh et push, y compris variantes de mails et toutes les langues.
- [ ] Appliquer le codec et la clôture de publication à tous les lecteurs et
  writers historiques ; tester les formats ancien/nouveau en coexistence.
  Les routes anciennes gardent leur réponse publique, pas leur format Redis
  interne figé.
- [ ] Conserver l'acte commun de cartes et déposer sa décision par la porte
  `record_decision_once` existante ; durées de sections et durée de page sont
  mesurées séparément. Garder les APIs de `consultation_sink` sans introduire
  de nouvelle dépendance circulaire vers `agents/effects`.
- [ ] GREEN D01/D02/D05/D06/X01 et suites cache/hidden/selected existantes.

**Résultat livré :** lecture réellement ciblée, bootstrap admissible sans réseau,
aucune fuite de droits via cache et pas d'ancien writer republié.

## Lot 06 — lectures éphémères et coordination inter-workers

**Nouveaux :**

- `apps/api/src/domains/briefing/load_schemas.py` : contrats de lecture.
- `apps/api/src/domains/briefing/load_store.py` : manifeste et résultats bornés.
- `apps/api/src/domains/briefing/load_service.py` : cycle de lecture et sharing.
- `apps/api/tests/unit/domains/briefing/test_load_service.py`.
- `apps/api/tests/integration/domains/briefing/test_load_coordination.py`.

**Modifier :** `core/config/briefing.py`, `infrastructure/cache/key_families.py`,
les tests de purge/reset/export et surfaces d'environnement du setting registry.
Réutiliser `single_flight.py` et les primitives `redis_claim.py`, sans changer
la politique du helper global `shared_flight.py`.

**Interfaces :**

- `CreateBriefingLoad(scope: Literal['normal', 'all'] | BriefingSectionName,
  request_id: UUID)` ; validation stricte, pas de contexte utilisateur fourni.
- `BriefingLoad` : `load_id`, `expires_at`, `context_revision`, ordre et
  états `pending/running/settled`, cartes admissibles déjà prêtes. Le manifeste
  privé porte `read_act_id` et la provenance des opérations partagées.
- `create_load(user: User, request: CreateBriefingLoad) -> BriefingLoad`.
- `read_load_section(user_id: UUID, load_id: UUID, section:
  BriefingSectionName) -> SectionReadResponse` ; union `pending/settled`.
- `freeze_load(user_id: UUID, load_id: UUID, expected_revision: str) ->
  FrozenBriefingRead` ; bundle issu exclusivement des résultats serveur,
  couverture et témoins, SMS sans corps dans la structure générique persistée.

- [ ] RED D03/D04/D06 : deux instances de service sur vrai Redis, erreurs
  partagées, deux refresh forcés, owner bloqué au-delà de l'attente historique,
  fin de bail, expiration, mémoire pleine, idempotence et ancien writer.
- [ ] RED D07/D08/X02 : mauvaise personne, compte supprimé, préférence devenue
  cachée, purge des familles et absence de données SMS dans le manifeste.
- [ ] Implémenter manifeste immuable de contexte, résultats séparés et claims
  renouvelés avec publication clôturée. Ne pas relancer un fetch à cause d'un
  nouveau waiter ou d'un nouvel identifiant de lecture équivalente.
- [ ] Configurer TTL/limites proposées, mesurer les payloads maximaux des schemas
  pour choisir et publier la borne de sérialisation ; tester son dépassement
  typé, jamais couper arbitrairement un résultat.
- [ ] Borner aussi manifestes terminés, résultats et tombstones ; prouver que
  leur éviction ne rend pas un travail en cours de nouveau réclamable et qu'un
  `410` ne déclenche aucune génération automatique.
- [ ] En panne Redis, erreur récupérable sans génération automatique et maintien
  des cartes déjà visibles ; aucune récupération cachée par `/cards` historique.
- [ ] GREEN D03/D04/D06/D07/D08/X02 sur Redis jetable et processus distincts.
- [ ] GREEN X04 sur PostgreSQL réel : flushs concurrents de dépenses sous le même
  acte additifs, une décision sans faux segments, aucun second enregistrement
  pour un waiter d'une opération déjà exécutée.

**Résultat livré :** contrat de lecture commun prêt pour HTTP et textes, sans
nouveau stockage permanent ni nouveau registre de sources.

## Lot 07 — textes communs, privacy SMS et budget de prompt

**Nouveaux :**

- `apps/api/src/domains/briefing/load_text.py` : clé canonique, ownership,
  restitution et état `uncertain`.
- `apps/api/src/domains/briefing/prompt_budget.py` : budget total local par slot.
- `apps/api/src/domains/sms/briefing_text_result.py` : stockage/restitution
  éphémères du résultat sensible, contrôlés par le domaine SMS.
- `apps/api/tests/unit/domains/briefing/test_load_text.py`.
- `apps/api/tests/unit/domains/briefing/test_prompt_budget.py`.
- `apps/api/tests/unit/domains/sms/test_briefing_text_result.py`.

**Modifier :** `briefing/llm.py`, `prompt_cards.py`, `sms_context.py`, portes
d'invalidation SMS et familles Redis, `llm/spend_roads.py` uniquement si un
nouveau writer physique apparaît. Éviter de déplacer la porte de facturation.

**Interfaces :**

- `BriefingGenerationConfig` : copie profonde du `LLMAgentConfig` effectif,
  versions/empreintes de prompts, personnalité résolue une fois et horloge locale
  cohérente ; aucune session DB attachée au snapshot.
- `build_text_generation_key(read: FrozenBriefingRead, configuration:
  BriefingGenerationConfig) -> str` ; contenu canonique utile, preuves,
  fenêtres, prompts, personnalité pertinente, slot/configuration effectifs.
- `build_budgeted_briefing_prompt(...) -> BudgetedBriefingPrompt` ; texte,
  compteur local et couverture omise explicite ; sortie réservée.
- `generate_load_text(user: User, read: FrozenBriefingRead) ->
  BriefingTextResult` ; `ready/pending/uncertain/expired`, provenance `reused`.
- `read_current_sms_briefing_text(...) -> GuardedTextResult` : propriétaire et
  consentements natifs vérifiés à chaque restitution ; preuve privée jamais
  exposée au client ni rangée dans le cache générique.

- [ ] RED D04/D08/D09 : deux workers, un seul owner LLM, SMS révoqué pendant
  chaque phase, perte de résultat après envoi, panne Redis avant réclamation,
  dépense connue après annulation. Vérifier exactement les appels et écritures.
- [ ] RED D10 : budget trop petit, gros items, tokens spéciaux, configuration
  changée, résultat de greeting/synthesis asymétrique ; ne pas lancer un second
  LLM pour « réparer » implicitement une erreur.
- [ ] Réutiliser les deux fonctions LLM natives sur le bundle figé et les gates
  de coût ; aucune lecture fournisseur supplémentaire, aucune description MCP.
- [ ] Étendre leur entrée de façon compatible par un snapshot optionnel commun ;
  passer sa configuration au `config_override` existant de `get_llm` et utiliser
  le même contenu de personnalité/temps dans les deux prompts. Tester le
  changement de slot ou de personnalité entre les deux branches, minuit et
  l'invalidation de la clé. Aucun prompt métier inline.
- [ ] Ajouter le budget total avec compteur local et projection par éléments.
  Rendre les trous de collecte explicites sans les transformer en données vides.
- [ ] Partager le résultat ordinaire pour la durée de la lecture ; confier le
  résultat ayant utilisé les SMS à la porte SMS native, TTL borné identique ou
  plus court, purge/invalidation et contrôle frais à chaque réponse.
- [ ] Une issue inconnue reste inconnue ; aucune reprise automatique par un autre
  worker. Réutiliser le greeting de secours si blocage de dépenses. Ne pas
  recopier la comptabilité du premier owner sur chaque cache hit.
- [ ] GREEN D04/D08/D09/D10 + tests de comptabilité, tarifs figés et limites.

**Résultat livré :** textes cohérents et dépenses bornées par l'intention,
restituables entre workers sans contourner la politique SMS.

## Lot 08 — routes progressives additives et contrat API

**Nouveau :** `apps/api/src/domains/briefing/load_router.py` et
`apps/api/tests/unit/domains/briefing/test_load_router.py`.
**Modifier :** routeur briefing et inclusion native, schemas publics si export
nécessaire ; conserver les anciennes routes et leurs réponses.

**Consomme :** `create_load`, `read_load_section`, `freeze_load`,
`generate_load_text`. **Produit :** les trois routes de la spec, validations,
`Retry-After`, erreurs `404/409/410/503`, schemas OpenAPI discriminés.

- [ ] RED D01/D03/D05/D07 : section inconnue, mauvais scope/UUID, autre compte,
  lecture périmée ou non terminée, consentement changé, demandes dupliquées.
- [ ] Exiger la route privée, `no-store`, erreurs de validation assainies et
  session d'authentification courte ; aucun await réseau dans une transaction.
- [ ] Implémenter les seules adaptations HTTP ; ne pas faire de copie de la
  logique service dans le routeur et ne pas accepter de cartes du navigateur.
- [ ] GREEN tests API + contrats historiques `/cards`, `/synthesis`, refresh,
  compagnon et audio, sans modifier les chemins des autres surfaces natives.

**Résultat livré :** API additive disponible sans bascule du frontend.

## Lot 09 — dashboard progressif avec révisions par section

**Nouveaux :**

- `apps/web/src/hooks/useBriefingLoad.ts` : état/annulation de lecture et
  révisions de section avec les primitives de requêtes de compte existantes.
- `apps/web/src/hooks/__tests__/useBriefingLoad.test.tsx`.
- `apps/web/e2e/smoke/briefing-progressive.spec.ts`.

**Modifier :** `hooks/useBriefing.ts`, `useBriefingPreferences.ts` seulement aux
frontières nécessaires, types API briefing, `TodayBriefing.tsx`,
`BriefingCard.tsx`, composants de synthèse/audio et tests associés, traductions.
`BriefingCardsGrid` appartient actuellement à `TodayBriefing.tsx` : ne pas
inventer une extension d'un fichier indépendant inexistant.

**Interfaces :** `useBriefingLoad()` retourne cartes par section,
`loadingBySection`, `errorBySection`, `textState`, révision/lecture,
`refreshSection(name)`, `refreshAll()` et retry explicite. Les contrôles de
compte continuent de venir de `useApplicationAccountQuery` et les préférences
de `useApplicationPreferenceState`.

- [ ] RED D02/D06/D07 : météo suspendue et rappels rendus ; réponse ancienne
  après refresh ; changement de compte ; double clic ; événement pendant
  première lecture et lecture après reconnexion.
- [ ] RED D05/D08/D11 : carte masquée pendant requête, ordre conservé, révocation
  SMS qui efface texte/audio, refresh d'une carte sans refetch des autres et
  sans nouvelle génération automatique.
- [ ] Rendre un emplacement en attente sans faux `NOT_CONFIGURED`, conserver les
  cartes utiles pendant refresh, séparer panne d'une section et panne du
  bootstrap. Garder radio/accès rapides utilisables comme actuellement.
- [ ] Démarrer les lectures indépendantes sans faire passer les cartes locales
  derrière une file externe ; coalescer chaque refresh et appliquer les trois
  consultations maximum d'une opération `pending`.
- [ ] Déclencher les textes une fois les sections prévues terminales ; ignorer
  toute réponse d'une ancienne lecture. Conserver les barrières de confidentialité
  et les invalidations natives, sans cache global partagé entre comptes.
- [ ] GREEN TU composants/hooks, E2E/axe et contrôle visuel Docker dev mobile,
  desktop, clavier, zoom, thèmes, motion et parité des langues.

**Résultat livré :** sous-projet dashboard complet, progressif et cohérent.

## Lot 10 — enrichissements externes sans blocage du résultat principal

**Modifier :** `domains/briefing/fetchers.py` et tests météo/mails existants.
**Nouveau :** tests ciblés dans
`apps/api/tests/unit/domains/briefing/test_fetcher_independence.py`.

**Interface :** schemas de cartes inchangés ; enrichissement optionnel marqué
indisponible si son budget doux expire, limites explicites de concurrence des
détails de mails, politique de retry fournisseur conservée.

- [ ] RED D12 : air/pollen bloqué sans bloquer météo principale ; appel météo
  principal en échec sans prétendre à une carte valide ; mails IDs seulement,
  ordre/dédup conservés, `429` et quota de détails respectés.
- [ ] Retirer seulement les dépendances séquentielles constatées. Mesurer avant
  de paralléliser les détails de mails ; ne pas multiplier les appels au-delà
  des plafonds natifs et ne pas masquer une erreur principale.
- [ ] GREEN fetchers + contrats UI/synthèse ; compteurs de source et essais
  contrôlés de charge avec fournisseurs simulés.

**Résultat livré :** diminution additionnelle de latence sans changement des
contrats fonctionnels, après les gains structurels des lots précédents.

## Lot 11 — qualification transverse, mesures et ratchets

**Modifier au périmètre utile :** `services/streaming/journey_timing.py`,
`latency_sli.py`, point d'observation TTFT existant, observabilité MCP/briefing,
tests de garde de métriques, documentation technique des domaines et runbook.
Ne pas réinitialiser les baselines de couverture, complexité ou taille.

**Interface :** début du parcours API et première réponse utile mesurés une
seule fois ; labels bornés par phase/résultat/cache, jamais par identifiant ou
nom libre ; logs corrélés assainis.

- [ ] RED N04/X01/X02/X03 : événement progressif sans token utile, routine sans
  personne, HITL/resume, transactions inactives pendant réseau, clés non
  classées ou non purgées, payload/objets par worker hors bornes.
- [ ] Observer préparation avant graphe et phases de carte ; documenter le
  changement éventuel de frontière d'une métrique historique, sans masquer
  l'ancienne période ni compter deux fois le même tour.
- [ ] Rejouer toute la matrice D/M/N/X selon son niveau et tous les consommateurs
  indirects : compagnon, lectures sélectionnées, chat pipeline/ReAct, MCP Apps,
  ressources, canaux, voix, initiatives et tâches autonomes du produit.
- [ ] Exécuter les gates pertinents : `task lint:backend`,
  `task lint:frontend`, `task lint:i18n`, `task test:markers`,
  `task test:backend:unit:coverage`, `task test:frontend:coverage`,
  `task test:e2e`, puis `task ci:fast` avant toute publication autorisée.
  Les suites Redis/PostgreSQL réelles s'ajoutent à ces gates sans services.
- [ ] Exécuter aussi le contrôle host propre demandé par le frontend : depuis
  `apps/web`, `pnpm exec tsc --noEmit --incremental false`, sans réutiliser un
  cache incrémental. Les tests de noms accessibles couvrent anglais et français
  directement, avec parité des clés sur toutes les langues.
- [ ] Ajouter les marqueurs des nouveaux tests au vrai job CI ; aucune nouvelle
  logique shell de test inline dans le workflow. Les tâches frontend restent
  l'autorité de l'environnement et de la couverture.
- [ ] Vérifier docs/ADRs/registre de settings/clés/exports. `AGENTS.md` ne se
  modifie jamais à la main ; les nouveaux settings ont lecteurs et exemples.
  Vérifier aussi les registres de consultations/surfaces, appels directs aux
  clients et portes de dépenses Google/LLM si leurs call sites changent.
  Aucun relèvement des ratchets pour absorber une complexité ajoutée.
- [ ] Exécuter `task lint:docs:preview` tant que les fichiers ne sont pas stagés ;
  séparer explicitement les anomalies héritées et celles du lot.
- [ ] Qualifier la séquence backend additif puis frontend, le rollback inverse
  et les miss sûrs de cache pendant coexistence de versions. Les contrôles
  d'accès ne sont déclarés livrés qu'une fois tous les workers qualifiés.
- [ ] Mesurer dans Docker dev cache froid/chaud, proxy de flux, plusieurs workers,
  déconnexion et reprise. Publier compteurs de tentatives/coûts, volumes Redis,
  mémoire et délais à charge comparable ; pas de promesse de gain non mesuré.

**Résultat livré :** dossier de qualification ; aucune conclusion « corrigé »
avant succès des flux critiques et divulgation des limites de validation.

## Lot 12 — confirmation et correction réseau, périmètre distinct

**Entrée :** mesures DNS/TCP/TLS datées, changements d'application qualifiés.
**Sortie :** segment responsable établi ou hypothèse explicitement non résolue,
proposition de correction concrète et mesure comparative reproductible.

- [ ] Relire la configuration réseau effective de la cible et les logs de
  résolution/connexion sans exposer de secrets. Ne pas déduire cette cible de
  la configuration Docker locale.
- [ ] Faire, dans le périmètre autorisé, un petit échantillon non authentifié par
  endpoint représentatif, sans retries, distinguant résolution, connexion,
  TLS et réponse ; comparer hôte/conteneur et adresses si pertinent.
- [ ] Tester les changements envisagés dans un environnement contrôlé. Ne pas
  désactiver IPv6, changer DNS/route ou relancer la production sur supposition.
- [ ] Une intervention réseau ou un déploiement de production requiert son
  autorisation propre ; présenter la correction et son rollback avant exécution.

Ce lot ne bloque pas l'implémentation locale des gains applicatifs. Il empêche
seulement d'attribuer au code une réparation non démontrée du réseau de prod.

## Critères de fin et restitution

- [ ] Les critères d'acceptation de la spec sont prouvés par assertions et flux
  réels pertinents ; inventaire des tests passés/échoués/skippés et environnements
  non vérifiés communiqué sans amalgamer les résultats.
- [ ] Le catalogue du tour, les noms/outils/ressources, HITL et consentements
  restent fonctionnellement cohérents sur tous les chemins déclarés.
- [ ] Les coûts restent attribués aux tentatives physiques, y compris échecs et
  annulations ; aucune issue inconnue convertie en succès ou retry implicite.
- [ ] Aucun changement de modèles, de configuration de production ou de données
  métier n'a été glissé dans ce chantier de latence.
- [ ] Relire inline le diff final et les changements concurrents, documenter
  risques résiduels et protocole de rollback avant livraison autorisée.
