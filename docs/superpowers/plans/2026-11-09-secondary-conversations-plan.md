# Discussions annexes — Implementation Plan

> **Pour l'exécution :** travailler lot par lot, strictement inline, sans sous-agent. Utiliser le cycle TDD décrit ici. Aucun commit, staging, branche, push ou déploiement sans demande de l'utilisateur. Ces contraintes remplacent les recommandations génériques de délégation et de Git des skills.

**Goal:** proposer plusieurs discussions LIA avec un historique propre, une Principale permanente pour les automatismes, et des réglages/apprentissages communs au compte.

**Architecture:** étendre le domaine conversations ; résoudre une cible immuable à l'entrée du tour ; séparer identité métier et runtime réinitialisable. Réutiliser les pipelines, extracteurs, registres, contrôles de dépenses et composants existants. Le nettoyage multi-stockages devient explicite et reprenable.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Redis, LangGraph, Next.js/React/TypeScript, pytest, Vitest, Playwright ; versions et dépendances du dépôt, sans nouvelle bibliothèque prévue.

**Spec:** [analyse, décisions, risques et matrice T01–T40](2026-11-09-secondary-conversations-analysis.md) et [contre-revue des trois arbitrages](2026-11-09-secondary-conversations-counter-review.md). Lire les deux avant le plan. Les fichiers marqués « créer » sont des propositions ; les autres sont des points d'ancrage vérifiés. Aucun lot ci-dessous n'a été implémenté.

Date : 2026-11-09. Statut : **prêt pour revue et exécution TDD, activation interdite avant les portes de qualification**.

## Global Constraints

- Principale jamais supprimable ; les UUID existants et checkpoints initiaux sont conservés.
- Aucun état de sélection global au compte ; `/me` et absence de cible signifient Principale.
- Historique/contexte d'outils/HITL isolés, apprentissages/préférences/quotas communs ; six familles d'extraction humaines inchangées dans leur admission.
- Un tour de graphe actif par compte dans le périmètre initial : choix explicite, pas une garantie générale de l'existant. Admission SQL durable, Redis pour transport/présence ; aucune transaction conservée pendant un appel fournisseur ou une attente humaine.
- Aucun plafond du nombre total d'annexes. Liste proposée à 30 éléments par défaut/100 maximum par page, titre borné par la capacité actuelle de 500 caractères ; bornes techniques publiées, constantes/settings/templates cohérents.
- Rotation runtime ET clôture transactionnelle de ses écritures. La rotation seule ne prouve pas une purge ; un `done`, un timeout et un TTL ne prouvent pas l'arrêt d'un producteur.
- Aucun appel LLM pour gérer la liste ou les titres ; aucune remise à zéro des dépenses sur reset/delete.
- Préserver les uploads partagés, fichiers générés, réponses conservées et registres selon leur politique ; ne pas transformer « supprimer la discussion » en « tout oublier ».
- Interfaces et documentation technique en anglais ; UX et FAQ dans les six langues. Les présents documents de travail datés sont en français conformément à l'exception du dépôt.
- Ne pas augmenter les baselines de taille/complexité/cycles/typing/a11y/hooks ; pas de suppression de règle ou de diagnostic pour faire passer un gate.
- Runtime frontend dans Docker selon le mode de travail du projet ; tests unitaires/statique possibles sur l'hôte. Tests SQL/Redis sur cibles jetables exclusivement.

## Review Focus

1. Deux cibles distinctes mais même compte, y compris l'UUID historique de Principale égal à celui du compte : tester explicitement purge et admission dans les lots 2 et 5.
2. Une réponse réseau perdue après commit, puis retry ou onglet fermé : opération idempotente et réconciliation, lots 1, 5 et 8.
3. Un vieux producteur, callback, checkpoint ou flush revient après reset/switch : cloisonnement runtime/révision et absence d'effet tardif, lots 2, 3, 5 et 8.
4. Un upload sert deux historiques, ou est attaché pendant la suppression : usage explicite et décision atomique, lots 4 et 5.
5. Live en veille et confirmations dans une annexe pendant une notification principale : cible immuable et navigation indépendante, lots 6, 7 et 9.

Chaque lot commence par son test comportemental rouge, vérifie que l'échec vient du contrat attendu, apporte le minimum cohérent puis repasse au vert. Une erreur d'import ou une fixture invalide n'est pas une preuve RED. Les garde-fous de migration sont prouvés par des écritures SQL, les claims par deux acteurs, les interactions par leurs effets et leur focus, pas seulement par des snapshots.

## Ordre et portes de passage

Ordre : **0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11**. Les sous-lots sont des unités révisables, pas une instruction de paralléliser. Le drapeau de création reste désactivé jusqu'au lot 11. Le code compatible doit néanmoins savoir lire les lignes existantes quand ce drapeau est coupé.

| Lot | Livrable testable |
|---|---|
| 0 | Corpus de référence et recensement des identités/scopes. |
| 1 | Schéma, Principale explicite, création idempotente, liste paginée bornée sans plafond total. |
| 2 | Runtime isolé et identité métier transmise à tous les producteurs. |
| 3 | Entrées de chat, admission compte, reprises et destinations principales. |
| 4 | Usages de fichiers et détermination atomique des uploads orphelins. |
| 5 | Reset/delete reprenables et suppression complète du compte. |
| 6 | Lectures transversales, journal, apprentissages et provenance. |
| 7 | Live et relais vocaux liés à leur discussion d'origine. |
| 8 | Transport/état frontend isolés et synchronisation multi-cibles. |
| 9 | Badge, gestionnaire, création/suppression/reset et navigation mobile/World. |
| 10 | Comptabilité, observabilité et guards transverses consolidés. |
| 11 | Qualification complète, documentation et protocole d'activation. |

## Lot 0 — Fixer les preuves et frontières

**Fichiers :** réutiliser les tests recensés dans l'analyse ; créer `apps/api/tests/fixtures/conversation_cases.py`, `apps/api/tests/unit/domains/conversations/test_scope_contract.py` et `apps/web/src/hooks/__tests__/conversation-cases.ts` seulement pour les données partagées nécessaires. Le corpus ne remplace pas les fixtures PostgreSQL/Redis existantes.

