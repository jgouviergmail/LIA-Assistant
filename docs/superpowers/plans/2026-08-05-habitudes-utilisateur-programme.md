# Programme « Habitudes utilisateur » — apprentissage des rythmes et récurrences

**Date** : 2026-08-05
**Statut** : **IMPLÉMENTÉ** (même jour, feu vert propriétaire) — voir
[ADR-214](../architecture/ADR-214-Habitudes-Utilisateur-Apprentissage-Deterministe.md).
Les 6 lots (0→5) sont livrés code + tests ; flag `HABITS_ENABLED` défaut OFF.
Ce dossier reste l'historique de l'enquête et la référence de calibration
(les seuils codés viennent des simulations §4 — les recalibrer impose de
rejouer le harnais).
**Nature** : dossier d'analyse + plan d'actions consolidé (pas un ADR, pas un changelog).

**Révision majeure post-implémentation (2026-08-05, constat propriétaire)** :
la conversation est ÉPHÉMÈRE par design (1 par utilisateur, resettable à
volonté) — `conversation_messages` n'est donc PAS la source primaire durable
que §2 supposait. Architecture corrigée : le rythme agrège l'UNION
(max-merge par heure) de trois sources — messages vivants ∪
`message_token_summary` (durable, 1 ligne/run, survit aux resets, **whitelist
des formes de sessions humaines** `session_%`/`channel_%`/UUID legacy — les
jobs tournent à heures fixes, un blacklist raté apprendrait le planning de
LIA elle-même) ∪ rollup `user_activity_days` (banque quotidienne,
alimentée AVANT toute décision de skip). Le déblocage est QUANTIFIÉ :
`required_n_eff` publié par classe (ADR-184) + barre de progression.

**Écarts d'implémentation vs plan** (assumés, documentés) :
- provenance des habitudes récurrentes : l'évidence est le payload agrégé
  (jours distincts, occurrences, R) — pas de `ProvenanceReference` par
  conversation (le ledger Redis ne conserve pas les ids de messages ; en
  fabriquer aurait été de la fausse provenance) ;
- CUSUM rétrogradé en V2 (la règle d'arrêt à 2 non-adhésions + le
  désapprentissage à 9 j bornent déjà le harcèlement — moins de pièces
  mobiles) ;
- priorisation de timing : v1 via le bloc « USER RHYTHM » du prompt de
  décision heartbeat (le LLM arbitre, bornes user-set rappelées dans le
  bloc) — le scoring mécanique de tick, initialement différé, a été livré
  ensuite (§11.2) derrière son propre flag défaut OFF ;
- validation du vocabulaire de domaine (`product_outcomes.domain`) déplacée
  au PRODUCTEUR (capture streaming) : product important `DOMAIN_REGISTRY`
  créait le cycle runtime agents↔product que le ratchet de couplage
  interdit.

---

## 1. Objectif produit

Permettre à LIA d'apprendre, de façon **fiable, explicable et contrôlable**, les
habitudes de l'utilisateur — périodes de connexion/discussion, demandes
récurrentes et leurs périodes — et de les exploiter pour améliorer la
proactivité (timing et pertinence des notifications), les suggestions
d'automatisation et la contextualisation des réponses.

Contraintes structurantes :

- **Prod = Raspberry Pi 5, 16 Go RAM** → aucun entraînement de modèle, aucun
  coût LLM d'apprentissage : statistiques déterministes uniquement.
- **Réutiliser l'existant** avant de créer (inventaire §2).
- **Contrôle utilisateur total** : activation, consultation, explication,
  correction, suppression, blocage — doctrine des intérêts.
- **Honnêteté** : une habitude affichée est prouvée ou n'existe pas (même
  doctrine que « un compte affiché est exact ou n'existe pas », ADR-185).

## 2. Inventaire vérifié des mécanismes existants (à réutiliser)

Chaque brique ci-dessous a été vérifiée dans le code le 2026-08-05.

