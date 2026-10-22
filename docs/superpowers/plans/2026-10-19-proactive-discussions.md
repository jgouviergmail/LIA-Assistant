# Discussions proactives — plan d'implémentation TDD

Révision 2 du 19 octobre 2026 : recommandations validées par la personne,
portrait autonome, contexte longitudinal, directives prioritaires, tools
internes et gestion UI de la base (consultation, purge, non-utilisation).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Exécution strictement INLINE, aucun sous-agent, conformément à la demande de la personne. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter des ouvertures de conversation personnelles, pertinentes et
contrôlables, tout en conservant les notifications proactives existantes.

**Architecture:** Domaine dédié, contexte longitudinal dérivé dans PostgreSQL,
orchestration hors LangGraph à recherche bornée, sources offertes par ports,
directives procédurales applicables, archive et diffusion natives. Préférences,
cadence, claims et budgets propres ; alertes et tours humains prioritaires.

**Tech Stack:** Python/FastAPI/SQLAlchemy/PostgreSQL, Redis/APScheduler,
LLM factory et structured output existants, Next.js/React/TypeScript,
pytest/Vitest/Playwright, Taskfile du dépôt.

**Spec:** [analyse et conception](../specs/2026-10-19-proactive-discussions-design.md).

## État de livraison — 20 octobre 2026

Implémentation réalisée directement dans le checkout `D:\Developpement\LIA`,
sur `main`, avec conservation des modifications concurrentes. Les cases ci-dessous
décrivent le plan TDD d'origine ; le bilan vérifié de l'exécution est celui de
cette section et des ADR [358](../../architecture/ADR-358-Independent-Proactive-Discussions-And-Native-Delivery.md),
[359](../../architecture/ADR-359-Longitudinal-Discussion-Context-And-User-Control.md)
et [360](../../architecture/ADR-360-Bounded-Discussion-Research-And-Accounted-Abstention.md).

Les lots métier, la source SMS native, les trois slots LLM, les outils internes,
les réglages et la gestion du contexte/historique sont raccordés. Les migrations
ont été éprouvées sur PostgreSQL isolé et appliquées à l'instance Docker DEV.
La génération exige les trois plafonds opérateur documentés dans l'ADR-360,
un modèle effectif compatible et le consentement personnel. L'absence de plafond
ferme la génération, sans cacher les réglages.