**Interfaces :** `ConversationCases` nomme les comptes U/V, P/A/B et leurs UUID distincts ; builders strictement typés, overrides précis. Aucun `Any`, double cast ou mock qui impose une cible indépendamment de l'entrée testée.

- [ ] Relire les instructions applicables, les trois documents et les fichiers concernés ; inventorier les modifications concurrentes en lecture seule, sans opération Git de mutation.
- [ ] Relever les ratchets actuels ; conserver les suites 57/90 et les 33 tests complémentaires comme preuves datées de l'existant, les 23 sondes comme preuves de conception, sans les traiter comme validation de la fonctionnalité.
- [ ] Recenser par AST les lecteurs de `Conversation`, `ConversationMessage`, `configurable.thread_id`, `__parent_thread_id`, les appels à `conversation_uuid`, les résolveurs par utilisateur et les writers de runtime. Classer chaque usage : identité métier, runtime, compte ou fournisseur.
- [ ] Écrire des cas qui reproduisent S01–S03 via les fonctions publiques effectives : deux signaux dans une transaction, reset annexe touchant la clé principale. Les tests nouveaux doivent échouer avant correction ; ne pas les neutraliser par des IDs identiques.
- [ ] Documenter dans le test de scope les lecteurs déjà corrects : activité compte, source proactive, provenance et export. Le test ne demande pas de transformer ces lecteurs en lecteurs courants.
- [ ] Caractériser R05 et R17 par leurs vraies portes : commit interne de `delete_all_for_user`, timeout de `await_run_id_tasks` avec enfant vivant. Les tests du shutdown global ne remplacent pas ceux du drainage d'un run.
- [ ] Compléter les 40 sites/24 modules du recensement AST ciblé par les subscripts, namespaces, méthodes synchrones et les paires producteurs/consommateurs. Lire les dépendances installées aux portes saver/Store avant de coder l'adaptation.

**Sortie :** chaque dépendance d'identité possède un propriétaire ; aucune décision de scope n'est laissée à un remplacement textuel global.

## Lot 1 — Modèle, résolution de Principale et catalogue de discussions

### 1A. Schéma et contrat d'identité

**Modifier :** `apps/api/src/domains/conversations/models.py`, `repository.py`, `schemas.py`, `apps/api/src/infrastructure/database/registry.py`, `apps/api/src/domains/users/user_data_map.py`.

**Créer :** une migration sous `apps/api/alembic/versions/` depuis la tête effective ; `apps/api/src/domains/shared/conversation_target.py` pour les types communs ; `apps/api/src/domains/conversations/catalogue_repository.py` pour les requêtes du catalogue.

**Interfaces proposées :**

```python
class ConversationKind(str, Enum):
    MAIN = "main"
    SECONDARY = "secondary"

@dataclass(frozen=True, slots=True)
class ConversationRef:
    owner_id: UUID
    id: UUID
    kind: ConversationKind
    revision: int
    runtime_id: UUID
```

`ConversationCatalogueRepository.get_primary(owner_id: UUID) -> Conversation | None` et `get_owned(owner_id: UUID, conversation_id: UUID) -> Conversation | None` remplacent les choix implicites. Les méthodes prennent leur session dans le constructeur, selon le pattern repository.

- [ ] RED PostgreSQL T01/T05 : deux annexes autorisées, une seule Principale, titre annexe non blanc, propriétaire étranger refusé ; vieilles données et UUID préservés.
- [ ] Ajouter kind/revision/runtime_id et l'unicité partielle ; backfill runtime_id depuis id. Supprimer l'ancienne unicité seulement dans cette migration contrôlée.
- [ ] Préserver la réactivation de l'ancienne Principale ; rendre impossible celle d'une annexe supprimée. Définir une contrainte de titre cohérente avec la validation applicative.
- [ ] Tester upgrade, downgrade sur zéro annexe et refus explicite du downgrade quand il détruirait la cardinalité. Pas de fusion automatique.
- [ ] Déclarer tout nouveau modèle au registre unique et sa politique de données ; ne pas ajouter une deuxième liste de modèles dans Alembic ou le lifespan.

**Test nouveau :** `apps/api/tests/integration/domains/conversations/test_multi_conversation_schema.py`. **Vérification :** test ciblé sur PostgreSQL jetable puis `task db:migrate:replay-check` après stabilisation du schéma complet des lots 4/5.

### 1B. Création et liste

**Créer :** `apps/api/src/domains/conversations/catalogue_service.py`, `catalogue_router.py`, `apps/api/src/core/config/conversations.py`. **Modifier :** `core/config/__init__.py`, `core/constants.py`, `core/exceptions.py`, les templates env pertinents, `domains/conversations/router.py` et `apps/api/src/api/v1/routes.py::get_client_config`, propriétaire vérifié de la publication de configuration. Le frontend la lit par `apps/web/src/hooks/useAppConfig.ts`.

**Interfaces :** `ensure_primary(owner_id: UUID) -> ConversationRef`, `create_secondary(owner_id: UUID, request: ConversationCreateRequest) -> ConversationCreateResult`, `list_owned(owner_id: UUID, page: ConversationPageRequest) -> ConversationPageResponse`. Requête de création = `title` + `request_id: UUID`; réponse distingue création et replay.

- [ ] RED T02–T04/T39 : GET sans effet, création annexe assurant une Principale, retries identiques, conflits de payload, plusieurs pages et créations dépassant l'ancien plafond proposé sans refus arbitraire.
- [ ] Implémenter le verrou propriétaire court pour assurer Principale/créer une annexe et respecter l'idempotence persistée. Le reçu minimal de création (compte, request_id, empreinte, UUID résultat) survit au retrait de l'annexe jusqu'à la suppression du compte ; un retry après retrait répond « cible retirée », jamais une nouvelle création. Déclarer le modèle et sa rétention, sans texte du titre dans le reçu.
- [ ] Calculer le total exact dans la requête filtrée de liste, pas depuis la page ; aucune lecture de messages/checkpoints pour lister. Implémenter les seules bornes de titre/page et leur publication depuis les mêmes constantes/settings. Relier le mixin à `Settings`, tester default/override et parité env. Aucun setting de nombre maximum d'annexes.
- [ ] Enregistrer les routes statiques avant les routes par ID ; garder `/me` compatible et faire du cache `conv:user` un cache explicite de Principale.
- [ ] Test de drapeau : création refusée quand off ; lecture, reset et suppression des données déjà présentes restent accessibles.