| Brique | Preuve | Réutilisation dans ce programme |
|---|---|---|
| **Confiance bayésienne + seuils min-obs** — `PlanPatternLearner`, Beta(2,1), 3 obs/0.75 pour suggérer, 10 obs/0.90 pour bypass | `src/domains/agents/services/plan_pattern_learner.py:231-256` | Doctrine de montée en confiance des habitudes (signals positifs/négatifs + seuils settings) |
| **Modèle « appris par signaux » avec statuts et blocage** — `UserInterest` (positive/negative_signals, active/blocked/dormant, embedding, decay) | `src/domains/interests/models.py:55-161` | `UserHabit` imite ce modèle (statuts, signaux, unicité par user+clé) |
| **Explicabilité publiée** — la formule et ses coefficients exposés à l'utilisateur, jamais gamifiés | `src/domains/interests/explainability_router.py:1-25` | Même contrat pour les habitudes (formule + observations + incertitude) |
| **Provenance bornée avec tombstones** | `src/domains/shared/provenance_repository.py:1-13` | « D'où LIA tient cette habitude » ; la suppression d'une conversation source n'est jamais annulée |
| **Détecteur de récurrence déterministe** (ADR-140) — signature domaines+créneau 4 h, jours distincts, cooldown, Redis advisory | `src/domains/agents/services/recurrence_ledger.py:37-53,111-178` ; câblage `post_response_extractions.py:471-528` ; réglages `core/config/automation.py` | Socle du Lot 2 — étendu (verrous), persisté à la promotion |
| **Pipeline d'extraction post-réponse** — 6 familles gardées (`is_automated_source`, trivial), métriques par décision | `src/domains/agents/nodes/post_response_extractions.py:40-72` | Aucune 7e extraction nécessaire : le rythme se calcule en batch, la récurrence est déjà câblée |
| **Habitudes qualitatives** — `MemoryCategory.PATTERN` (« Recurring behaviors, habits ») | `src/domains/memories/models.py:53` | Déjà couvert ; la surface Habitudes y renvoie, pas de duplication |
| **Diffusion ambiante d'un portrait compilé** — bloc plein/bref injecté dans tous les flux, dégradation en `""` | `src/domains/journals/portrait_builder.py` | Pattern d'injection du bloc « rythme » (Lot 5) |
| **Heartbeat : famille « activity » non-source, jamais gatée** — aujourd'hui réduite à « dernier message + heures écoulées » | `src/domains/heartbeat/context_aggregator.py:937-965` ; doctrine `source_policy.py:38-45` | Point d'accueil naturel du bloc rythme dans la décision (Lot 4) |
| **Fenêtres horaires et quotas par utilisateur** (heartbeat + intérêts : start/end hour, min/max per day) | `src/domains/users/models.py:296-372` | Invariant : le rythme appris ne fait que **prioriser à l'intérieur** de ces bornes |
| **Ledgers de notifications avec feedback 👍/👎** | `heartbeat/models.py:19-120`, `interests/models.py:167-266` | Boucle de feedback implicite (signaux négatifs sur mauvaise fenêtre) |
| **Automations utilisateur** — `ScheduledAction` (days_of_week, trigger_hour/minute, tz, HITL) + drafts SCHEDULED_ACTION (P11) | `src/domains/scheduled_actions/models.py:77-210` | Cible de la suggestion préremplie (Lot 2) |
| **Vérité durable par run** — `product_outcomes` (user, produced_at, channel, device_class, state, GDPR-mappée) | `src/domains/product/models.py:25-92` ; purge `users/user_data_map.py:196` | Source secondaire de timing des demandes ; **seam à fermer** : `domain="unknown"` en dur (`product/service.py:129`) alors que `qi_primary` est disponible au même endroit du pipeline (`post_response_extractions.py:481`) |
| **Timestamps durables des discussions** — `ConversationMessage(role, created_at)` indexés | `src/domains/conversations/models.py:96-161` | Source primaire du rythme d'activité (couvre tous les canaux) |
| **Job nightly leader-elected** (pattern ×30) | `src/infrastructure/startup/schedulers.py` | Le job de recalcul du profil imite ce pattern |
| **Surfaces réglages à imiter** — InterestsSettings (blocage, historique), MemorySettings (pin/suppression/risque de purge), HeartbeatSourceSwitches, SectionToolbar/RowActions/EmptyState (ADR-206→208) | `apps/web/src/components/settings/` | Section « Habitudes » construite sur ces primitives |

**Ce qui n'existe pas** (le manque que ce programme comble) : aucune
représentation apprise du *quand* — le heartbeat décide sans savoir quand
l'utilisateur est habituellement là ; le détecteur de récurrence est éphémère
(Redis), aveugle aux habitudes hebdomadaires, et sa suggestion est un texte
générique non persistant, invisible dans les réglages.

## 3. Décision d'architecture : statistiques déterministes, pas de ML entraîné

Trois raisons convergentes, chacune suffisante :

1. **RPi5** : pas de budget pour entraîner/servir un modèle ; les statistiques
   proposées coûtent ~1 requête SQL agrégée + 1 UPSERT par utilisateur et par
   nuit, zéro LLM.
2. **Explicabilité exigée** (doctrine intérêts) : une présence par jour, une
   borne de Wilson et une sélectivité se publient à l'utilisateur ; un modèle
   entraîné, non.
3. **Volumes** : quelques centaines à quelques milliers de messages par
   utilisateur — un modèle apprendrait le bruit ; les tests statistiques avec
   seuils calibrés par simulation (§4) contrôlent précisément FP et FN.

## 4. Détecteurs proposés et validation par simulation

Harnais : `habit_sim4.py` (scratchpad de session, stdlib, seedé, 300 essais
par scénario). Utilisateurs synthétiques à vérité connue : réguliers (pics
8h30/21h30 semaine + 10h30 week-end, 10 % de bruit), nuls « éveil-uniforme »,
nuls « bloc quotidien aléatoire » (adversarial : 3 h d'activité placées au
hasard chaque jour), bavards uniformes, faible volume, cessation d'habitude.

### 4.1 Rythme d'activité (fenêtres actives par classe de jour)

Unité statistique = **le jour** (immunise contre le clustering intra-journée,
défaut mesuré des approches par message). Par classe (semaine/week-end),
fenêtre glissante 56 j, poids exponentiels demi-vie 14 j :

- candidates = fenêtres (début 0-23 h × longueur 2-4 h) ;
- revendicable si : présence pondérée ≥ 0.55 **et** borne de Wilson 99 % ≥ 0.35
  **et** présence récente (14 j) ≥ 0.30 **et** cohérence split-half (présence
  ≥ 0.45 sur chaque moitié des jours) ;
- sélection gloutonne par **capture marginale**, total plafonné à 6 h ;
- gate décisif de **sélectivité** : part d'activité capturée ≥ 0.6 et
  capture/part-de-journée-de-référence (16 h) ≥ 1.9 — c'est ce test qui rend
  la revendication informative (un utilisateur uniforme capture ≈ sa part →
  rejeté) ;
- **hystérésis** : une fenêtre déjà revendiquée se retient à seuils relâchés
  (0.45/0.50/1.6) — anti-flapping ;