Qualification finale : 321 tests unitaires et PostgreSQL des discussions réussis ;
suite backend rapide complète à 45 445 réussites, 32 skips et un échec documentaire
extérieur au chantier (trois documents concurrents présents sur disque mais absents
de l'index). L'audit documentaire en prévisualisation valide ces liens. La suite
frontend avec couverture réussit, ainsi que le lint, le typage et les trois parcours
navigateur à 320, 390 et 1280 pixels, avec contrôles d'accessibilité et de débordement.
Les ratchets ne sont pas relevés.

Aucun appel de modèle payant, déploiement de production ou de démonstration n'a été
effectué. L'évaluation humaine du naturel des discussions et la réception sur un
appareil réel restent des qualifications produit explicites ; les tests simulés
ne les prouvent pas. Le code livré reste dans le travail local non commité.

## Global Constraints

- Analyse du 19 octobre 2026, `main` HEAD `4b8016fba`, avec changements concurrents
  non inclus dans ce commit : relire l'état réel avant exécution.
- Aucun code métier n'est livré par ce document. Les choix métier sont approuvés
  et les précisions reçues remplacent les anciennes propositions contradictoires.
- Même diffusion que les notifications proactives actuelles : décision explicite
  de la personne ; pas de push générique imposé ni de canal ajouté.
- Notifications actuelles, leurs prompts, leurs préférences et l'absence de
  plafond quotidien heartbeat restent inchangés.
- Aucun minimum quotidien ; maximum nullable ; compter seulement les ouvertures
  archivées, jamais les tours de réponse ni les tentatives d'envoi par appareil.
- Lecture seule des sources ; écritures dans la base dérivée interne seulement ;
  aucune nouvelle autorité d'action externe ni faux
  message utilisateur ; les mutations demandées ensuite gardent le HITL serveur.
- Nouvelle source désactivée jusqu'au choix de la personne. Accès, cache,
  enrichissement et nouveaux dérivés sous la même politique.
- Portrait source autonome, autorisé ou refusé en bloc ; aucun filtrage de ses
  supports d'après les autres interrupteurs. Pas de programme de provenance
  transitive absolue des mémoires historiques dans ce périmètre.
- Base de contexte consultable dans l'UI ; purge globale et par sélection,
  statut réversible « Non utilisable » appliqué avant modèles et calculs.
  Exclusions conservées après reconstruction et purge ; aucun effacement source.
- Les règles procédurales actives sont chargées par leur propre chemin et
  versionnées ; le refus de la source factuelle mémoires ne les exclut pas.
  Le consentement mémoire global et les protections des règles épinglées restent en place.
- Valeurs de qualification proposées, à confirmer : fonction off ; maximum 2/j ;
  fenêtre 09 h–20 h ; délai 4 h ; attente 24 h ; audit opérationnel 30 j ;
  72 h récentes + 7 j prospectifs ; tick 30 min. Approfondissement V2 : historique
  ciblé 6 mois + 30 j futurs, contexte minimal 12 mois sous rétention source,
  2 vagues de 4 lectures ; budgets contexte 8000/1200 par passe, décision
  6000/600, rédaction 2000/250, à qualifier aux plafonds réels des slots.
- Heures 0–23 ; début inclus, fin exclue ; égalité refusée ; overnight permis.
- Au plus cinq appels modèle par run avec construction profonde ; trois pour
  un contexte modifié sans recherche ; deux avec contexte valide réutilisé.
  Aucune répétition automatique
  d'un appel modèle échoué ; tous les usages connus conservés.
- Montants des enveloppes financières : configuration opérateur requise et
  mesurée avant activation ; leur absence ne signifie pas budget illimité.
- Pas de nouvelle dépendance envisagée. Ratchets shrink-only, fichiers cohérents,
  aucune session SQL autour du réseau, une session par lecteur concurrent.
- Tests hermétiques et comptes fictifs ; runtime frontend dans Docker DEV.
  Aucun déploiement prod, aucune modification des données réelles dans ce plan.

## Review Focus

1. Une source refusée ou un élément « Non utilisable » reste exclu des caches,
   recherches et nouveaux dérivés ; le portrait autorisé reste entier : lots
   3, 3A, 4 et 9.
2. Une alerte, un tour humain, un reset ou un opt-out survenant durant la
   génération font céder la discussion avant publication : lot 7.
3. Deux workers, un crash après commit et un acquittement fournisseur perdu
   n'ajoutent pas une seconde ouverture ni une nouvelle dépense de génération :
   lots 2 et 7.
4. Une simple réponse « oui » à une ancienne ouverture reprend le bon contexte
   sans transformer une hypothèse de LIA en fait humain : lot 8.
5. Fonction activée sans matière, source partielle et décisions `skip` ne
   fabriquent ni sujet ni silence de facturation : lots 4, 5, 6 et 10.
6. Un rendez-vous mensuel n'est pas traité comme une nouveauté à chaque fois,
   et des données manquantes ne prouvent pas un événement isolé : lot 3B.
7. Une correction humaine s'applique malgré l'extraction retardée ; une règle
   épinglée ou hors top-k n'est pas oubliée ; non-utilisation et purge survivent
   aux reconstructions : lots 3C, 8 et 9.

## Découpage des responsabilités et interfaces communes

Les chemins nouveaux de cette section sont des propositions. Les modules
existants cités ont été inspectés ; ne pas créer des modules fantômes parce
qu'un ancien commentaire ou une note mémoire les nomme.

| Zone | Responsabilité |
|---|---|
| `domains/proactive_discussions/schemas.py`, `policy.py`, `registry.py` | Contrats, décisions pures, sources et dépendances publiées |
| `context_store/`, `contextualization/`, `directives.py` | Base dérivée, épisodes, séries/occurrences, contraintes et invalidations |
| `models.py`, `repository.py`, `commands.py`, `router.py` | Persistance, transitions atomiques, préférences et API propriétaire |
| `context.py`, `research.py`, `selection.py`, `prompts.py` | Budget, instantané, lectures complémentaires et décisions |
| `delivery_authority.py`, `publication.py`, `runner.py` | Autorité fraîche, archive/outbox et coordination |
| `billing.py`, `consultations.py`, `lifecycle.py` | Coûts, registres et effacement |
| `domains/shared/discussion_sources.py` | Ports sans dépendance vers agents ou domaines fournisseurs |
| Modules `discussion_source.py` chez les domaines propriétaires | Projection des lectures et des droits ; aucun repository d'autrui réimplémenté |
| `infrastructure/scheduler/proactive_discussions.py` | Job, jitter, batches et composition du moteur |
| `infrastructure/proactive/notification.py` | Adaptation minimale et compatible de la diffusion d'un message déjà archivé |
| Hook et composants frontend dédiés | Réglages, retours, exclusions, historique et reprise du chat |

Types de la spec définis au lot 1 : `DiscussionPolicy`, `SourceSnapshot`,
`DiscussionEvidence`, `ResearchRequest`, `DiscussionDecision`,
`DiscussionOpening`. Ajouter `RunClaim`, `PublicationReceipt`, `DeliveryAttempt`,
`DiscussionLimits`, `AttentionVerdict`, `BudgetReservation`, `SourceReadRequest`,
`RunResult` dans des modules étroits si le fichier de schémas approche son cap.
Pas de `Any`, de statut sans producteur ou de champ JSON sans validateur.

Interfaces possédées par les lots :

- Sources : `DiscussionSource.read(request: SourceReadRequest) -> SourceSnapshot`
  asynchrone. Request porte compte, run, politique/version, fenêtre et budget.
- Contexte : `build_context(user_id: UUID, *, run_id: str, now: datetime,
  policy: DiscussionPolicy) -> DiscussionSnapshot` asynchrone.
- Recherche : `execute_research(snapshot: DiscussionSnapshot, requests:
  tuple[ResearchRequest, ...]) -> DiscussionSnapshot` asynchrone.
- LLM : `interpret_context(candidate: ContextCandidate, *, research_remaining: int,
  run_id: str) -> ContextResolutionWithUsage`, `decide(snapshot: DiscussionSnapshot,
  *, run_id: str) -> DecisionWithUsage` et `write_opening(candidate:
  EngagementCandidate, *, run_id: str) -> MessageWithUsage`, asynchrones.
- Publication : `publish_opening(claim: RunClaim, candidate: EngagementCandidate,
  message: MessageWithUsage, *, now: datetime) -> PublicationReceipt`, asynchrone.
- Runner : `run_discussion_for_user(user_id: UUID, *, now: datetime) -> RunResult`,
  asynchrone ; `now` injecté et transmis, pas redéfini par chaque helper.

`DecisionWithUsage` et `MessageWithUsage` transportent les `LLMBillingRecord`
existants. `DiscussionSnapshot` porte la politique autorisée, les lectures, les
  références et la couverture ; `EngagementCandidate` est une décision engage
validée, sans nouveau texte utilisateur. Les références persistées ne servent
jamais à reconstruire un contenu expiré.

Chaque lot suit RED → preuve de l'échec attendu → implémentation minimale →
GREEN → revue INLINE. Les commits d'implémentation sont limités aux fichiers
du lot ; ne jamais inclure l'index concurrent entier ni utiliser `--no-verify`.

## Lot 1 — Contrats et politique pure

**Fichiers à créer :** `apps/api/src/domains/proactive_discussions/{__init__,schemas,policy,registry}.py`,
`apps/api/src/domains/shared/discussion_sources.py`.

**Tests :** `apps/api/tests/unit/domains/proactive_discussions/test_policy.py`,
`test_decisions.py`, `test_registry.py`.

**Consomme :** helper `is_within_hour_window`, timezone et domaine canonique existants.
**Produit :** tous les types communs, `effective_sources(policy, authority)`,
`validate_research_request(request, snapshot)` et registre vérifié au boot.

- [ ] Écrire `test_null_daily_max_means_no_count_bound`,
  `test_zero_max_rejected`, `test_equal_hours_rejected`,
  `test_overnight_start_inclusive_end_exclusive`,
  `test_empty_allowlist_reads_nothing`, `test_added_source_defaults_off`.
  Assertions : null reste null ; 0/égalité/clé inconnue refusés ; 22–6 accepte
  22 et 5, refuse 6 ; source nouvelle non autorisée par héritage.
- [ ] Écrire les unions : `skip` refuse un message ; `engage` exige sujet et
  références présentes ; `defer` exige une échéance bornée. La résolution de
  contexte est une union distincte `ready|research|insufficient`, avec 1 à 4
  lectures pour `research`. Refuser surplus de champs et opération inconnue.
- [ ] Exécuter les trois modules pytest ciblés et constater RED pour contrats
  absents, sans dépendance réseau ni skip conditionnel de clé fournisseur.
- [ ] Implémenter modèles stricts, union discriminée, décisions pures et
  spécification serveur des sources. La source SMS est déclarée indisponible
  avec une raison ; pas un lecteur vide affiché comme succès.
- [ ] Vérifier complétude bidirectionnelle source/label/port/dépendances et
  domaine taxonomique. Les intentions éditoriales ne créent pas de domaines.
- [ ] Rejouer les TU et `task lint:cycles`, `task lint:i18n` si labels ajoutés.

## Lot 2 — Préférences, claims et transitions PostgreSQL

**Créer :** `models.py`, `repository.py`, `commands.py` du nouveau domaine ; une
migration Alembic suivant le véritable head au moment d'exécuter ce lot.
**Modifier :** `apps/api/src/infrastructure/database/registry.py`.
**Tests :** `tests/integration/domains/proactive_discussions/test_repository.py`,
`test_claims.py`, `test_policy_writes.py` sous `apps/api`.

**Consomme :** contrats du lot 1.
**Produit :** `get_policy(user_id)`, `update_policy(user_id, patch, expected_revision)`,
`claim_run(user_id, now)`, `renew_claim(claim)`, `settle_run(claim, result)`,
`commit_opening(claim, candidate, message, now)` ; async, owner-scoped.

- [ ] RED sur PostgreSQL jetable : ancien compte absent de la table de politique
  lit off ; deux bootstraps créent une seule ligne ; révision concurrente refuse
  une modification périmée sans perdre les clés ; FK et contraintes de maximum.
- [ ] RED : deux acteurs réclament le même compte, un seul gagne ; expiry,
  takeover et ancien acteur ne peuvent renouveler/clore ; cancellation écrit
  `abandoned` sans annuler le propriétaire suivant.
- [ ] RED : archive + ouverture + outbox + compteur logique sont atomiques ;
  rollback ne consomme rien ; deux publications au dernier quota n'en passent
  qu'une ; null ne passe pas dans une comparaison numérique.
- [ ] Implémenter préférence dédiée, claim/fencing, index de requête des
  candidats, ouvertures et outbox/tentatives. Un seul message ID par ouverture ;
  unicité de la clé de publication et pending unique par compte.
- [ ] Le total journalier est dérivé des ouvertures archivées dans la plage UTC
  du jour civil courant ; si un compteur matériel est nécessaire, UPSERT SQL
  atomique dans la même transaction, jamais SELECT/incrément Python.
- [ ] GREEN sur vraies transactions : DST 23 h/25 h, minuit local, timezone
  modifiée et max diminué pendant génération. Aucun test ne mocke le SQL central.
- [ ] Vérifier migration upgrade/downgrade et unique head, import de modèles,
  annotations MyPy et ratchet de taille ; ne pas migrer une DB réelle.

## Lot 3 — Sources possédées et droits des données dérivées

**Créer :** modules `discussion_source.py` sous `memories`, `journals`, `habits`,
`open_loops`, `relations`, `health_metrics`, `meetings`, `peers`, `interests`,
`reminders`, `scheduled_actions`, `workboard`, `conversations` ; lecteurs par
famille sous `connectors/discussion_sources/` pour calendar/email/contact/task/weather/location.
La composition les installe dans `shared/discussion_sources.py`.

**Modifier :** hooks de démarrage `infrastructure/startup/registries.py`,
`domains/shared/consultation_surfaces.py`,
`domains/agents/effects/{user_data_readers,direct_client_callers}.py` si un
nouveau lecteur direct le justifie réellement ; `conversations/message_readers.py`
si le reader lit directement le modèle plutôt que son repository.

**Tests :** `tests/unit/domains/proactive_discussions/test_source_authority.py`,
`test_source_projection.py`, `test_derived_context.py` et intégration
`test_sources_pg.py` ; tests au niveau des adaptateurs concernés.

**Consomme :** politique et port source.
**Produit :** snapshots avec couverture, références stables, permissions
revalidables, provenance et statuts explicites pour chacune des sources.

- [ ] RED `test_refused_source_invokes_no_live_or_cache_reader` sur toutes les
  sources, y compris agenda occupé ; `test_connector_scope_revoked_blocks_detail` ;
  `test_unknown_availability_is_not_empty` ; `test_foreign_evidence_id_rejected`.
- [ ] RED des projections : email lu/envoyé récent ne disparaît pas parce que
  le heartbeat ne lit que non-lus du jour ; tâche réalisée/échéance distinguées ;
  agenda annulé/refusé ; rapport réunion courant seulement ; peer côté propre et
  texte expiré absent ; mémoire invalidée ignorée ; source SMS non livrée indisponible.
- [ ] RED `test_allowed_portrait_is_whole_despite_constituent_source_refusal`,
  `test_disallowed_portrait_is_neither_read_nor_reused_from_context_store`,
  `test_dated_portrait_is_not_recent_event_evidence`,
  `test_biometric_memory_respects_health_and_topic_consent`.
- [ ] Implémenter projections dans les domaines propriétaires, sans requêtes
  métier recopiées. Portrait : builder existant, bloc bref entier daté sous son
  propre consentement ; aucun filtrage de ses supports, aucune recompilation globale.
- [ ] Enregistrer seulement les consultations réellement ouvertes avec
  `source=proactive`, sous le collecteur du run. Cache hit ne revendique pas un
  accès fournisseur ; échec déclaré. Aucune capture de texte privé dans les logs.
- [ ] GREEN avec clients normalisés simulés Google/Apple/Microsoft ; vérifier
  la direction, les identités ambiguës et les scopes. Exécuter les guards de
  cycles/lecteurs, les tests du portrait et les tests heartbeat de sources existants.

## Lot 3A — Base contextuelle, générations et non-utilisation

**Créer :** `domains/proactive_discussions/context_store/{models,schemas,repository,updater}.py`,
migration Alembic additive du nouveau modèle ; `context_commands.py` pour les
commandes de purge, non-utilisation et remise en utilisation.
**Tests :** `test_context_store.py`, `test_context_exclusions.py`, intégration
`test_context_store_pg.py`, `test_context_forgetting_pg.py`.

**Consomme :** sources normalisées et politique du lot 3.
**Produit :** `ContextObservation`, `ContextEpisode`, `ContextPattern`,
`ContextEvidenceLink`, `SourceCoverage`, `ContextGeneration`, `ContextCandidate`,
`ContextUseExclusion`, `ContextResolution`, `DirectiveSnapshot` ;
`apply_delta(candidate, delta)`, `publish_generation(claim, candidate)`,
`set_context_usable(actor_id, item_id, usable, expected_revision)`,
`purge_context(actor_id, selection, expected_epoch)`, asynchrones et owner-scoped.

- [ ] RED sur PostgreSQL : upsert d'objet/version idempotent, delta inchangé
  sans nouvelle observation ni analyse ; source/compte distincts ne se heurtent
  pas ; curseur partiel ne marque pas toute la période comme couverte.
- [ ] RED : reconstruction concurrente et ancienne génération servant jusqu'à
  publication atomique ; ancien worker après purge ne peut écrire ; rollback
  garde l'état validé ; suppression d'une source retire ses supports et dérivés.
- [ ] RED `test_non_usable_item_and_descendants_never_reach_model_or_retrieval`,
  `test_non_use_survives_source_upsert_relabel_and_generation_rebuild`,
  `test_purge_preserves_non_use_choices`, `test_reenable_requires_explicit_user_action`.
  Vérifier les entrées réellement fournies aux modèles et agrégateurs, pas
  seulement le flag de la ligne finale.
- [ ] Implémenter identités stables d'éléments indépendantes d'un texte résumé
  et de la génération, source/version/occurrence, liens de preuve et état
  utilisable/non utilisable. L'exclusion d'un épisode ou pattern bloque aussi
  sa réutilisation par les nouveaux calculs, pas seulement sa sélection finale.
- [ ] RED : si un bloc indivisible réintroduirait un élément explicitement
  exclu, l'omettre entier, portrait compris, sans inspection ni filtrage de ses
  supports historiques. Les détails UI expliquent cette admission effective.
- [ ] Implémenter purge globale ou sélectionnée, epoch d'oubli, annulation des
  claims/outbox dépendants et marqueur de reprise : pas de réimport immédiat
  silencieux de l'ancien historique ; reconstruction historique explicite.
  Préférences, exclusions de non-utilisation et sources originales conservées.
- [ ] Mise à jour incrémentale bornée : curseur natif lorsqu'il existe, sinon
  fenêtre avec chevauchement et versionnement. Lots restants gardés « à traiter »,
  pas jetés quand le budget est consommé. Ne pas copier des corps source complets.
- [ ] GREEN : rétention dérivée au plus tard avec celle des sources, contexte
  minimal glissant proposé de 12 mois, export/purge du compte, rétention peer
  courte, root portrait autonome, source refusée et reset chat limité à ses supports.

## Lot 3B — Séries, occurrences, épisodes et récurrences personnelles

**Créer :** `contextualization/{identity,patterns,episodes}.py` du domaine.
**Modifier :** projections additives des clients agenda et normaliseurs Google,
Microsoft et Apple cités dans la spec, sans changer les cartes/tools actuels ;
contrat typé des adaptateurs du lot 3.
**Tests :** `test_occurrence_identity.py`, `test_personal_patterns.py`,
`test_episodes.py`, fixtures des trois calendriers et `test_monthly_followup_flow.py`.

**Consomme :** observations, couverture et exclusion du lot 3A, résolveurs
d'identité existants, récurrences déclarées de la source.
**Produit :** `qualify_pattern(occurrences, coverage, declared_series) -> ContextPattern`,
`build_episode(observations, prior_episode, constraints) -> EpisodeProposal`,
avec preuves/contradictions et état explicite déclaré/observé/possible/périmé.

- [ ] RED : même UID Apple pour plusieurs occurrences n'écrase pas les dates ;
  parent/type/originalStart Graph conservés ; originalStartTime Google et exception déplacée
  désignent la même occurrence ; annulation ne devient pas un accomplissement.
- [ ] RED : un RDV médical avec historique inconnu n'est pas « isolé » ; une
  série mensuelle n'est pas une présence confirmée ; des rendez-vous indépendants
  espacés de 28/31 jours peuvent former un rythme civil observé sans RRULE inventée.
- [ ] RED : trois doubles lectures d'un rendez-vous ne comptent pas comme trois
  visites ; titre proche pour enfant/contact ne concerne pas automatiquement
  l'utilisateur ; absence de couverture empêche de conclure à une rupture.
- [ ] Implémenter normalisation additive et calcul déterministe des occurrences,
  fréquences et écarts, avec seuils configurés et justifiés par le corpus, pas
  réutilisation du ledger de demandes à LIA comme preuve de rendez-vous.
- [ ] Implémenter regroupement d'épisodes étayé : projet commencé/terminé,
  conversation citée/événement nouveau, demande envoyée/réponse obtenue. Une
  hypothèse proposée par modèle n'est admise qu'avec supports résolus et
  compatibilité d'identité ; une exclusion rend ses dérivés non admissibles.
- [ ] GREEN sur corpus multi-mois : suivi médical déclaré, observé, sporadique,
  déplacé, interrompu, corrigé « routine », même titre mais autre personne ;
  qualifier aussi projet, attente et intérêt repris. Rejouer tests des trois
  clients et des cartes agenda pour la non-régression de projection.

## Lot 3C — Lecture des directives et réaction aux corrections

**Créer :** `directives.py`, `directive_cache.py`, port/hooks de réaction humaine
du domaine, sans import cyclique depuis les domaines mémoires/conversations.
**Modifier :** lecture paginée active du repository mémoire et porte d'événements
après commit d'extraction/édition si elle n'existe pas ; l'extracteur garde son
comportement envers les lignes épinglées.
**Tests :** `test_procedural_constraints.py`, `test_correction_bridge.py`,
intégration `test_directive_revision_pg.py`, `test_feedback_extraction_flow.py`.

**Consomme :** catégorie/protections/consentement mémoire existants, vrais messages
humains visibles et identifiant d'ouverture.
**Produit :** `load_directive_snapshot(user_id) -> DirectiveSnapshot`,
`build_directive_constraints(snapshot, candidate) -> DirectiveConstraints`,
garde transitoire et invalidation de candidats après correction.

- [ ] RED : directive ancienne hors top-k et 201e règle toujours considérées ;
  pagination cohérente ; aucune réanalyse sur simple usage_count ; budget trop
  petit ne fait pas disparaître une interdiction silencieusement.
- [ ] RED : source factuelle « Mémoires » des discussions coupée n'éteint pas
  les contraintes ; mémoire globale coupée interdit leur lecture et l'extraction,
  tandis que les réglages structurés explicites restent effectifs.
- [ ] RED : « pas maintenant » temporaire, correction durable, pouce négatif
  ambigu et directive dans un email tiers sont distingués ; aucun modèle ne
  transforme les propres questions de LIA en instructions humaines.
- [ ] RED : correction explicite pendant génération invalide le candidat avant
  settlement mémoire ; extraction retardée/échouée ou update refusé sur règle
  épinglée ne produit pas un faux « mémorisé ». Suppression/édition manuelle
  invalide le cache et les contraintes dérivées.
- [ ] Implémenter snapshot complet propriétaire et compilation seulement quand
  les règles changent : contraintes structurables côté serveur, autres consignes
  intactes sous budget. Les références aux règles canoniques restent vérifiables.
- [ ] Brancher le garde transitoire sur le vrai retour humain lié à l'ouverture,
  puis sur l'issue du traitement mémoire réellement commis ; les consignes
  ambiguës font différer le sujet sans inventer une règle permanente. Correction
  d'une règle épinglée via UI ou tools mémoires et confirmation existants.
- [ ] GREEN : directive récente, contradiction durable, nouvel épinglage,
  suppression et consentement retiré durant appel ; vérifier de bout en bout
  la non-publication de la prochaine ouverture interdite.

## Lot 4 — Snapshot longitudinal, sélection et recherches utiles

**Créer :** `context.py`, `research.py`, `selection.py`, `consultations.py`.
**Tests :** `test_context.py`, `test_research.py`, `test_selection.py` dans les TU
du domaine, plus `test_source_timeouts.py` en intégration de faux clients.

**Consomme :** ports du lot 3.
**Produit :** `build_context`, `execute_research`,
`select_candidate(decision, snapshot) -> EngagementCandidate | None`.
`build_context` compose désormais les lots 3A–3C : slice autorisée du contexte
persisté, règles et delta, puis résolution sémantique via le port du lot 5.

- [ ] RED : budget de prompt intégral, item trop grand, forte volumétrie email,
  source tronquée, distinction date d'événement/date de collecte ; au moins les
  sources prioritaires permises gardent une chance de fournir un candidat.
- [ ] RED : deux vagues de quatre opérations maximum, avec plafond explicite
  des requêtes physiques incluant pagination et sous-appels ; requête sur objet
  étranger, source refusée, opération d'écriture, dates relatives non résolues,
  curseur ou intervalle malformé refusés avant invocation du port.
- [ ] RED : récurrence de deux événements homonymes sans identité ne devient
  pas une habitude ; couverture incomplète n'établit pas une absence ; mêmes
  faits via mail/SMS ou mémoire/journal ne sont pas des preuves indépendantes.
- [ ] Implémenter orchestrateur de lectures limitées, sessions séparées courtes,
  deadline par source et deadline globale, propagation de cancellation. Aucun
  full briefing/point360 pour filtrage après coup.
- [ ] Implémenter fingerprints de faits/version/fenêtre d'opportunité, cache
  d'empty avec TTL et sélection variée ; réévaluation à une échéance d'opportunité
  même sans changement de données, sans apprentissage non consenti. Réutiliser
  contexte et interprétations par version, sans réanalyser le même contenu.
- [ ] RED : pages incomplètes des trois agendas portent leur couverture réelle ;
  aucune fin de série déduite d'une réponse plafonnée ; recherche identique déjà
  satisfaite non refacturée ; élément non utilisable absent avant retrieval et
  toute interprétation ; purge empêche le réamorçage historique implicite.
- [ ] GREEN : faux serveur lent/401/403/429/payload énorme ; expiration cache,
  embedding absent, recherche très ancienne et futur lointain avec faible page,
  conflit de versions. Vérifier qu'aucune tâche/coroutine ne reste ouverte.

## Lot 5 — Interprétation contextuelle, décision et rédaction LLM

**Créer :** `prompts.py` et prompts versionnés
`discussion_context_prompt.txt`, `discussion_decision_prompt.txt`,
`discussion_message_prompt.txt` ainsi que
scaffolding versionné si nécessaire sous `agents/prompts/v1/`.
**Modifier :** `domains/llm_config/constants.py`, settings déclarés dans un module
`core/config/proactive_discussions.py` composé dans Settings ; registres de
placeholders/prompt versions et traductions admin.
**Tests :** `test_prompts.py`, `test_llm_contract.py`, `test_message_policy.py`.

**Consomme :** delta, génération valide, contraintes, snapshot, candidate et factory LLM.
**Produit :** `interpret_context`, `decide`, `write_opening`, leurs usages
facturables et erreurs typées. Le contexte proposé reste non publié avant
validation de références, d'identités et de version par le lot 3A.

- [ ] RED : le contexte peut demander une recherche tant qu'une vague reste ;
  la dernière résolution refuse de relancer ; la décision d'engagement ne propose
  pas de recherche ; `engage` sans preuve actuelle est écarté. Une réponse vide,
  JSON illisible ou tronqué ne devient pas une ouverture.
- [ ] RED : style et langue réellement actifs, instruction de personnalité via
  `PersonalityService.get_prompt_instruction_for_user`, marque temporelle du
  portrait, budget alloué et données externes distinctes des instructions.
- [ ] RED sur corpus adversarial : instruction dans email/SMS/peer ne change
  pas le rôle ; rendez-vous ne devient pas réussite ; silence ne devient pas
  anxiété ; mémoire sensible avec usage_nuance ne produit pas un sarcasme blessant.
- [ ] RED : contexte inchangé ne réutilise aucun appel d'interprétation ; delta
  modifié traité par lot, pas par document ; textes tiers ne créent aucune règle
  ni action ; contexte mensuel qualifié et observation isolée produisent des
  angles cohérents, sans annoncer participation ou état émotionnel inventés.
- [ ] Implémenter trois slots propres et prompts versionnés, profiles de
  reasoning et output cap existants ; pas de nouveau chat adapter JEV. Les
  tests consomment `LLM_DEFAULTS`, sans nom de modèle codé en dur.
- [ ] Compter le prompt complet avant appel ; garder une réponse non conforme
  comme échec fermé, pas de correcteur LLM supplémentaire caché. Les garanties
  sémantiques restent évaluées sur corpus, pas proclamées par regex.
- [ ] GREEN sur bornes : cache valide au plus deux appels, delta simple trois,
  deux vagues de recherches au plus cinq ; budgets 8000/1200 pour chaque passe
  contexte, 6000/600 décision et 2000/250 rédaction, sous plafonds du modèle.
- [ ] GREEN sur stubs LangChain typés, placeholder guards, registres des slots,
  locales et sorties multi-fournisseurs simulées ; aucune clé réelle requise.

## Lot 6 — Dépenses, réservations et observabilité

**Créer :** `billing.py`, `budget.py` du domaine,
`infrastructure/observability/metrics_proactive_discussions.py`.
**Modifier :** `infrastructure/llm/spend_roads.py`,
`domains/google_api/spend_roads.py` si des appels facturables sont ouverts,
registre des familles de cache, composition du suivi hors tour et affichages
de coût existants si le nouveau type est fermé dans leurs tables.
**Tests :** `test_billing.py`, `test_budget.py`, intégration
`test_budget_reservations_pg.py`.

**Consomme :** LLMBillingRecord et TrackingContext actuels.
**Produit :** `reserve_discussion_budget(user_id, run_id, estimate) -> BudgetReservation | None`,
`settle_discussion_budget(reservation, usage)` et règlement garanti des dépenses.

- [ ] RED : `skip` ayant consommé des tokens écrit le ledger ; décision réussie
  puis génération échouée conserve les deux usages connus ; annulation et
  révocation après appel n'effacent pas la facture ; aucun compte synthétique.
- [ ] RED : interprétation de delta, reconstruction demandée et compilation
  de contraintes sont facturées même sans ouverture ; aucun digest email caché
  hors enveloppe ; coût de chaque tentative rattaché au même run et à son owner.
- [ ] RED : budget d'instance et quota de compte refusent avant modèle ; un
  connecteur personnel n'est pas refacturé dans la dépense plateforme ; appels
  Google sans LLM restent comptés ; cached input et cache write ne sont pas doublés.
- [ ] RED PostgreSQL : deux réservations au dernier crédit, expiry et takeover,
  settlement idempotent, coût supérieur à l'estimation, annulation/crash libérant
  seulement le propriétaire ; borne financière absente empêche la production,
  sans présenter la sauvegarde d'une préférence comme une livraison effective.
- [ ] Implémenter l'enveloppe propre au flux sous les limites existantes, avec
  contrôle avant chaque appel. Budget indisponible suspend cette initiative
  sans modifier le fail-open/fail-closed des autres fonctions.
- [ ] Déclarer les routes de spend et consultations ; métriques à labels
  bornés : évaluations, skip/defer, ouverture, coût, coupe, échec, latence et
  canal. Pas de nom, email, sujet ou identifiant utilisateur en label.
- [ ] GREEN : absence de double accounting, usage tardif, prix manquant et
  plafond changé ; tests des guards spend/reader/registry et dashboards concernés.

## Lot 7 — Runner, autorité fraîche et publication durable

**Créer :** `runner.py`, `delivery_authority.py`, `publication.py` du domaine,
`infrastructure/scheduler/proactive_discussions.py`.
**Modifier :** `infrastructure/startup/schedulers.py`, feature switches et leurs
system settings, `infrastructure/proactive/notification.py` pour une entrée
explicite de diffusion d'archive existante.
**Tests :** `test_runner.py`, `test_attention.py`, `test_delivery_authority.py`,
intégration `test_publication_pg.py`, `test_outbox_recovery.py`.

**Consomme :** lots 1–6, ActivityProbe, conversation_has_pending_hitl, active_run_lease,
dispatcher et effet proactif existants.
**Produit :** runner et publication de leurs interfaces communes ; job enregistré
avec jitter ; `dispatch_archived(archive: ArchivedProactiveMessage, ...)` public.

- [ ] Caractériser en RED les anciens comportements du dispatcher avant
  extraction de code partagé : archive seule est un succès existant, échecs
  partiels par canal conservés, mêmes payloads pour heartbeat/intérêts/rappels.
- [ ] RED de la nouvelle publication : deux workers ne font qu'un message ;
  opt-out/source révoquée/compte inactif/heure passée/max atteint/objet supprimé
  entre décision et publication conduisent à abandon facturé.
- [ ] RED : tour humain, routine HITL, reset et alerte récente survenant pendant
  génération font céder le moteur. Une discussion publiée ne refuse jamais
  l'alerte suivante ; un bail perdu arrête tout effet ultérieur.
- [ ] RED : la sonde HITL retournant `(False, None)` donne un verdict inconnu
  et diffère ce flux. Un agenda refusé n'est pas consulté par le contrôle occupé.
  Ne pas changer les fallbacks historiques des routines et du heartbeat.
- [ ] Implémenter requête de candidats JOIN sur préférence dédiée, politique
  d'attention, claim durable et run sans session longue. Ne pas brancher la
  table de préférences sur un helper exigeant une colonne User inexistante.
- [ ] Publier avec lease de conversation courte, relecture d'activité/reset,
  contrôle frais des droits et transaction d'archive/outbox. Le fournisseur
  n'est jamais appelé pendant le verrou SQL de cette transaction.
- [ ] Implémenter `dispatch_archived` sans seconde archive, en extrayant les
  transports communs du dispatcher. L'ancien `dispatch` conserve ses defaults,
  métadonnées et calcul de succès. Clé d'effet stable par tentative/canal du
  nouveau flux ; reçus explicites, aucun « delivered » déduit sans résultat.
- [ ] GREEN : crash avant commit, après commit avant envoi, après acceptation
  avant settlement, provider sans idempotence : état incertain explicite et pas
  de répétition aveugle. Redis down suspend publication ; source down dégrade
  seulement la lecture concernée. Connexions SQL rendues pendant appels lents.
- [ ] Tester tick/push/moments heartbeat, intérêt et routines avec les suites
  existantes concernées ; nouveau switch opérateur coupe production au call
  time, conserve lecture et suppression de son historique.

## Lot 8 — API, feedback et reprise du tour humain

**Créer :** `router.py`, `feedback.py`, `topic_exclusions.py`,
`conversation_bridge.py`, `lifecycle.py` du domaine ; commandes applicatives
typées sous `agents/application/discussion_{schemas,operations,catalogue,spec}.py`,
`agents/tools/application_discussion_tools.py`, lecteurs et commandes de gestion
du contexte et du statut d'utilisation.
**Modifier :** `api/v1/routes.py`, catalogue applicatif et ressources, portes
de reply metadata de l'API chat existante et conversion `out_of_graph.py`
seulement si nécessaire pour porter une référence stable.
Étendre explicitement `agents/application/{registry,catalogue_registration,
native_operations,preparation,preference_dispatch,draft_editing,draft_rendering,
state_resources}.py` et `agents/tools/tool_registry.py` selon le type exact
d'opération ; ne pas créer un second système de commandes.
**Tests :** `test_routes.py`, `test_feedback.py`, `test_conversation_bridge.py`,
intégration `test_reply_flow.py`.

**Consomme :** politique persistée, opening/message ID et droits frais.
**Produit :** endpoints de spec, commande de pause et exclusion, référence
`reply_to_message_id` vérifiée dans le contrat de chat si absent actuellement.
Les dix tools de la table de spec couvrent réglages, historique/détails, pause,
refus de sujet, inspection, usage, purge et refresh du contexte. Les mémoires
procédurales gardent leurs tools existants.

- [ ] RED : route étrangère 404, plafond nullable, PATCH révision périmée,
  feedback rejoué identique idempotent, verdict inconnu refusé. `GET
  /topic-exclusions` liste ; `DELETE /topic-exclusions/{id}` retire un refus.
- [ ] RED des tools : fonction/manifeste/opération/sections présents au démarrage
  à froid, découvertes pipeline et ReAct, runtime owner injecté, jamais de user_id
  modèle ; maximum absent préserve, maximum null supprime seulement le plafond,
  tableau préserve les sources hors demande ; JSON schema conserve le null utile.
- [ ] RED : lecture d'historique sans accès fournisseur, réglage sauvegardé
  distinct de l'état effectif, lecture/purge possibles capability de production
  coupée ; refresh coûteux refuse sans droits/budget, annonce le job accepté
  sans dire la reconstruction finie ni forcer l'ouverture d'une discussion.
- [ ] RED : commande de non-utilisation et purge vérifie propriétaire, révision,
  sélection exacte et confirmations serveur ; draft périmé refuse ; ordre replay
  ne réactive pas une exclusion ; ressources UI actualisées après commit.
- [ ] RED : « Pas maintenant » suspend jusqu'à la fin réelle de la fenêtre
  courante, y compris overnight/DST, sans routine ni rappel ; exclusion de sujet
  réversible, sans supprimer mémoire ou modifier intérêts.
- [ ] RED : ouverture injectée comme AIMessage avant la réponse humaine ;
  réouverture d'historique et checkpoint ne doublent pas ; réponse explicite
  ancienne recharge son contexte autorisé même hors lookback natif ; « oui »
  ne répond pas au mauvais message ; référence d'un autre compte refusée.
- [ ] Implémenter une référence de réponse explicite, contrôlée serveur et
  bornée ; pas de pseudo-HumanMessage ni de transfert automatique de données
  périmées. Si nécessaire, query_intelligence par tour et round-trip HITL entier.
- [ ] Implémenter feedback et message metadata dans la même transaction, ressources
  applicatives synchronisées et mutations agent sous gate serveur existant.
  Le moteur d'ouverture n'appelle aucune de ces mutations de sa propre autorité.
- [ ] Implémenter les tools avec décorateurs, préparation native, gate et
  commandes propriétaires existants ; conserver la politique par défaut de
  confirmation des nouvelles écritures, sans ajouter d'exception globale.
  Émission de ressources `proactive_discussions` et `discussion_context` selon
  le résultat réellement commis ; paramètres admin non accessibles aux comptes ordinaires.
- [ ] GREEN : reprise pipeline/ReAct, HITL d'action ultérieure toujours requis,
  feedback reçu dans deux onglets, lien natif ordinaire inchangé ; aucun
  apprentissage de mémoire/habitudes à partir d'une supposition du moteur.

## Lot 9 — Réglages, chat et accessibilité frontend

**Créer :** `apps/web/src/hooks/useProactiveDiscussions.ts`,
`components/settings/ProactiveDiscussionsSettings.tsx`, petits composants
sources/historique/exclusions, `components/chat/DiscussionActions.tsx`, helpers
de présentation purs si l'extraction protège les hotspots.
Ajouter `hooks/useDiscussionContext.ts` et
`components/settings/discussion-context/{ContextList,ContextDetails,ContextUsage,
ContextPurgeDialog}.tsx`, avec responsabilité cohérente par composant plutôt
qu'un écran monolithique. Ces noms sont des propositions de fichiers futurs.
**Modifier :** `lib/{settings-sections,application-resources}.ts`,
`components/settings/settings-section-registry.tsx`, `hooks/useNotifications.ts`,
`components/chat/ChatMessage.tsx`, contrats Message/chat existants et six locales.
**Tests :** hook, composants et `apps/web/e2e/smoke/proactive-discussions.spec.ts`.

**Consomme :** API et permissions publiées ; aucun registre source client parallèle.
**Produit :** réglages, actions et présentation du nouveau type proactif.
La gestion de la base expose observations, épisodes et récurrences : filtres,
recherche, pagination, détails, sélection, statut utilisable/non utilisable,
purge ciblée/globale et remise en utilisation explicite.

- [ ] RED Vitest : liste dans l'ordre serveur, source indisponible/refusée
  distinguée, null « sans limite », saisie erronée annoncée ; activation ne
  modifie aucun réglage heartbeat ; modifications rapides ne perdent pas de choix.
- [ ] RED : changement de compte/unmount ignore toute réponse tardive, rollback
  de dernière écriture, refresh conserve champ/focus ; noms accessibles fr/en.
- [ ] RED : bulle `proactive_discussion` garde le thème de discussion, pas la
  teinte alerte héritée ; boutons et menu au clavier ; répondre garde le
  brouillon ; pause/sujet refusé suivent le bon ID, sans feedback heartbeat.
- [ ] RED de la base : consulter quand le moteur est off, filtres et total
  cohérents, détail d'un pattern avec ses occurrences, distinction qualification/
  statut d'usage ; marquer « Non utilisable » est conservé après reload et
  visible dans un autre onglet ; échec d'écriture ne montre pas un succès.
- [ ] RED : purge ciblée ou globale affiche portée exacte et confirmation,
  conserve sources/mémoires/exclusions, base vide après commit, aucune réindexation
  historique automatique immédiate ; réactivation reste un geste explicite.
  Concurrent update avant confirmation exige une nouvelle portée.
- [ ] GREEN E2E de contrôle réel : élément visible → non utilisable → évaluation
  simulée dont les entrées modèle l'excluent → reload → remettre en utilisation.
  Purge pendant reconstruction refuse la publication de l'ancien worker ; actions
  UI et tools produisent le même état. Fixtures entièrement fictives.
- [ ] Implémenter avec primitives existantes, hook de durée de vie du compte,
  API client et mises à jour sérialisées. Garder les contrôles focalisés montés,
  signaler aria-busy/aria-disabled avec garde d'exécution plutôt que blur.
- [ ] GREEN Playwright contrôlant API/SSE/FCM : succès, erreur puis reprise,
  doublon, reconnect, deux onglets, mobile 320 px et zoom/reflow, menu et retour
  focus. Absence d'API Notification/ServiceWorker en WebView ne lève pas d'erreur.
- [ ] Valider `task lint:frontend`, tsc sans incrémental, frontend coverage via
  Task, parité i18n, ratchets a11y/hooks/complexité et parcours E2E concernés.

## Lot 10 — Cycle de vie, non-régression et qualification relationnelle

**Modifier :** `domains/account_export/builder.py` et lecteurs propriétaires
nécessaires ; `domains/users/account_deletion_service.py`, reset/purge de
conversation, `infrastructure/cache/key_families.py` ; lecteurs notifications
de Radio et du briefing si la famille `proactive_*` les inclut.
**Créer :** corpus fictif et harness sans réseau dans tests du nouveau domaine ;
documentation technique, ADR de la fonctionnalité et carte documentaire selon
les templates courants du dépôt.
**Tests :** `test_lifecycle_pg.py`, `test_no_regression_flows.py`,
`test_editorial_corpus.py`, suites des lecteurs et exports affectés.

**Consomme :** fonctionnalité complète.
**Produit :** preuves de qualification, diagnostics et documentation à jour.

- [ ] RED : export contient préférences et ouvertures pertinentes ; effacement
  compte supprime contenus/claims/caches/exclusions et préserve la facturation
  selon le contrat existant ; reset invalide pending sans perdre préférences.
- [ ] RED : export/effacement couvrent observations/épisodes/patterns/exclusions
  d'usage, index, garde de correction et marqueurs de reprise ; source expirée
  ne survit pas dans un résumé dérivé ; purge ne perd pas les choix non utilisables.
- [ ] RED : expiration de texte peer/source ne permet pas sa reconstruction
  depuis audit ; audit de 30 j proposé purgé ; désactivation annule outbox
  non envoyée ; aucun message déjà envoyé effacé implicitement.
- [ ] RED : Radio/briefing ne récitent pas la nouvelle question ; alertes
  actuelles y restent ; compteurs et activité distinguent une ouverture d'un
  envoi par appareil ; historique/retour ne rejoue aucune performance avatar.
- [ ] Construire le corpus de la spec avec horloge injectée et preuves attendues.
  Tous les cas de confidentialité, identité, quotas et non-régression doivent
  passer ; les évaluations de ton et de pertinence ont un protocole humain
  documenté, sans score inventé ni oracle unique LLM.
- [ ] Mesurer les prompts rendus, coûts théoriques aux tarifs effectifs,
  nombre maximal de sources, latence et pool SQL sous sources lentes ; définir
  l'enveloppe financière et les seuils éditoriaux avant pilote.
- [ ] Exécuter `task lint`, backend fast xdist puis coverage séquentiel,
  `task test:markers`, `task test:frontend:coverage`, E2E affectés et
  `task ci:fast`. Ne pas lancer `test:backend:exhaustive`.
- [ ] Valider le runtime dans Docker DEV avec providers simulés, puis seulement
  si autorisé un probe réel court sur compte de preuve, sans retry ; distinguer
  modèle, archive, canal accepté, lecture et appréciation humaine.
- [ ] Mettre à jour docs/maps/facts seulement via leurs outils ; utiliser
  `lint:docs:preview` pour ce qui n'est pas stagé ; si CLAUDE change, régénérer
  AGENTS. Aucun relèvement de baseline ; chaque dette héritée est séparée des
  résultats de ce travail.

## Lot conditionnel — Source SMS

**SMS :** activer seulement après livraison et qualification du projet
`2026-10-19-phone-ingestion-sms`. Remplacer l'indisponibilité déclarée par un
lecteur propriétaire ; tests OTP/blocages/rétention/doublons/owner et inclusion
uniquement sur choix explicite. Les autres lots ne nécessitent pas cette source
pour fonctionner ; l'UI ne l'annonce pas disponible avant son installation.

## Ordonnancement et critères de sortie

Ordre : 1 → 2 → 3 → 3A → 3B → 3C → 4 → 5 → 6 → 7 → 8 → 9 → 10. Certaines vérifications
de facturation peuvent être écrites dès les lots sources, mais les appels réels
restent fermés jusqu'au lot 6. Les slots n'activent aucun job par leur création.
SMS reste un raccord conditionnel séparé.
La base contextuelle, ses règles, ses tools et sa gestion UI sont obligatoires
pour la V1 approfondie, pas un lot ultérieur facultatif.

Un lot est terminé avec ses preuves RED/GREEN, commandes exactes, décompte de
tests et warnings, limites et revue INLINE de ses contrats. Une couverture
unit-only ne clôt ni la concurrence SQL ni les canaux réels ni l'acceptabilité
humaine. L'activation progressive suit la validation produit et technique ;
aucune publication prod n'est autorisée par ce plan.

## Auto-revue du plan

- Couverture des demandes : toutes les familles de données ont un port ou une
  dépendance explicitement indisponible ; tous les contrôles utilisateur ont
  leurs lots API, UI et tests ; la recherche et la reprise humaine sont distinctes.
- Contrats cohérents : source/read au lot 3 ; snapshot/research au lot 4 ;
  LLM au lot 5 ; budget au lot 6 ; publication/runner au lot 7 ; reprise au lot 8.
  Stockage/usage au lot 3A, épisodes et récurrences au lot 3B, directives au lot
  3C ; gestion identique par API/tools au lot 8 et UI au lot 9.
- Risques implicites les plus probables affectés à des tests nommés : refus
  indirect, concurrence, opt-out/reset, réponse tardive et facturation silencieuse.
- Aucune exécution métier, migration, test payant ou déploiement réalisée
  pendant l'écriture du plan. Choix produit reçus et intégrés ; calibration,
  coût des modèles effectifs et preuves restent les portes techniques d'activation.