**Tests nouveaux :** `apps/api/tests/unit/domains/conversations/test_catalogue_service.py`, `apps/api/tests/integration/domains/conversations/test_catalogue_routes.py`, `test_creation_races.py` dans le même dossier integration. **Sortie :** aucune sélection navigateur ne change la résolution principale.

## Lot 2 — Séparer identité métier et runtime réinitialisable

**Modifier :** `domains/agents/context/runtime_context.py`, `domains/agents/context/runtime_context_builder.py`, `domains/agents/services/conversation_orchestrator.py`, `domains/agents/services/orchestration/service.py`, `domains/conversations/service.py`, `domains/agents/context/manager.py`, `domains/agents/context/access.py`, `domains/agents/tools/runtime_helpers.py`, factories et wrappers de `domains/conversations/checkpointer.py`, `instrumented_checkpointer.py`, `domains/agents/context/store.py`.

**Créer :** `apps/api/src/domains/conversations/runtime_identity.py` pour la résolution et `runtime_persistence.py` pour le contrat de clôture des écritures ; `apps/api/tests/unit/domains/conversations/test_runtime_identity.py` ; `apps/api/tests/unit/test_conversation_identity_guard.py`. Garder les adaptateurs natifs et l'ownership des pools aux portes existantes, sans dépendance du domaine conversations sur agents.

**Interface :** `ConversationRef` est la source du runtime ; `LiaRuntimeContext` garde `conversation_id` métier et reçoit `conversation_revision` et `runtime_id`. `checkpoint_config(target: ConversationRef) -> RunnableConfig` construit le strict minimum de plomberie. Les paramètres `run_id` et identité de session d'auth ne sont pas remplacés par runtime_id.

- [ ] RED T06/T14/T22 : deux historiques et deux contextes outils indépendants ; une réinitialisation change le runtime sans changer les FK de provenance ; ancienne configuration préservée au premier tour après migration.
- [ ] Faire passer le même objet cible dans chargement d'état, construction du graph config, compaction, estimation du contexte et résolutions d'outils. Le `thread_id` LangGraph reçoit runtime_id ; les métadonnées métier gardent conversation_id.
- [ ] Migrer les lecteurs qui convertissent aujourd'hui un thread en conversation : `domains/attachments/thread_id.py`, producteurs image/document/page/browser/skill, extractions, appels de comptabilité et contexte de sous-boucles. Un namespace de sous-agent interne conserve le parent runtime pour le travail, le parent métier pour les fichiers et actes.
- [ ] Transmettre le parent runtime explicitement pour tout thread enfant non UUID ; enregistrer les seuls namespaces/threads enfants réellement persistés dans son inventaire de purge. Ne pas inférer le parent depuis une chaîne ni ajouter un checkpointer aux sous-agents qui n'en ont pas.
- [ ] Retirer les fallbacks qui masqueraient l'absence d'identité métier sur un chemin censé la fournir. Conserver l'absence légitime de conversation pour un producteur autonome qui la déclare.
- [ ] Garder le contrat du registre : `agent_decisions.thread_id` continue à nommer la discussion métier. Ne pas remplacer aveuglément les occurrences de `thread_id` dans les registres/exports.
- [ ] Prouver la garde avec une fixture ajoutant un nouveau lecteur illégitime. Le registre AST distingue les usages de plomberie autorisés des conversions vers une FK.
- [ ] RED T33/T36 : reproduire R19–R23 avec le vrai adaptateur de LIA. Validation `FOR SHARE` du runtime courant et `aput`/`aput_writes` sur la MÊME connexion/transaction ; reset sous verrou incompatible. Tester les deux ordres, rollback, blobs, pending writes, round-trip, HITL et sous-graphes. Aucun état de requête sur le singleton.
- [ ] Faire passer tous les writers de contextes runtime par la même clôture SQL. Déclarer leurs namespaces et `index=False`, conserver les lectures exactes ; ne pas mettre les embeddings du Store global sous transaction. Tester batch mixte, méthode synchrone, heartbeat indépendant, fermeture/attente des tâches de batching et absence de régression du pool.
- [ ] Faire refuser une génération retirée par un résultat/exception interne typé, sans retry modèle ; garder métriques et logs factuels. La purge continue d'utiliser les méthodes natives. Aucun trigger ni fork de SQL fournisseur.

**Tests additionnels nouveaux :** `apps/api/tests/integration/domains/conversations/test_runtime_checkpoint_isolation.py`, `test_runtime_write_fence.py` avec vrai saver/Store et deux connexions ; étendre les tests existants des fichiers produits, pools et round-trips. Mesurer `pg_stat_activity` pendant le modèle/embedding simulé lent.

**Sortie :** aucun fichier, acte ou token summary n'est rattaché au UUID d'un runtime retiré à la place de la discussion.

## Lot 3 — Entrées de chat, admission et destinations autonomes

### 3A. Cible explicite à toutes les portes d'un run

**Modifier :** `domains/agents/api/schemas.py`, `router.py`, `service.py`, `background_runner.py`, `channel_gateway.py`, `infrastructure/cache/conversation_cache.py`, `infrastructure/scheduler/out_of_turn_run.py`.

**Créer :** `apps/api/src/domains/agents/api/conversation_target.py`, uniquement si le résolveur du lot 1 n'offre pas déjà la composition authentification+cible adaptée à ces routes ; cette composition ne possède pas une seconde règle de sélection.

**Interfaces :** `conversation_id: UUID | None` et `conversation_revision: int | None` dans `ChatRequest` et le contrat interne `StreamRequest`. `resolve_target(owner_id, requested_id, expected_revision) -> ConversationRef` signifie Principale si absent. Le nouveau client ciblé fournit la révision affichée, y compris pour upload/Live ; un envoi préparé avant reset ne rejoint pas automatiquement le nouveau contexte. `AgentService` reçoit la cible résolue une fois ; l'alias historique absent/absent reste Principale.