- effectif minimal (Kish) : 12 jours-semaine / 6 jours-week-end, sinon verdict
  « insuffisant » (l'UI dit « en apprentissage », jamais une habitude inventée).

Résultats mesurés (300 essais/scénario) :

| Métrique | 21 j | 28 j | 56 j |
|---|---|---|---|
| FP éveil-uniforme | 0 % | 0.3 % | 0 % |
| FP bloc-aléatoire (null extrême) | 1.7 % | 9.0 % | 4.3 % |
| FP bavard-uniforme | 0 % | 0 % | 0 % |
| Détection pic matin / soir (régulier) | 98.0 / 99.3 % | 98.7 / 99.0 % | 100 / 100 % |
| Détection week-end | — (données insuffisantes, voulu) | 89.3 % | 98.7 % |
| Erreur de phase | 0.00 h | 0.00 h | 0.00 h |

Désapprentissage après cessation : médiane **9 j**, p90 9 j, aucun blocage.
Stabilité : perte de revendication sur **0.18 %** des contrôles quotidiens
(habitude continue). Faible volume (~1.5 msg/j) : aucune fenêtre revendiquée —
**voulu** : « habituellement actif à H » serait factuellement faux pour un
utilisateur présent moins d'un jour sur deux ; son profil de *distribution*
(les histogrammes) reste disponible pour une formulation honnête (« quand il
écrit, c'est plutôt le matin »).

### 4.2 Demandes récurrentes (extension d'ADR-140)

Défauts mesurés du détecteur actuel : une habitude **hebdomadaire n'est jamais
détectée** (0/300 — fenêtre 14 j < 3 lundis) ; le créneau fixe 4 h coupe les
habitudes à cheval sur une frontière ; la suggestion ne porte aucune heure ni
aucun jour (rien à préremplir).

Proposition v2 (rétrocompatible, mêmes points de câblage) :

- signature **sans créneau horaire** (domaines seuls) — l'heure devient une
  *mesure*, plus une clé ;
- **stockage par JOUR, plus par occurrence** (contre-revue 2026-08-05) : le
  cap actuel de 20 *occurrences* saturé par un domaine sollicité 3×/jour ne
  retient que ~7 jours d'historique → la condition « étalement ≥ 10 j » du
  time-lock devient inatteignable pour un utilisateur intensif (FN structurel,
  invisible de la simulation qui ne modélisait pas le cap). Nouvelle entrée =
  (jour local, heures plafonnées à 5) ; cap = `recurrence_window_days` (28)
  entrées — jours distincts exacts, R calculé sur les heures stockées,
  équivalent à ce que la simulation a mesuré ;
- existence : ≥ 4 jours distincts sur 28 j (advisory, interne) ;
- **verrous réévalués chaque jour**, seuls déclencheurs d'une suggestion
  visible :
  - *time-lock* : ≥ 8 occurrences, étalées sur ≥ 10 j, R circulaire ≥ 0.8 **et**
    cohérence split-half (deux moitiés R ≥ 0.7, moyennes à ≤ 2 h) ;
  - *weekly-lock* : ≥ 4 jours distincts sur le même jour de semaine, ≥ 75 % ;
  - *daily/workdays* : étiquetage différé à ≥ 14 jours distincts, « workdays »
    si ≤ 1 jour de week-end.

Résultats mesurés (horizon 56 j) :

| Scénario | Verdict attendu | Obtenu | Jour médian | Erreur d'heure |
|---|---|---|---|---|
| Quotidien 9 h | daily | **99.7 %** | 15 | 0.13 h |
| Hebdo lundi 9 h | weekly | **90.7 %** (résiduel : détecté plus tard) | 21 | 0.24 h |
| Quotidien 12 h (frontière de bucket) | daily | **99.7 %** | 15 | 0.16 h |
| Jours ouvrés 9 h | workdays | **100 %** | 21 | 0.13 h |
| Étalé sans heure (2/j au hasard) | aucune suggestion | **100 % silencieux** | — | — |
| Sporadique (2/sem au hasard) | aucune suggestion | **100 % silencieux** | — | — |

Le point produit décisif : **0 % de suggestion à tort** sur les usages sans
structure temporelle — la suggestion préremplie (jours + heure) n'est émise
que verrouillée, et elle reste un draft HITL que l'utilisateur édite.

Tous les seuils ci-dessus (§4.1, §4.2) deviennent des settings env-overridable
(`HABITS_*`) avec ces valeurs par défaut ; le harnais de simulation est versé
en annexe du dossier pour re-calibrer.

## 5. Architecture cible

### 5.1 Nouveau bounded context `domains/habits/`

- `models.py` :
  - `UserHabitProfile` (1 ligne/user) : histogrammes présence-par-jour
    (7×24 en JSONB compact, ~2-6 Ko), fenêtres revendiquées par classe,
    verdicts (`windows`/`diffuse`/`insufficient`), méta (fenêtre, n_eff,
    computed_at). Recalculé — jamais muté en place (règle JSONB : nouveau dict).
  - `UserHabit` (habitudes discrètes) : `kind` (enum `HabitKind` :
    `active_window` | `recurring_request`), `key` (classe+fenêtre ou signature
    domaines), `payload` JSONB (schéma Pydantic versionné), `positive_signals`/
    `negative_signals` (feedback), `status` (`active`/`paused`/`blocked`),
    `last_observed_at`, contrainte unique (user, kind, key). Provenance via
    `ProvenanceRepository`.
- `repository.py` / `service.py` (détecteurs §4 en fonctions **pures** testées
  en table, I/O séparée) / `router.py` (list, explanation, pause, block,
  delete, delete-all) / `schemas.py`.
- Config `core/config/habits.py` + flag global `HABITS_ENABLED` (défaut
  **false**) + préférence utilisateur `habits_enabled` (défaut true, gatée par
  le flag). Tout mapping keyé sur `HabitKind` reçoit un assert de complétude au
  boot (ADR-085).

### 5.2 Calcul : batch nightly, zéro hot path

Job `infrastructure/scheduler/habit_profile_job.py` (leader-elected, flag-gaté,
enregistré dans `startup/schedulers.py` avant `leader_elector.start()`) :

- par utilisateur actif, **une** requête d'agrégation SQL sur
  `conversation_messages` (role='user', 56 j, `AT TIME ZONE` la tz utilisateur,
  GROUP BY dow/heure + comptes par jour) — ~168 lignes ramenées, pas les
  messages ; puis détecteur pur + UPSERT du profil et des `UserHabit` dérivées
  (hystérésis : une habitude existante se retient aux seuils de sortie) ;
- sessions DB : une par utilisateur, jamais partagée (règle AsyncSession) ;
- messages de sources automatisées exclus — **piège confirmé** : l'exécuteur
  d'actions programmées archive un message `user` synthétique
  (`scheduled_action_executor.py:352-356`, `archive_user_message=(attempt==1)`) ;
  sans exclusion, une action quotidienne à 7 h apprendrait « utilisateur actif
  à 7 h » (boucle de rétroaction sur ses propres automatisations). Discriminant
  déterministe : sessions préfixées `scheduled_action_`
  (`core/constants.py:493`, déjà exploité par `derive_channel`) ; l'exclusion
  SQL exacte (jointure ou métadonnée) se fixe au Lot 1 avec un test dédié
  anti-rétroaction ;
- coût RPi5 : < 1 s/user/nuit, zéro LLM, mémoire négligeable.

La récurrence (Lot 2) garde son écriture fire-and-forget existante
(`post_response_extractions.py`) ; la **promotion** en `UserHabit` persisté se
fait au moment du verrou (le ledger Redis reste advisory ; les habitudes
promues survivent désormais à un flush — résilience nouvelle vs ADR-140).

### 5.3 Consommation (chaque canal derrière le flag + la préférence)

1. **Heartbeat — contexte de décision** : bloc « rythme » (fenêtres actives,
   fenêtre courante ou prochaine) rejoint la famille `activity`
   (non-source, jamais gatée — doctrine `source_policy.py`) ; le prompt lit
   les valeurs via placeholders settings (ADR-184, jamais de nombre en prose).
2. **Timing des notifications** : score de préférence pour les ticks dans une
   fenêtre apprise, **à l'intérieur** des bornes utilisateur — jamais un gate
   dur. Invariant anti-famine testé : à l'approche de la fin de fenêtre
   utilisateur, la préférence s'efface (le `min_per_day` reste garanti).
   Intersection vide (fenêtre apprise ∩ bornes utilisateur = ∅) → score
   neutre, comportement identique à aujourd'hui (testé).
   Implémenté dans la sélection des tâches proactives, **pas** dans
   `EligibilityChecker` (partagé — risque n°1 documenté d'ADR-135).
3. **Suggestion d'automatisation** : verrou → draft `SCHEDULED_ACTION`
   prérempli (days_of_week + trigger_hour appris, tz utilisateur), HITL,
   cooldown existant ; accepté/écarté alimente positive/negative_signals.
4. **Briefing** : mention du rythme dans les entrées de synthèse ; piège
   documenté : les trois consommateurs cachés de `CardsBundle` (`_iter_cards`,
   `_read_cards_from_cache`, `_has_content`) si une section est ajoutée.
5. **Contexte conversationnel (Lot 5, après mesure)** : bloc ambiant bref
   (~40 tokens) façon `portrait_builder` (dégradation en `""`), avec surface
   panneau de debug déclarée (règle : toute injection par requête déclare
   cache → émission → section).

### 5.4 Réactions mesurées aux écarts (demande propriétaire 2026-08-05)

L'assistant réagit **sobrement** quand la réalité s'écarte d'une habitude à
haute confiance — la preuve vécue qu'il connaît son utilisateur. Trois types
autorisés, chacun cadré comme un **service rendu**, jamais comme une
observation de surveillance :

1. **Routine verrouillée manquée** (le plus utile) : le créneau habituel d'une
   demande récurrente verrouillée passe sans demande → le heartbeat peut
   proposer UNE fois : « D'habitude tu me demandes X le lundi matin — je te le
   prépare ? ». Coût d'un faux positif très bas (c'est une offre, pas une
   affirmation).
2. **Session à heure inhabituelle** : activité dans une plage de présence ~0
   (surprisal élevé) → remarque légère intégrée à la réponse en cours
   (« il est tard — version courte ? ») + adaptation du format. Jamais une
   notification.
3. **Retour après absence anormale** (écart >> intervalle typique) : accueil
   bref + digest de ce qui s'est passé — service, pas commentaire.

**Exclusions explicites** : aucun commentaire sur les patterns de connexion
sans valeur de service (« tu te connectes moins » = interdit) ; les dérives
lentes (habitude qui s'estompe) se traitent en SILENCE (rétrogradation par
l'hystérésis, jamais une remarque).

Mathématique de détection (triviale, pas de nouveau détecteur) : surprisal
sous le profil appris — k créneaux attendus manqués consécutifs sur une
habitude de présence p̂ → P = (1-p̂)^k, avec **k dépendant de la forme**
(contre-revue 2026-08-05) : habitude quotidienne k=2 (k=1 à p̂=0.85 produirait
~1 fausse remarque/semaine ; k=2 → ~1 toutes les 7-8 semaines), habitude
hebdomadaire k=1 (l'offre au créneau manqué a de la valeur immédiate ;
~1/10 semaines à p̂=0.9). **Règle d'arrêt sur non-adhésion** : une offre
type 1 émise sans que la routine soit ensuite demandée compte comme signal
négatif implicite ; 2 non-adhésions consécutives → type 1 muet pour cette
habitude jusqu'à ré-occurrence positive. C'est elle qui borne le harcèlement
sur une routine abandonnée à **2 remarques maximum** (le désapprentissage à
9 j fait le reste). La dérive soutenue se traite par l'hystérésis existante ;
un CUSUM dédié est rétrogradé en option V2 (complexité non justifiée une fois
la règle d'arrêt en place).

**Garde-fous anti-lourdeur (le cœur de la demande)** :
- budget global : ≤ 1 remarque d'écart/jour, ≤ N/semaine (settings), imputé
  aux quotas heartbeat existants ;
- uniquement les habitudes `active` à confiance ≥ palier « suggest » ;
  cooldown par habitude (défaut 7 j) ;
- type 1 = **source gatée** « habits » ajoutée à `HEARTBEAT_SOURCE_KEYS`
  (l'utilisateur peut couper « LIA peut m'interrompre sur mes habitudes »
  sans couper l'apprentissage — doctrine source_policy) ; types 2-3 = voie
  ambiante (Lot 5), directive de sobriété dans le prompt ;
- toggle dédié « remarques sur les écarts » sous le master toggle habitudes ;
- 👍/👎 sur ces notifications → negative_signals de l'habitude (ledger
  existant) ; la décision finale notifier/se taire reste au LLM de décision
  heartbeat — les statistiques fournissent des évidences, jamais une
  obligation d'émettre.

Volumétrie attendue : avec 2-3 habitudes verrouillées et les budgets par
défaut, ~≤ 2 remarques/semaine dans le pire cas.

### 5.5 Contrôle utilisateur (parité avec les intérêts)

Section réglages « Habitudes » : master toggle ; liste par kind avec libellé
lisible (« Actif en semaine 8 h-10 h », « Demande e-mails chaque lundi ~9 h ») ;
« Pourquoi ? » = observations, formule et incertitude publiées (doctrine
explicabilité) + provenance (extraits vivants, tombstones) ; actions par ligne
(`RowActions`) : suspendre, bloquer (ne jamais réapprendre cette clé),
supprimer ; barre (`SectionToolbar`) : tout effacer (step-up destructif),
export ; état « en apprentissage » via `EmptyState` avec `reason`. i18n ×6,
a11y (noms accessibles stables), e2e hermétique.

RGPD : les deux tables entrent dans `user_data_map.py` (`_PURGED_FULL`), le
service de suppression de compte et l'export (`account_export`). Logs : IDs et
compteurs à INFO, jamais d'heures nominatives corrélées à du contenu.

## 5.6 Hétérogénéité des profils d'usage (note propriétaire 2026-08-05)

Trois profils coexistent : intensif, intermédiaire, occasionnel. Le design
les absorbe **par construction** — tous les seuils sont des taux (présence =
fraction de jours, jamais des comptes de messages) et l'unité statistique est
le jour : un utilisateur bavard ne « prouve » pas une habitude plus vite, un
occasionnel n'est pas pénalisé par son volume mais par sa couverture réelle.
Matrice de valeur par profil :

| Profil | Rythme (fenêtres) | Récurrences | Écarts | Expérience réglages |
|---|---|---|---|---|
| Intensif régulier | ✓ (98-100 % dès 21-28 j) | ✓ | ✓ (budgets) | habitudes complètes |
| Intensif sans structure | verdict `diffuse` honnête | ✓ si rituels | type 2-3 seulement | « pas d'habitude horaire » |
| Intermédiaire (3-4 j/sem) | ✓ si présence ≥ seuils (hystérésis stabilise le bord) | ✓ | ✓ | habitudes partielles |
| Occasionnel ritualisé (ex. chaque lundi) | ✗ voulu (la revendication serait fausse) | **✓ — cas mesuré `weekly_monday_9h` : 90.7 %** | type 1 sur la routine verrouillée | récurrences seules |
| Occasionnel erratique | ✗ | ✗ (0 % suggestion à tort mesuré) | aucun (rien de verrouillé) | « usage occasionnel », comportement identique à aujourd'hui |

Quatre raffinements induits :

1. **Verdict `sparse` distinct** : fraction pondérée de jours actifs < 30 % →
   l'UI dit « usage occasionnel — fenêtres horaires non applicables ; les
   récurrences restent détectées », au lieu d'un `none` ambigu qui laisserait
   croire à un échec d'apprentissage.
2. **Absence anormale RELATIVE** (écart type 3) : le seuil de « retour après
   absence » se calcule sur la distribution des intervalles inter-sessions de
   l'utilisateur (p90 × facteur settings), jamais en absolu — un occasionnel
   ne doit pas recevoir un « bon retour ! » condescendant à chaque visite
   normale pour lui.
3. **Job nightly en delta** : aucun nouveau message utilisateur depuis le
   dernier calcul → recalcul sauté (comparaison d'un simple max(created_at)).
   Avec une base majoritairement occasionnelle, le coût RPi5 tend vers zéro.
4. **Mesure J+14 segmentée par profil** (intensif/intermédiaire/occasionnel,
   dérivé du taux de jours actifs) — une moyenne globale masquerait une
   mauvaise expérience d'un segment.

## 6. Edge cases traités (et comment)

| Cas | Traitement |
|---|---|
| Changement de timezone / DST | Recalcul nightly depuis UTC + tz **courante** → auto-résorbé en une nuit ; ZoneInfo gère le DST ; jours de 23/25 h : biais négligeable, documenté |
| Voyage sans changement de tz | Dérive amortie par demi-vie 14 j + hystérésis ; `last_known_location` existe si un jour on veut mieux |
| Nouvel utilisateur | « insufficient » avant ~3 semaines — affiché « en apprentissage », jamais inventé |
| Faible volume | Pas de fenêtre revendiquée (elle serait fausse) ; distribution seule, formulation adaptée |
| Utilisateur sans habitude (uniforme/bavard) | Verdict `diffuse`/`none` explicite — c'est une information, pas un échec |
| Cessation d'habitude | Désapprentissage médian 9 j (mesuré) ; `paused` automatique avant suppression ? Non : statut `active` retiré par le job, la ligne reste consultable `dormant`-like via `last_observed_at`, purge au-delà d'un TTL settings |
| Suppression de conversations (droit à l'oubli) | Le recalcul suit la source : les messages supprimés sortent du profil à la nuit suivante ; provenance en tombstone |
| Messages automatisés / canaux | Exclusion **obligatoire** des messages `user` synthétiques des actions programmées (préfixe de session `scheduled_action_`, constants.py:493) — test anti-rétroaction dédié ; tous les canaux humains (web, Telegram, voix) convergent en `ConversationMessage` → couverts |
| Travailleurs postés / semaines alternées | Présence par créneau ~50 % → sous le seuil 0.55 → verdict `none`/`diffuse` : **silence plutôt qu'une revendication fausse** (limitation documentée, v2 possible par périodicité 14 j) |
| Redis flush | Ledger advisory inchangé ; habitudes promues en Postgres |
| Concurrence | Job leader-elected, une session/tx par utilisateur, UPSERT ; aucune écriture concurrente sur le profil |
| Croissance non bornée | Fenêtre glissante 56 j ; cap d'habitudes par kind (settings) ; profil à taille fixe |
| Conflit rythme appris / réglages explicites | Les bornes utilisateur priment toujours ; le rythme ne fait que prioriser dedans (test dédié) |

## 7. Non-régression (gates de sortie de chaque lot)

- `HABITS_ENABLED` défaut **false** : arbre de comportement strictement
  identique tant que le flag est éteint (test de non-câblage).
- Aucune écriture nouvelle sur le hot path de chat (le seul delta hot-path est
  Lot 0 : un paramètre `domain` passé à un appel fire-and-forget existant).
- Heartbeat : bloc contexte ajouté seulement si flag+pref+profil ; sinon `""`
  (pattern portrait). Tests : jamais d'élargissement des fenêtres user-set ;
  invariant anti-famine du `min_per_day`.
- Ratchets : nouveaux fichiers < 600 SLOC ; CC < 15 (détecteurs découpés en
  fonctions pures) ; aucun cap relevé ; couverture ≥ plancher, relevée après.
- Round-trip test sur le payload `UserHabit`/profil (règle sérialisation).
- Gates par lot : `task lint`, `task test:backend:unit:fast`,
  `task db:migrate:replay-check` (migrations), `task test:frontend` +
  ratchets (Lot 3), `task ci:fast` avant chaque rendu, preuve runtime Docker.

## 8. Plan d'actions (lots ordonnés, processus invariant)

Processus par lot (non négociable, doctrine maison) : spec courte → **feu vert
utilisateur** → TDD → gates → preuve runtime Docker → release → mesure J+14
pour les lots proactifs.

- **Lot 0 — fondations (petit, 1 session)** : fermer le seam
  `product_outcomes.domain` (passer `qi_primary` du pipeline post-réponse à
  `record_outcome_produced` — bénéfice double analytics/habitudes) ;
  **marquer les messages user synthétiques** (contre-revue 2026-08-05 :
  `_archive_user_message_first` ne stocke que `{run_id, attachments}` —
  `agents/api/service.py:396-398` — un message d'action programmée est
  aujourd'hui indistinguable d'un message humain, et la conversation étant
  1:1 par utilisateur — `conversations/service.py:68-69` — aucune
  discrimination par conversation n'est possible) : quand
  `is_automated_source=True`, ajouter `automated_source: true` au
  `message_metadata` (constante `field_names`) + test ; l'historique non
  marqué sort de la fenêtre 56 j avant toute consommation (Lots 1/4
  postérieurs) — auto-assainissement, pas de backfill ; ADR-214 ; décision
  d'activation de `RECURRENCE_SUGGESTION_ENABLED` en dev pour commencer à
  collecter.
- **Lot 1 — domaine habits + profil de rythme (2 sessions)** : bounded context,
  migration (2 tables + pref user), job nightly, config seuils (§4.1), GDPR ×3
  (purge/suppression/export), métriques Prometheus, tests table-driven des
  détecteurs purs (vecteurs issus du harnais §4). Flag OFF.
- **Lot 2 — récurrences v2 + promotion (1-2 sessions)** : verrous (§4.2) dans
  `recurrence_ledger`, promotion `UserHabit`, provenance, draft
  `SCHEDULED_ACTION` prérempli, feedback → signaux.
- **Lot 3 — surface utilisateur (1-2 sessions)** : réglages « Habitudes »
  (§5.4), hooks `useHabits`, i18n ×6, e2e, a11y. C'est le lot qui autorise
  l'activation du flag (le contrôle précède l'exploitation).
- **Lot 4 — consommation proactive (1-2 sessions)** : bloc rythme heartbeat,
  scoring de timing, briefing, **écarts type 1** (routine manquée, source
  gatée « habits », budgets §5.4) ; activation en dev puis prod ; **mesure
  J+14** (part des notifications dans les fenêtres apprises, feedback 👍/👎
  avant/après, taux de remarques d'écart et leur accueil).
- **Lot 5 — contexte conversationnel (optionnel, après mesure)** : bloc
  ambiant bref + **écarts types 2-3** (heure inhabituelle, retour d'absence)
  + surface debug panel.
- **V2 possible (post-mesure, non engagée)** : Thompson sampling (Beta) sur le
  choix du créneau d'envoi à l'intérieur des fenêtres apprises, récompensé par
  le feedback existant — même famille bayésienne que `PlanPatternLearner`,
  coût négligeable ; périodicités non hebdomadaires (quinzaine) par
  périodogramme si le besoin est observé.

Ordre de valeur : Lots 1+3 donnent déjà « LIA me connaît et me le montre » ;
Lot 4 est le gain de proactivité mesurable ; Lot 2 est le gain d'automatisation.

## 9. Positionnement état de l'art (analyse 2026-08-05)

Pour la classe de problème « modélisation d'habitudes par utilisateur, faible
volume de données, exigence d'explicabilité, matériel contraint », l'état de
l'art industriel (suggestions on-device des assistants mobiles, timing de
notifications des apps grand public) est précisément la famille retenue :
règles statistiques conservatrices + confiance bayésienne + priorité à la
précision sur le rappel. Détail par technique :

| Dans le plan | Alternative « état de l'art » | Arbitrage |
|---|---|---|
| Statistiques circulaires (R, moyenne circulaire) | von Mises / test de Rayleigh — identique en substance | Retenu (standard pour données horaires périodiques) |
| Détection daily/weekly par concentration jour-de-semaine | Périodogramme (Lomb-Scargle/chi²) détectant toute période | Les deux périodes qui comptent (24 h, 7 j) sont couvertes exactement ; le périodogramme = V2 si un besoin (quinzaine) est observé |
| Décroissance exponentielle + hystérésis (désapprentissage 9 j mesuré) | Détection de rupture bayésienne en ligne (BOCPD) / CUSUM | CUSUM léger ajouté pour la dérive soutenue (§5.4) ; BOCPD complet disproportionné pour l'enjeu |
| Bornes de Wilson, taille effective de Kish, split-half | Standards de fiabilité statistique | Retenus tels quels |
| Scoring déterministe du créneau d'envoi | Bandit contextuel / Thompson sampling (pratique publiée du timing de notifications) | V2 optionnelle post-mesure : Thompson Beta sur les créneaux, récompense = feedback existant — même famille que `PlanPatternLearner`, coût ~nul |
| Écarts par surprisal (1-p̂)^k | Détection d'anomalies probabiliste avec contrôle FDR | Le surprisal + budgets + cooldowns EST la version FDR-pragmatique à cette échelle |
| **Refusé** : modèles de séquence profonds (LSTM/Transformer) pour prédire la prochaine action | État de l'art académique en prédiction de comportement | Inadapté : sur-apprentissage à ces volumes, inexplicable, coût RPi5, et le produit ne demande pas de prédire le contenu |
| **Refusé** : apprentissage fédéré / cross-utilisateurs | Pertinent à l'échelle de millions d'utilisateurs | Sans objet ici ; les habitudes restent strictement per-user |

Conclusion : à périmètre et contraintes donnés, le plan est à l'état de l'art
*utile* ; les deux seuls emprunts supplémentaires justifiés (CUSUM de dérive,
bandit de créneau) sont respectivement intégré (§5.4) et proposé en V2.

## 10. Ce que ce programme ne fait pas (périmètre gelé)

- Pas de corrélations inter-signaux (santé×agenda longitudinal = P16, gelé
  post-mesure du programme interdomaine).
- Pas d'apprentissage cross-utilisateurs (les habitudes sont strictement
  per-user ; seul `PlanPatternLearner` reste cross-user et anonyme).
- Pas de rotation de la requête mémoires du heartbeat (limitation documentée
  d'ADR-135, hors périmètre).
- Pas de prédiction de contenu (on apprend *quand* et *quoi de récurrent*,
  pas *ce que l'utilisateur pense*).

## 11. Validation adversariale sur données réelles (2026-08-05, post-implémentation)

Le détecteur réel a été exécuté sur les agrégats jour×heure des trois comptes
de prod (extraction SSH lecture seule, comptages uniquement). Verdicts :

- **Détecteur : validé.** `n_eff` est le Kish des poids calendaires (chaque
  jour de classe observé compte, actif ou non — l'absence est une donnée) ;
  deux comptes non clippés partagent donc le même `n_eff` par construction.
  Aucune fenêtre revendiquée sous le plancher ; les gates tiennent.
- **Ingestion : faux positif réel prouvé, corrigé.** Une action programmée
  quotidienne écrivait 1 message rôle-user à 07:00 depuis 66 jours sur un
  compte réel (66/66 corrélés `scheduled_action` par `run_id`) → le détecteur
  revendiquait « 06:00-08:00 ». Correctif : filtre `NOT EXISTS` run→session
  (même whitelist que les summaries) sur la source messages ; le métronome
  disparaît, verdict honnête `sparse`. Coût : 1,3 ms (RPi5).
- **Resets = présence humaine par construction, ajoutés comme 3ᵉ source.**
  `reset_conversation` n'a qu'un appelant (endpoint authentifié) ; 124 jours
  distincts sur le compte principal contre ≤ 4 via messages/summaries. Sans
  eux : `sparse` à tort ; avec : `none` exact (présent, sans heure fixe).
- **Libellé de progression corrigé** : `n_eff` compte des jours
  d'OBSERVATION (calendrier), pas des jours d'activité — les 6 locales disent
  désormais « jours d'observation ».
- **Population réelle actuelle** : aucun compte ne porte de fenêtre légitime
  aujourd'hui (usage chat épars, poussé par les canaux proactifs) — le
  déblocage viendra du volume, la barre de progression le quantifie, et les
  récurrences restent la granularité utile.

Détail des mesures : ADR-214, section « Amendement 2026-08-05 ».

### 11.1 Lot « progression des récurrences » (2026-08-05, même session)

Suite aux arbitrages propriétaire post-validation :

- **Candidats en observation** : `GET /habits` publie désormais les
  signatures que le ledger a vues mais pas encore verrouillées
  (`candidates` + `candidates_more`), avec le seuil d'existence RÉELLEMENT
  appliqué (`recurrence_min_distinct_days`, ADR-184). Le module
  `habits/candidates.py` lit Redis par le contrat de clé (agents importe
  déjà habits pour la promotion — l'import inverse fermerait le cycle) ;
  contrat épinglé par `test_candidates_ledger_contract.py` (3ᵉ site lecteur
  après agents et heartbeat). Cap d'affichage paramétrable
  (`HABITS_CANDIDATES_DISPLAY_MAX`, défaut 5), reste COMPTÉ. Au-delà du
  seuil de volume, l'UI affiche « régularité en cours de confirmation » —
  un verrou n'est pas une progression linéaire, prétendre l'inverse serait
  un mensonge. Front : primitive `ObservationProgress` partagée avec la
  barre de déblocage du rythme.
- **Rangée d'actions** : « Recalculer maintenant » (CTA solide thémé,
  ADR-207) à gauche de « Tout oublier » (destructif solide), même
  géométrie, même rangée ; « Recalculer » reste accessible avant le premier
  calcul (point d'entrée du rétroactif).
- **`.env.prod.example`** : l'écart avec `.env.example` est INTENTIONNEL
  (commentaire en tête du bloc [75b]) — la surface opérateur prod n'expose
  que le flag et l'heure du job, les seuils calibrés restent aux défauts.
- **Scoring mécanique de tick (5ᵉ niveau)** : analysé ici, puis IMPLÉMENTÉ
  dans la foulée — voir §11.2.

### 11.2 Scoring de tick — IMPLÉMENTÉ (2026-08-05, même session)

Point d'insertion : `HeartbeatProactiveTask.check_eligibility` (les checks
communs — fenêtre user-set, quota, cooldown, lissage probabiliste — restent
dans EligibilityChecker, le scoring N'y entre PAS : piège ADR-135).
Livré :

- règle pure `should_defer_tick` (`heartbeat/habit_context.py`) : différer
  un tick hors fenêtre apprise UNIQUEMENT si une entrée de fenêtre reste
  atteignable AUJOURD'HUI avant la fermeture des bornes utilisateur, avec
  la marge d'un intervalle de tick (anti-famine ; bornes wrap-minuit →
  plafond conservateur à minuit, jamais de report vers demain) ; l'heure 0
  est une borne VALIDE (bug `or` attrapé en revue : minuit lu comme absent
  aurait différé vers une fenêtre hors bornes — figé par test) ;
- gate async `should_defer_tick_for_rhythm` : flag dédié
  `HABITS_TICK_SCORING_ENABLED` (défaut OFF, exposé dans les DEUX env
  examples — attention opérateur), `habits_enabled` système ET préférence
  utilisateur (ajoutée à `_extract_user_settings` du runner), verdict
  `windows` exigé (des fenêtres sans le verdict = payload corrompu, ne
  pilotent jamais le timing), classe de jour locale, fail-open sur toute
  erreur ;
- métrique `heartbeat_ticks_deferred_total{day_class}` + log debug ;
- la garantie de minimum du lisseur probabiliste reste intacte : les ticks
  en fenêtre et post-fenêtre ne sont jamais différés.

Interaction prouvée par tests (24) : géométrie table-driven wrap inclus,
flag OFF sans round-trip DB, verdicts non-windows, week-end, erreur de
stockage. Preuve vivante dev : flag OFF par défaut → comportement inchangé ;
flag ON sur le profil réel (`none`) → jamais différé. Thompson sampling
(récompense = feedback déjà câblé) reste la V2+ documentée §9.

### 11.3 Lot « durabilité + visibilité » (2026-08-05, même session)

Trois volets livrés après le scoring de tick :

- **Factorisation préalable** : le FORMAT du ledger de récurrence
  (clé, payload par jour, caps, TTL, legacy) descend dans
  `infrastructure.cache.recurrence_store` — agents (sémantique),
  heartbeat (jours d'occurrence) et habits (candidats, seed) consomment le
  même module ; les trois littéraux dupliqués disparaissent, les tests de
  contrat restent en non-régression bout-en-bout.
- **Seed du ledger depuis `product_outcomes`** (`habits/ledger_seed.py`) :
  un ledger VIDE (flush Redis, ou premier recompute post-déploiement) se
  reconstruit depuis la vérité durable — même whitelist humaine par
  run→summary que toutes les sources (le métronome scheduled_action ne
  seed jamais), `domain <> 'unknown'` (l'historique non labellisé
  n'invente rien), write NX (le vivant prime), caps + TTL du store,
  SELECT sous SAVEPOINT (un échec n'empoisonne pas la transaction du
  recompute — piège ADR-204 attrapé en revue). Limite énoncée : les
  signatures composées (« email+contact ») réapprennent en live,
  `product_outcomes` ne porte que le domaine primaire. Branché dans le
  recompute AVANT le delta-skip (nightly + bouton Recalculer). Preuve
  vivante dev : seed réel → le `evaluate_locks` d'agents lit les jours
  seedés → verdict honnête → nettoyage.
- **Heatmap 24 créneaux** : `bin_presence` publié par classe dans
  l'overview ; le panneau rend une rangée de 24 cellules (intensité
  normalisée au créneau le plus fort, `role="img"` + libellé i18n,
  masquée à zéro présence) — le « où » de l'activité reste visible même
  sur un verdict `none`.
- **Provenance honnête des habitudes récurrentes** : l'explication publie
  les JOURS D'OCCURRENCE réels du ledger (la base exacte du verrou), avec
  dépassement compté ; toujours AUCUNE référence de conversation fabriquée
  (le ledger ne garde pas d'ids de messages — écart assumé maintenu).
  Nouvelle surface front `HabitExplanation` (pattern InterestExplanation :
  disclosure plié, fetch à l'ouverture, seuils appliqués publiés,
  masqué téléphone).

La contre-revue du lot a corrigé un défaut ADR-184 préexistant rendu
visible par la surface de provenance : `build_explanation` publiait les
seuils du RYTHME pour toutes les habitudes, y compris récurrentes — dont
les seuils réellement appliqués sont ceux des verrous. Les seuils sont
désormais publiés PAR KIND (figé par test : les nombres du rythme ne
fuient jamais sous une habitude récurrente).