- [ ] RED T05/T06/T08 : chat, active run, pending HITL, cancel et reattach portent la même cible ; stream foreign ou stream d'une autre discussion du compte refusé.
- [ ] Vérifier propriété/révision avant d'ouvrir SSE ; ne pas garder une session d'auth ou de résolution sur la durée du flux.
- [ ] Faire porter la cible et le run dans tous les résultats qui doivent être réconciliés par le front, y compris le premier tour créant Principale.
- [ ] Ajouter le curseur composite des messages tout en acceptant le `before` historique sur l'alias ; test de plusieurs messages au même timestamp et ordre final sur la PK.
- [ ] Remplacer les incréments de stats lus/modifiés en Python par une mise à jour SQL atomique et tester notification+réponse concurrentes.

**Tests nouveaux :** `apps/api/tests/integration/domains/agents/api/test_chat_conversation_target.py`, `apps/api/tests/unit/domains/agents/api/test_conversation_resume.py` ; étendre `test_messages_pagination.py` et `test_conversation_orchestrator.py` existants.

### 3B. Admission compte et routage principal

**Modifier :** `infrastructure/streaming/run_stream_broker.py`, ses finalizers/leases, `infrastructure/async_utils.py` et les wrappers des runners qui prennent actuellement leur propre lease. **Créer :** `apps/api/src/domains/conversations/execution_models.py`, `execution_repository.py` et `apps/api/src/infrastructure/streaming/run_admission.py` pour la composition. Migration, registre unique et user-data map accompagnent ce modèle.

**Interface :** `RunAdmission` interne immuable contient compte, discussion, runtime, révision, run/stream, worker boot identity et owner token. `admit_run(target, run_id, stream_id) -> RunAdmission | RunBusy` acquiert l'autorité SQL ; `RunBusy` indique la discussion possédée à rejoindre. Le modèle d'activité distingue `graph`/`live` et phases `running`, `draining`, `recovering`, `closed` ; index unique partiel compte sur les trois premières pour `graph`. La réservation Live du lot 7 protège sa cible sans occuper le slot graphe de ses délégations. Le client HTTP ne fournit pas une admission ; Redis ne la recrée pas par déduction.

- [ ] RED T07/T35 : premier message simultané, deux discussions/deux workers, expiration Redis, ancien finalizer, récupération et arrêt inconnu ; aucune admission transférée sur simple TTL et aucun démarrage payant sans autorité sûre.
- [ ] Admission et lifecycle prennent le même ordre de verrous courts décrit dans la contre-revue. La fonction est appelée une fois et transmise aux runners, sans double claim ; reprise conditionnée par run/token. Un échec du miroir Redis ne libère pas l'autorité SQL.
- [ ] Séparer fin du flux, drainage du graphe et extractions différées. Garder les tâches vivantes indexées après timeout ; une extraction tardive reste sous garde source. La clôture du run exige arrêt/join du producteur et des writers de travail, sans confondre travail indépendant et graphe.
- [ ] Relâcher l'activité à une pause HITL seulement après suspension effective, en gardant la question attachée au runtime. Cancel sans accusé d'arrêt ou crash inconnu → recovering ; aucune relance d'un effet fournisseur inconnu. Récupération bornée et runbook explicite, pas un lease qui expire silencieusement.
- [ ] Migrer explicitement les producteurs Principale : notification, reminder_notification, discussion_persistence, discussion_attention, discussion_runner, workboard_runner, phone_relay_runner, voice_delegation, canaux Telegram, self_call_context et lecteurs radio qui résolvent une conversation unique. Vérifier chaque import/type, pas le seul nom de méthode.
- [ ] Déclarer les nouvelles clés dans `key_families.py` avec leur forme/identité ; séparer la purge d'un runtime du verrou d'admission compte.
- [ ] Pour chaque runner autonome, éprouver le contrat d'occupation/report sans nouvelle file implicite ni faux succès. Notifications qui archivent seulement hors admission graphe. Typer `CurrentPrimaryPublication` et `PinnedRunPublication`, test T37 : un ancien résultat ne peut pas se rebinder en notification indépendante.

**Tests nouveaux :** `apps/api/tests/integration/infrastructure/streaming/test_account_run_admission.py`, `test_run_lifecycle_races.py`, PostgreSQL et Redis jetables, deux workers ; tests unitaires du drainage par run et des états de récupération. **Sortie :** T12/T24/T35/T37 verts ; sélectionner une annexe ne détourne aucune sortie autonome.

## Lot 4 — Rattacher les usages de fichiers

**Modifier :** `domains/attachments/models.py`, `schemas.py`, `router.py`, `service.py`, `domains/agents/api/archive_first.py`, chemin d'archive finale, `infrastructure/scheduler/attachment_cleanup.py`.

**Créer :** `apps/api/src/domains/attachments/conversation_usage.py` et une migration de relation d'usage. Enregistrer le modèle et sa politique de données par les portes uniques.

**Interfaces :** `link_usage(owner_id: UUID, attachment_id: UUID, target: ConversationRef) -> None` idempotent ; `release_conversation_usages(target: ConversationRef) -> tuple[UUID, ...]` renvoie seulement les uploads dont la transition vers suppression a été acquise. Les méthodes travaillent sur une session courte appartenant au service appelant.

- [ ] RED T19 : upload A seulement, partagé A/B, upload non attribuable, draft non envoyé, fichier généré et kept, propriétaire étranger, attachement concurrent à la libération.
- [ ] Créer les liens lors de l'usage accepté, y compris si l'archive précoce est reprise plus tard. Contrôler origine, état et propriétaire ; conserver la provenance de génération indépendante.
- [ ] Backfiller depuis les références de messages réellement décodées par les helpers existants. Rapporter les uploads sans preuve, sans inventer une origine ni les effacer.
- [ ] Implémenter un verrou/transition atomique sur le fichier lors du dernier usage ; le nettoyage périodique lit la même décision, pas une règle parallèle.
- [ ] Porter la cible dans le formulaire d'upload du nouveau client ; la compatibilité d'un client ancien n'attribue pas automatiquement son fichier à une annexe active ailleurs.
- [ ] RED T40 : upload en vol, temporaire écrit avant crash, refus de publication sur ancienne révision. Capturer identité/chemin avant effet filesystem et conserver l'intention de nettoyage jusqu'au résultat. Ne pas supprimer un dossier compte, ne pas réutiliser un chemin, ne pas prolonger implicitement l'expiration d'un upload partagé.

**Test nouveau :** `apps/api/tests/integration/domains/attachments/test_conversation_usage.py`. **Sortie :** aucun fichier partagé ou généré n'est supprimé par le retrait d'une discussion.

## Lot 5 — Reset, suppression et nettoyage reprenable

### 5A. Lifecycle métier et protocole de nettoyage

**Créer :** `apps/api/src/domains/conversations/lifecycle.py`, `cleanup_contracts.py`, `cleanup_repository.py`, `cleanup_models.py` ; `apps/api/src/infrastructure/scheduler/conversation_cleanup.py`. **Modifier :** service/router/schemas conversations, `reset_purge.py`, key families, startup schedulers, registre des modèles, configuration et constantes du lot 1.

**Interfaces :**

```python
async def request_reset(
    owner_id: UUID, conversation_id: UUID, *,
    operation_id: UUID, expected_revision: int,
) -> ConversationOperationResponse: ...

async def request_delete(
    owner_id: UUID, conversation_id: UUID, *,
    operation_id: UUID, expected_revision: int,
) -> ConversationOperationResponse: ...
```

Ces signatures sont celles du service recevant sa session en constructeur. La responsabilité d'intégration expose un `RuntimeCleanupPort` nommé avec `purge_checkpoint`, `purge_tool_context`, `purge_pending` et résultats typés, afin que le domaine conversations n'importe pas de nouveaux détails du domaine agents. Le runner compose ces ports et les services fichiers/Redis.

- [ ] RED T17/T18/T34/T38 : suppression Principale interdite, titre conservé au reset, activité durable/Live refusée, HITL abandonné sans effet, révision périmée, replay même operation_id avant contrôle de révision, empreinte différente refusée, rollback avant commit.
- [ ] Dans la transaction métier unique : réclamer l'opération, capturer les cibles immuables, publier une nouvelle révision/runtime au reset ou retirer la discussion au delete, supprimer messages/compteurs de vue/usages. Conserver totaux facturés et provenance détachable. Aucun appel au `delete_all_for_user` qui committe ; séparer opérations repository, intention et I/O. Injecter un échec après chaque étape avant le seul commit.
- [ ] Armer les changements pour l'après-commit. Le commit inconnu se résout en relisant l'opération ; aucun retry automatique d'une mutation sans identité.
- [ ] Hors transaction, exécuter les purges exactes avec claim durable : owner token, expiration, fence, phases idempotentes, reprises et erreurs factuelles. États pending/running/retry_wait/needs_attention/succeeded et transitions de la contre-revue. Un ancien owner ne clôture pas l'opération d'un autre ni n'enchaîne une nouvelle phase.
- [ ] Ajouter au scheduler leader le rattrapage des opérations incomplètes, avec constante de job, jitter et bornes settings ; aucune boucle infinie ni session conservée pendant les I/O.
- [ ] Faire perdre à un ancien runtime toute autorisation d'archiver, publier, confirmer, apprendre ou recréer son stockage : clôtures SQL lot 2, portes Redis owner/génération, callbacks locaux invalidés. Tester l'ancien producteur après purge et après reprise d'un claim ; `succeeded` exige toutes les phases et clôtures effectives, jamais un TTL ou done.
- [ ] Retirer du reset les purges par substring compte et l'invalidation globale LLM. Déclarer les familles/identités réellement purgées, dont skill proposals/browser sessions si elles portent des références de la cible.
- [ ] L'API distingue `logical_applied`, nouvelle révision et nettoyage terminal. La vue neuve peut servir après commit ; aucune résurrection sur panne de nettoyage. L'alias ancien réutilise ce service, n'émet success qu'à l'achèvement et, à sa borne, fournit une erreur typée de réconciliation avec operation_id. Aucun retry destructif aveugle.
- [ ] Une opération incomplète reste récupérable/alertée, sans expiration qui effacerait sa dette ; rétention bornée du tombstone après succès seulement. Un retry tardif sur ancienne expected_revision ne détruit pas de nouveaux messages.

**Tests nouveaux :** `apps/api/tests/integration/domains/conversations/test_lifecycle.py`, `test_cleanup_recovery.py`, `apps/api/tests/unit/domains/conversations/test_cleanup_policy.py`. Tests PostgreSQL/Redis/Store réels pour transitions, doubles de filesystem ciblés pour pannes injectées ; au moins une preuve sur fichiers temporaires réels.

### 5B. Suppression compte et rétention

**Modifier :** `domains/users/account_deletion_service.py`, `user_data_map.py`, `domains/account_export/builder.py`, déclarations de cleanup du lot 5A.

- [ ] RED T26 : compte avec P/A/B et ancien runtime déjà retiré ; chaque cible purgée, second compte préservé, billing retained et registres conformes.
- [ ] Remplacer `_load_conversation` singleton par un inventaire borné de toutes les cibles. Capturer les identifiants nécessaires avant la disparition des lignes de conversation.
- [ ] Éviter que CASCADE ne supprime le travail de nettoyage encore nécessaire. Déclarer la rétention opérationnelle sans contenu : purge après résultat explicite, aucune expiration des échecs. Fermer les admissions et les writers du compte avant de conclure son nettoyage ; les reçus de création ne survivent pas au compte.
- [ ] Vérifier export de toutes les discussions, références SET NULL, tombstones et absence de message supprimé reconstitué à partir d'un cache.

**Sortie lot 5 :** la suppression ciblée ne touche ni les autres discussions ni leurs états de travail ; l'effacement global du compte n'oublie aucune annexe.

## Lot 6 — Lecteurs, mémoire, journal et provenance

**Modifier :** `domains/journals/consolidation_service.py`, `domains/agents/nodes/post_response_extractions.py`, `domains/agents/context/extraction_revision.py`, extracteurs existants des six familles, `domains/bookmarks/repository.py`, `domains/agents/application/bookmark_keep_scope.py`, `domains/conversations/message_readers.py`, `domains/shared/provenance_repository.py`, `infrastructure/discussion_invalidation.py` et sources/attention proactives concernées.

**Créer si nécessaire :** `apps/api/src/domains/conversations/reader_scopes.py` pour le périmètre courant/principal/compte, sans confondre la visibilité déjà déclarée ; `apps/api/src/domains/shared/conversation_source.py` pour la référence de source immuable et le port de validité.

**Interfaces :** `ConversationSourceRef(owner_id, conversation_id, revision, run_id, message_id)` ; `source_is_current(ref) -> bool` lu au moment de l'écriture d'un résultat différé, à côté de la révision du consentement compte. Les éléments optionnels réellement absents ont un type explicite, pas une chaîne `unknown` utilisée comme UUID.

Le port de validité s'exécute dans la session de l'écriture : verrou de ligne ou condition SQL révision+état, sans réseau avant commit. Tester la course où le reset survient entre un premier check et le retour du modèle ; un booléen mis en cache avant le wait ne vaut pas autorisation d'écrire.

- [ ] RED T13/T14 : six extractions ordinaires sur P et A, consentement changé, reset A, traitement partiellement payé ; source retirée n'écrit plus, coût reste rattaché au run, B n'est pas invalidée.
- [ ] Réutiliser les politiques propres aux six familles : le helper `ExtractionKind` actuel ne déclare que mémoire/journal/psyché. Garder la variante de révision pour les autres sources, sans inventer des valeurs supportées. Vérifier source/consentement dans la transaction finale selon l'ordre de verrous commun.
- [ ] Remplacer les deux lectures singleton du journal par un flux/ensemble compte borné globalement ; agréger les rythmes, groupement du dialogue par discussion, tri stable et coupe publiée.
- [ ] RED T15/T16 : sujets distincts, budgets saturés, lecture indisponible, réponse annexe ne répondant pas à l'ouverture principale. Réutiliser `_reply_to` existant et prouver son maintien.
- [ ] Corriger la résolution implicite du bookmark avec la conversation du runtime ; la commande « garder cette réponse » ne lit plus `latest` au compte. Vérifier les autres actions de carte par leur source, pas seulement leur propriétaire.
- [ ] Déclarer et tester les scopes de tous les lecteurs ; garder les lecteurs d'activité/export déjà transversaux. Ajouter une fixture AST réellement fautive à la garde.
- [ ] Retirer précisément les supports des sources supprimées et republier les contextes dérivés avec le fencing existant. Conserver apprentissages canoniques et derniers états valides non dépendants de la source retirée.

**Tests nouveaux :** `apps/api/tests/integration/domains/journals/test_multi_conversation_sources.py`, `apps/api/tests/unit/domains/agents/nodes/test_secondary_extraction_parity.py`, `apps/api/tests/unit/domains/bookmarks/test_current_conversation_keep.py`, `apps/api/tests/unit/test_conversation_reader_scopes_guard.py`.

**Sortie :** les annexes apprennent et sont connues de LIA sans mélanger les dialogues bruts ni doubler leurs budgets.

## Lot 7 — Live, veille et relais

**Modifier :** `domains/live/schemas.py`, `service.py`, `session_store.py`, `session_end.py`, `standby.py`, les délégations et résumés de `domains/voice_sessions/`, `infrastructure/scheduler/out_of_turn_run.py`, les appels frontend du Live et `apps/web/src/stores/liveStore.ts`.

**Interface :** le start Live reçoit cible et révision affichée (absence historique → Principale). La réservation d'activité SQL porte la cible avant l'appel fournisseur ; le record Redis conserve `lia_conversation_id` et `lia_conversation_revision`, avec ses identifiants fournisseur distincts. Le relais transmet cette cible par `StreamRequest`, sans la rebinder à une révision nouvelle.

- [ ] RED T23 : start A→view B→standby→wake→close, mode direct et délégué, fin déclenchée à distance, reconnect et coûts. Toutes les archives restent sur A.
- [ ] RED start/reset dans les deux ordres : réservation Live durable sous autorité commune avant appel fournisseur, ouverture refusée libérée après compensation, résultat inconnu en récupération. La veille conserve le droit d'occupation, la clôture ET le relay terminé le libèrent. Ne pas lire une seule clé Redis comme preuve d'absence.
- [ ] Ajouter le round-trip JSON exact de la cible et une compatibilité bornée des anciens records sans cible : résolution Principale une seule fois, puis snapshot conservé ; jamais la sélection navigateur courante.
- [ ] Contrôler les sessions Live dans la décision de reset/delete, y compris la veille. Fin et relay terminés doivent précéder le retrait de leur cible.
- [ ] Garder le host/microphone au niveau compte ; un changement de workspace ne ferme pas la session. Le bandeau nomme la discussion d'origine et permet de la rejoindre.
- [ ] Vérifier T24 sur téléphonie/Telegram : callback principal, attribution de l'acte initiateur annexe et confirmation périmée refusée. Ne pas rebinder des webhooks à une vue locale.

**Tests nouveaux :** `apps/api/tests/unit/domains/live/test_conversation_binding.py`, `apps/api/tests/integration/domains/live/test_conversation_relay.py`, `apps/web/e2e/smoke/chat-secondary-live.spec.ts`.

## Lot 8 — Transport frontend et synchronisation

**Modifier :** `apps/web/src/hooks/useConversation.ts`, `useChat.ts`, `useChatServerSync.ts`, `useConversationSync.ts`, `useNotifications.ts`, `useInputDraft.ts`, `apps/web/src/lib/api/chat.ts`, `lib/sse-handlers/index.ts`, `lib/chat-sync.ts`, `lib/chat-merge.ts`, `reducers/chat-reducer.ts`, types chat/conversation. Backend : `domains/conversations/sync_signal.py`.

**Créer :** `apps/web/src/hooks/useConversationSelection.ts` et `apps/web/src/types/conversation.ts` si la définition n'est pas déjà centralisée au moment de l'exécution.

**Interfaces :** `ConversationSelection` distingue `{kind: 'primary', id: string | null}` d'une annexe à UUID connu. `ConversationSignal` devient un objet discriminé avec type, conversationId et revision. Le client de stream est construit par contrôleur avec target et dispose ; les buffers différés sont fermés/ignorés par ce propriétaire.

- [ ] RED T09–T11 : A répond après sélection B, tokens/flush/done de A tardifs, deux vues et singleton partagé, changement de compte, annexe supprimée, reset d'une cible non affichée.
- [ ] Paramétrer toutes les API par la cible et conserver l'identifiant renvoyé par le serveur. Un 404 d'annexe est un état explicite ; seul le contrat nullable de Principale signifie « pas encore créée ».
- [ ] Attacher historique/recherche/pagination/totaux/debug aux clés owner+conversation+revision ; utiliser annulation et garde de génération, car un abort ne garantit pas l'absence d'un callback déjà prêt.
- [ ] Localiser client SSE et buffers de tokens. Le cleanup d'une ancienne vue n'annule ni ne flush le stream de la nouvelle.
- [ ] Étendre la clé du brouillon persistant à compte+discussion et migrer l'ancienne clé vers Principale uniquement. Le flush capture sa cible ; `seedInputDraft` sans cible prépare Principale ; logout supprime toutes les clés du compte. Tester refresh, switch pendant debounce, stockage indisponible et deux onglets.
- [ ] Coalescer les signaux backend par paire compte/conversation, respecter rollback et after_commit ; transmettre le payload entier et ne rafraîchir que la bonne vue/liste.
- [ ] Prendre en charge la reconnexion : flux actif→reattach ; flux terminé→history merge ; événement manqué→foreground reconciliation ; aucun appel LLM de rattrapage.

**Tests :** étendre les sept fichiers frontend de référence, `apps/web/src/hooks/__tests__/useInputDraft.test.ts`, les tests de reducer SSE/compaction/HITL et créer `apps/web/src/hooks/__tests__/useConversationSelection.test.tsx`, `apps/web/src/lib/__tests__/chat-stream-isolation.test.ts`. Backend : `apps/api/tests/unit/domains/conversations/test_multi_conversation_sync.py`.

**Commande ciblée :** `task test:frontend -- src/hooks/__tests__/useConversationSelection.test.tsx src/lib/__tests__/chat-stream-isolation.test.ts` puis les suites modifiées. **Sortie :** navigation et événements ne peuvent écrire dans une autre discussion.

## Lot 9 — Gestionnaire, badge et ergonomie

**Créer :** `apps/web/src/components/chat/ConversationSwitcher.tsx`, `ConversationCreateDialog.tsx`, `DeleteConversationConfirm.tsx`. **Modifier :** `ChatWorkspace.tsx`, `ResetConversationConfirm.tsx`, `features/world/WorldNativePanel.tsx`, `app/[lng]/dashboard/chat/page.tsx`, `hooks/useAutoSendIntent.ts`, `hooks/useDeepLinkParams.ts`, `lib/chat-deep-link.ts`, six `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`.

**Interfaces :** le switcher reçoit sélection, catalogue et callbacks typés de sélection/création/suppression ; il ne possède ni transport SSE ni autorité de facturation. Le formulaire retourne un titre validé ; l'ID de tentative est conservé pendant retries. Reset/delete nomment la cible affichée au moment de l'ouverture et sa révision, même si la vue change ensuite.

- [ ] RED T27/T38 : ouverture badge, Principale épinglée et sans action delete, création obligatoire, Enter/Escape, erreur réseau et retry, suppression active/inactive, retour à Principale après retrait durable ; erreur de nettoyage suivie sans retour de l'annexe.
- [ ] Réutiliser Dialog/FieldFrame/Input/RowActions/AlertDialog et les tokens existants ; actions de ligne séparées, pas de boutons imbriqués. Nom accessible traduit et complet, titre visuel tronqué.
- [ ] Renommer le contrôle de barre en « Réinitialiser » et toutes les variantes locales. Distinguer les textes reset/delete, y compris apprentissages et actifs conservés, sans exposer les détails de checkpoint à l'utilisateur.
- [ ] Implémenter les brouillons locaux par discussion et la récupération d'un brouillon quand sa cible a disparu ; ne jamais envoyer automatiquement son contenu dans Principale.
- [ ] Mettre le badge dans le groupe central en flux. Adapter le reflow lorsque l'état chargé ne tient pas à 320 px ; garder voix, recherche, contexte, espaces, reset et ancrage du compagnon accessibles.
- [ ] Appliquer le même contrôleur au World embedded ; la sélection n'éjecte pas du World et ne change pas les conversations sociales entre personnes.
- [ ] Préserver les query params d'intent ; un lien sans cible ouvre Principale, un lien ciblé s'autorise avant consommation, un lien périmé n'envoie rien ailleurs.
- [ ] Tester mode background actif/inactif : détachement autorisé avec reprise dans le premier cas, navigation pendant génération explicitement bloquée dans le second. Le UI explique l'état occupé par un autre tour du compte.

**Tests nouveaux :** `apps/web/src/components/chat/__tests__/ConversationSwitcher.test.tsx`, `ConversationCreateDialog.test.tsx`, `DeleteConversationConfirm.test.tsx` ; `apps/web/e2e/smoke/chat-secondary-conversations.spec.ts`, `chat-secondary-conversations-sync.spec.ts`.

**Tests existants à étendre :** `chat-header-reachability.spec.ts`, `chat-header-layout.spec.ts`, `chat-reset-confirm.spec.ts`, `chat-conversation-sync.spec.ts`, `chat-hitl-card.spec.ts`, `chat-intent-replay.spec.ts`, parcours World et tests Live pertinents. Mettre à jour leurs commentaires devenus faux sur les fichiers générés.

**Sortie :** T28/T29 sur état chargé, longs titres, six langues, thèmes, zoom et clavier ; aucun contrôle masqué sous un autre, focus rendu après fermeture.

## Lot 10 — Dépenses, registres, caches et observabilité

**Modifier selon le résultat des tests :** portes existantes `domains/usage_limits/`, `infrastructure/llm/usage_guard.py`, `infrastructure/cache/llm_cache.py`, `domains/chat/repository.py`, extractions/accounting concernés et `domains/agents/effects/`. Aucune nouvelle route de facturation parallèle.

**Créer seulement si nécessaire :** `apps/api/src/infrastructure/observability/metrics_conversation_lifecycle.py` avec tableaux/panneaux/alertes correspondants, et un runbook de purge en attente. Les métriques de sync existantes restent la référence pour les signaux.

- [ ] RED T20–T22 : compte/instance bloqués restent bloqués dans une annexe neuve ; compteurs affichés locaux et dépenses globales ; propre clé connecteur ; 429/timeout sans double appel ; sources retirées et coût payé conservé.
- [ ] Garder la comptabilité par run et le rattachement à la discussion métier pour toutes les modalités ; vérifier les extractions différées et leurs fallbacks, pas seulement le modèle de réponse.
- [ ] Donner à la clé cache les dépendances sémantiques nécessaires, dont runtime/révision si implicites. Le test interdit de dépendre d'un `config` actuellement exclu ou de purger les caches d'autres comptes.
- [ ] Mesurer les formes de prompts des deux modes et les compteurs cache natifs fournisseurs sur les fixtures : historique A/B correctement isolé, contexte commun borné une seule fois, coûts historiques non recalculés.
- [ ] Vérifier les lecteurs de registres, exports, profils et suppressions : message source null admissible, aucun resealing ou acte synthétique pour un clic de CRUD.
- [ ] Publier erreurs/retards de cleanup et runs recovering avec labels fermés et alertes testées ; distinguer attente, refus, reprise et succès. Aucun UUID/titre en label. Mesurer `pg_stat_activity` pendant les attentes fournisseurs et les purges externes.
- [ ] Exécuter les guards de spend roads, user-data map, key families, messages readers, logging/PII et métriques. Faire baisser les hotspots réellement réduits, sans ajuster un baseline avant mesure.

**Tests nouveaux :** `apps/api/tests/integration/domains/conversations/test_multi_conversation_accounting.py`, `apps/api/tests/unit/infrastructure/cache/test_conversation_llm_cache_scope.py`, `apps/api/tests/integration/domains/conversations/test_retained_records.py`.

## Lot 11 — Qualification et documentation de livraison

- [ ] Relancer chaque T01–T40 sur le snapshot final et tenir un rapport : commandes exactes, exits, compte de tests, warnings, runtime/browsers, limites. Un succès datant d'avant une modification importante n'est pas recyclé.
- [ ] Passer `task lint`, `task test:backend:unit:fast`, `task test:frontend`, `task test:frontend:coverage` et les intégrations ciblées sur PostgreSQL/Redis jetables. Pour les changements de tâches de fond, passer aussi la couverture backend séquentielle ; aucun warning de ressource ou stderr après résumé accepté.
- [ ] Passer `task db:migrate:replay-check`, vérifier une seule tête Alembic et les migrations depuis une copie jetable des formes de données historiques. Ne jamais utiliser la base dev/prod comme cible destructive de test.
- [ ] Exécuter les nouveaux parcours et les parcours critiques touchés dans le harness Playwright hermétique. Chromium obligatoire ; Firefox/WebKit et reflow/zoom requis pour les nouveaux contrôles et la voix selon la matrice existante. Le navigateur ne doit joindre aucun fournisseur payant.
- [ ] Vérifier le clavier tactile et les safe-areas sur les shells mobiles selon les moyens disponibles ; une émulation desktop ne sera pas annoncée comme un test sur téléphone physique.
- [ ] Mesurer le listing sans N+1, les deux navigateurs/onglets simultanés, les notifications pendant switch, les crashs aux frontières de commit et la reprise après redémarrage du worker.
- [ ] Ajouter l'ADR au numéro libre réellement courant, les entrées des cartes vivantes et leurs six traductions. Mettre à jour les guides chat/mémoire/fichiers/Live, FAQ6 locales, README et architectures réellement impactées. Ne pas recopier des defaults détenus par le code.
- [ ] Si une règle générale est nécessaire, modifier `CLAUDE.md` et régénérer `AGENTS.md` par `task docs:sync-agents`. Exécuter les gates docs/maps/i18n ; ne pas « corriger » un faux défaut d'index que le preview élimine.
- [ ] Établir le protocole d'activation : schema/code compatible, workers drainés/remplacés, backlog cleanup sain, activation de création. Retour arrière opérationnel = création off, données toujours consultables ; ancien schéma singleton non réinstallable en présence d'annexes.
- [ ] Avant toute demande future de push, `task ci:fast` puis suites supplémentaires exigées par l'impact. Aucune commande Git ou de déploiement n'est incluse dans ce plan.

**Critère de livraison :** toutes les conditions fonctionnelles de l'analyse et T01–T40 ont leur preuve ; les limites de moyens sont nommées et ne dispensent d'aucun invariant critique. Aucun mélange de cible, aucune suppression collatérale, aucun contournement de quota, aucun contrôle inaccessible, aucun succès de purge prématuré. Aucun scénario critique non exécuté n'est accepté implicitement. Une limitation nouvelle n'est pas masquée par un drapeau ou un mock.

## Contrôle du plan avant exécution

| Contrôle | État de l'analyse |
|---|---|
| Source du besoin et décisions | Présentes dans le dossier lié ; aucun comportement métier essentiel laissé implicite. |
| Réutilisation | Graphe, extracteurs, contexte typé, broker, journal, audit, UI et fixtures existants identifiés. Pas de deuxième moteur. |
| Identités | Compte, discussion, runtime, run, session vocale fournisseur explicitement séparés. |
| Données anciennes | UUID conservés, migration/backfill, anciens clients, anciens records Live et downgrade cadrés. |
| Effets et pannes | Claims, résultats explicites, retries locaux idempotents et refus de relancer une génération inconnue testés dans les lots propriétaires. |
| Ratchets | Hotspots mesurés ; extractions cohérentes prévues ; aucun relèvement autorisé. |
| Questions bloquantes | Aucune pour démarrer ces lots dans le périmètre fixé ; les choix d'extension seraient de nouvelles décisions. |
| Niveau de confiance | Prêt à implémenter sous TDD ; la preuve de correction finale appartient aux gates, pas au présent document. |
