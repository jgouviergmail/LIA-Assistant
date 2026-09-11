# ADR-214 : les habitudes utilisateur s'apprennent par statistiques déterministes, sous contrôle utilisateur intégral

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Date**: 2026-08-05
**Décideurs**: Équipe LIA
**Complète**: [ADR-140](ADR-140-Chat-Piloted-Automations.md) (détecteur de récurrence), [ADR-135](ADR-135-Heartbeat-Interest-Quality.md) (qualité des mentions proactives), [ADR-178](ADR-178-Product-Value-Dashboard.md) (`product_outcomes`), [ADR-117](ADR-117-Background-Chat-Runs.md) (archive-first)

## Contexte

LIA ne possède aucune représentation apprise du *quand* de son utilisateur.
Le heartbeat décide d'interrompre en sachant seulement « dernier message il y
a N heures » (`context_aggregator._fetch_activity`). Le détecteur de
récurrence d'ADR-140 est éphémère (Redis), aveugle aux habitudes
hebdomadaires — sa fenêtre de 14 jours ne peut mathématiquement pas contenir
les 3 lundis exigés — et sa suggestion est un texte générique sans jour ni
heure, invisible des réglages.

Le programme « Habitudes utilisateur » (plan complet :
`docs/plans/2026-08-05-habitudes-utilisateur-programme.md`, simulations à
l'appui) apprend trois choses : le rythme d'activité (fenêtres actives par
classe de jour), les demandes récurrentes verrouillées (quotidien / jours
ouvrés / hebdomadaire, avec heure apprise), et réagit sobrement aux écarts.

## Décision

### 1. Statistiques déterministes calibrées par simulation — pas de ML entraîné

Trois raisons, chacune suffisante : la prod tourne sur Raspberry Pi 5 (zéro
budget d'entraînement/inférence) ; la doctrine d'explicabilité des intérêts
exige une formule publiable à l'utilisateur ; aux volumes par utilisateur
(centaines à milliers de messages), un modèle apprendrait le bruit là où des
tests statistiques à seuils calibrés contrôlent précisément les faux
positifs/négatifs (mesures : FP rythme 0-0,3 % sur usage sans habitude,
détection 98-100 % dès 21-28 j ; 0 % de suggestion d'automatisation à tort
sur usage étalé/sporadique).

L'unité statistique du rythme est **le jour** (présence par créneau), jamais
le message : le comptage par message est corrompu par les rafales
intra-journée (mesuré en simulation — FP 83-100 % pour l'approche naïve).

### 2. Aucune écriture nouvelle sur le hot path

Le profil de rythme se recalcule par un job nightly leader-elected
(agrégation SQL sur `conversation_messages`, une session par utilisateur,
UPSERT du profil). La récurrence réutilise l'écriture fire-and-forget
existante d'ADR-140. Les deux seuls deltas hot-path sont les seams du Lot 0 :

- **`product_outcomes.domain`** : le seam v1 d'ADR-178 écrivait `"unknown"`
  en dur. Le domaine du tour COURANT est désormais capturé par le service de
  streaming au passage du delta `query_intelligence` (gaté sur
  `routing_history_changed` : le premier chunk `values` rejoue le checkpoint,
  dont la QI est celle du tour PRÉCÉDENT — l'enregistrer serait une donnée
  fausse, pas un simple « unknown »), puis validé contre `DOMAIN_REGISTRY`.
- **`is_automated_source` sur la ligne user archivée** : la conversation est
  1:1 par utilisateur et la ligne archivée ne portait aucun marqueur — un
  message synthétique d'action programmée était indistinguable d'un message
  humain. Sans exclusion, une action quotidienne à 7 h apprendrait
  « utilisateur actif à 7 h » : LIA apprendrait de ses propres automatisations.
  `archive_user_message_first` (extrait de `AgentService` — ratchet de
  taille : un fichier logique ne grossit jamais) stampe désormais le marqueur ;
  l'historique non marqué sort de la fenêtre d'observation (56 j) avant toute
  consommation — auto-assainissement, pas de backfill.

### 3. Le contrôle utilisateur précède l'exploitation

Nouveau bounded context `domains/habits/` (modèles `UserHabitProfile` +
`UserHabit` imitant `UserInterest` : signaux ±, statuts
active/paused/blocked), flag global `HABITS_ENABLED` défaut **OFF**,
préférence utilisateur, section réglages complète (consultation, explication
de la formule façon intérêts, provenance avec tombstones, correction,
suspension, blocage, suppression, export) livrée AVANT que le heartbeat, le
briefing ou les suggestions ne consomment quoi que ce soit. Purge GDPR,
suppression de compte et export de compte câblés dès la migration.

### 4. Le rythme appris priorise, il n'élargit jamais

Les bornes explicites de l'utilisateur (fenêtres horaires, min/max par jour)
priment toujours : le scoring de timing préfère les créneaux appris À
L'INTÉRIEUR des bornes, intersection vide → comportement identique à
aujourd'hui, et l'invariant anti-famine du `min_per_day` est testé.

### 5. Les remarques d'écart sont un service, bornées et arrêtables

Trois types autorisés (routine verrouillée manquée = offre via source gatée
« habits » ; heure inhabituelle et retour d'absence = voie ambiante), budgets
(≤ 1/jour), cooldown 7 j par habitude, k de surprisal dépendant de la forme
(quotidien k=2, hebdomadaire k=1), et règle d'arrêt : 2 offres consécutives
sans adhésion rendent le type muet pour cette habitude jusqu'à ré-occurrence
positive — borne dure de 2 remarques sur une routine abandonnée. Tout
commentaire de surveillance sans valeur de service est interdit.

## Conséquences

- Un utilisateur occasionnel mais ritualisé (chaque lundi) obtient son verrou
  hebdomadaire sans qu'on lui invente un « rythme de vie » ; un utilisateur
  sans structure temporelle obtient le silence (verdicts `diffuse`/`sparse`
  explicites) — les deux détecteurs opèrent à des granularités
  complémentaires.
- Le ledger de récurrence passe au stockage PAR JOUR (cap = jours de fenêtre,
  heures plafonnées par jour) : le cap historique de 20 occurrences rendait
  l'étalement ≥ 10 j inatteignable pour un usage multi-quotidien.
- `product_outcomes.domain` devient exploitable par l'analytics produit ET
  par les habitudes (bénéfice double du même seam).
- Les seuils vivent dans `core/config/habits.py` (env-overridable) avec les
  valeurs calibrées ; les recalibrer impose de rejouer le harnais de
  simulation du plan.

## Amendement 2026-08-05 — validation adversariale sur données réelles

Le détecteur réel exécuté sur les agrégats de prod (lecture seule, comptages
jour×heure uniquement) a produit deux verdicts qui corrigent cet ADR :

1. **L'auto-assainissement 56 j de la décision 2 était insuffisant.** Les
   actions programmées injectent des messages rôle-user NON marqués tant que
   le marqueur n'est pas déployé, et l'apprentissage rétroactif les ingère :
   mesuré sur un compte réel, un métronome de 66 messages à 07:00 (1/jour,
   week-ends compris) aurait fait revendiquer « fenêtre 06:00-08:00 » — le
   planning du scheduler de LIA, pas l'habitude de l'utilisateur. La source
   messages porte désormais un second filtre : `NOT EXISTS` vers
   `message_token_summary` par `run_id`, excluant tout message dont le run
   appartient à une famille de session non whitelistée (même whitelist que la
   source summaries). Un message sans run/summary correspondant reste inclus
   (il précède le tracking, donc l'automatisation). Coût mesuré : 1,3 ms sur
   le RPi5 (index unique `run_id`).
2. **Les resets de conversation sont une source de présence.**
   `reset_conversation` n'a qu'un appelant — l'endpoint authentifié — donc
   chaque ligne d'audit `action='reset'` est un geste humain par
   construction. Pour un utilisateur qui reset souvent, c'est LA trace
   durable (124 jours distincts mesurés sur le compte principal contre ≤ 4
   via messages/summaries) : sans elle, son profil lisait `sparse` alors
   qu'il est présent presque chaque jour. L'union devient messages ∪
   summaries ∪ resets ∪ rollup (max par heure), bornes comprises.

Après correctifs, sur les trois comptes réels : plus aucune fenêtre fabriquée
(l'ex-« 06:00-08:00 » disparaît), et les verdicts honnêtes tombent — `none`
(présent sans heure fixe) pour le compte principal, `sparse` pour les deux
usages majoritairement pilotés par le push.

### Complément 2026-08-05 (même session) — les deux lots de consommation

- **Candidats de récurrence en observation** : le panneau publie les
  signatures vues mais non verrouillées avec le seuil d'existence appliqué
  (`recurrence_min_distinct_days`) ; au-delà du volume, l'état « régularité
  en cours de confirmation » (un verrou n'est pas linéaire). Lecture Redis
  par contrat de clé (3ᵉ site épinglé par test — agents importe déjà habits,
  l'inverse fermerait le cycle) ; cap `HABITS_CANDIDATES_DISPLAY_MAX`
  paramétrable, reste compté.
- **Scoring déterministe de tick** (décision 4, volet timing) :
  `should_defer_tick` différencie un tick hors rythme appris seulement si
  une entrée de fenêtre reste atteignable le jour même dans les bornes
  utilisateur (marge d'un intervalle ; anti-famine ; heure 0 = borne
  valide). Flag dédié `HABITS_TICK_SCORING_ENABLED` défaut OFF ; le lissage
  probabiliste du runner et sa garantie de minimum restent intacts.
- **Durabilité et visibilité** (même session) : le FORMAT du ledger descend
  dans `infrastructure.cache.recurrence_store` (trois domaines, zéro
  littéral dupliqué) ; un ledger vide se reconstruit depuis
  `product_outcomes` (même whitelist humaine, `domain <> 'unknown'`,
  write NX, savepoint — les récurrences deviennent rétroactives sur
  l'historique post-déploiement) ; la répartition horaire (`bin_presence`)
  devient une heatmap 24 créneaux dans le panneau ; l'explication d'une
  habitude récurrente publie les jours d'occurrence RÉELS du ledger —
  toujours aucune référence de conversation fabriquée.

## Amendement 2026-09-03 — sources humaines durables, provenance du seed, garde d'évaluation

L'audit « trois boucles silencieuses » (voir ADR-260) a mesuré, sur le compte
principal en production, ce que les deux amendements précédents n'avaient pas
pu voir :

1. **La source `message_token_summary` ne survit PAS aux resets.** Le reset
   de conversation supprime les résumés de tokens de la conversation
   (`token_summaries_deleted_for_conversation`) : 5 lignes `session_` en
   56 jours pour 235 tours humains réels. La liste blanche par forme de
   session n'atteignait presque rien. **La source humaine durable est
   `product_outcomes`** — une ligne par run finalisé, jamais supprimée par le
   reset, dont la colonne `channel` dit qui était derrière le run. Le prédicat
   « tour humain » a désormais **une seule implémentation**
   (`habits/human_turns.py` : `channel = 'web'` et `result_type IN
   ('answer','action')`), lue par le dépôt du rythme ET par le seed du ledger,
   épinglée contre le vocabulaire du domaine produit. Deux formulations d'un
   même « humain » finissent toujours par diverger (ADR-255).
2. **Le seed reconstruisait les routines de LIA comme des habitudes de
   l'utilisateur.** Sa liste blanche lisait « pas de résumé de tokens =
   humain » ; or les résumés sont supprimés au reset et les `run_id` des runs
   proactifs ne correspondent jamais. 183 outcomes `automation_run` (les
   routines 07:00-09:00 exécutées de nuit pendant qu'un fuseau de voyage
   restait actif) ont seedé `email` 27 jours, `event` 26, `weather` 26,
   `web_search` 27 — pour cinq tours tapés. Rejoué avec `evaluate_locks`,
   l'amas nocturne seul verrouille « daily à 01:16 » : LIA aurait proposé
   d'automatiser sa propre automatisation ; mêlé aux heures humaines, il
   diluait R sous 0,8 et masquait toute vraie habitude. Le seed lit le
   prédicat partagé ; un test d'intégration rejoue le cas prod contre
   PostgreSQL et exige zéro verrou.
3. **La provenance est dite.** Un payload seedé porte `origin: "seed"`
   (`live` par défaut à la lecture ; un tour vivant repasse la clé à `live`),
   publié par `/habits` et affiché « reconstruit depuis l'historique » dans
   l'écran des habitudes. Le seuil ne change pas : on dit d'où vient la
   donnée, on ne la juge pas autrement.
4. **L'évaluation est gardée comme l'enregistrement.**
   `_resolve_recurrence_suggestion` refuse désormais un run automatisé
   (`is_automated_source`, compté par `recurrence_evaluation_skipped_total`) :
   un run programmé ne pouvait pas enregistrer une occurrence mais pouvait
   évaluer, faire feu et promouvoir une habitude.
5. **La clause historique `NOT EXISTS` de la source messages est datée** :
   le marqueur `is_automated_source` existe depuis le 2026-08-05 ; à partir du
   2026-09-30 plus aucune ligne non marquée n'est dans la fenêtre de 56 jours
   et la clause peut disparaître.

6. **La présence en lecture est une quatrième source** (décision propriétaire
   2026-09-03 : une notification ne compte JAMAIS comme activité ; un pouce
   haut ou bas compte). Le compte principal vivait par le heartbeat — 106
   notifications lues en 30 jours, 361 ouvertures de l'application en 20
   jours, 5 tours tapés — et le détecteur ne voyait que la frappe. Deux
   signaux comptent désormais : l'**ouverture de l'application** (ping du
   client au montage, sur `visibilitychange`→visible et au focus, throttlé ;
   jamais depuis un poll d'arrière-plan ; flag `HABITS_PRESENCE_ENABLED`, OFF
   par défaut) et le **pouce** sur une notification heartbeat ou intérêt
   (toujours, dès que les habitudes sont actives ; `feedback_at` horodate le
   geste, la source SQL ne lit que cette colonne). Une heure bankée par heure
   locale et par utilisateur (`SET NX`), écrite par UPSERT atomique dans le
   rollup durable avec `GREATEST(existant, 1)` — la présence marque l'heure,
   elle ne gonfle jamais un compte de messages. Les clés sont de famille
   `presence` (`USER_LEARNING`, ADR-260). La porte d'inactivité du heartbeat
   lit `max(last_login, dernière présence)` : deux comptes qui lisaient sans se
   reconnecter avaient été réduits au silence après sept jours.
7. **Ce que la présence change, mesuré** (rejeu du vrai détecteur sur le
   rollup prod du compte principal, seuils par défaut) : tel quel, `none`
   (meilleur bin 0,39) ; avec une ouverture à 08 h trente jours sur
   trente-cinq, **toujours `none`** — le bin 8 h monte à 0,89 mais la porte
   *capture* refuse : l'activité de ce compte est étalée sur vingt-quatre
   heures et une fenêtre d'une heure n'en capture pas 60 % ; avec une
   présence uniforme (une heure différente chaque jour), `none` ; avec une
   présence à 08 h seule, les jours de semaine, `windows` 07-09 h à 0,92. La
   présence rend lisible le rythme d'un utilisateur qui lit sans écrire ; elle
   n'invente pas de fenêtre à qui n'en a pas. Les seuils restent ceux de la
   calibration.

Ce qui ne change pas : les seuils calibrés, l'unité statistique (le jour), la
règle « le rythme priorise, n'élargit jamais ».

## Amendement 2026-09-11 — le ledger de récurrences n'avait jamais rien enregistré

**Constat, mesuré en production** : `user_habits` = 0 ligne pour l'instance
entière, cinq semaines après la mise en service. Le rythme, lui, tournait et
répondait honnêtement `none` (voir plus bas). La moitié « récurrences »
d'ADR-214 n'a jamais reçu une occurrence : sur 14 jours, 227 tours
actionnables, 0 écriture, compteur `post_response_extraction_scheduled_total`
à `not_applicable` seul.

**Cause** : les deux lecteurs de la porte (`post_response_extractions.py`,
`initiative_recurrence.py`) lisaient `get_qi_attr(state, "intent")`. Or
`QueryIntelligence` ne déclare pas d'attribut `intent` — le champ s'appelle
`immediate_intent`, et son vocabulaire (`search | detail | create | …`) ne
contient de toute façon pas `action`. `getattr(obj, "intent", None)` rend
`None` sans rien signaler ; `None != "action"` est vrai pour tout tour. Le
même mécanisme lisait `secondary_domains`, lui aussi inexistant. Preuve sur un
blob de checkpoint réel : `immediate_intent` et `primary_domain` présents,
`"intent"` absent.

**Pourquoi la CI était verte** : les 40 tests couvrant la porte
construisaient `"query_intelligence": {"intent": "action"}` — la clé que le
lecteur attendait, jamais la forme que le producteur émet. Un test bâti sur
l'hypothèse du lecteur valide le lecteur contre lui-même.

**Décisions** :

1. **Une seule déclaration, deux lecteurs** :
   `resolve_actionable_domain(state)` lit `routing_history[-1].intention ==
   INTENTION_ACTION` — la décision du routeur, en vocabulaire fermé, et la
   valeur même dont `product_outcomes.result_type` dérive, si bien qu'un tour
   que le tableau de bord compte comme une action est un tour que le ledger
   enregistre. Lecture tolérante objet **ou** dict (aller-retour msgpack).
2. **La signature reste le domaine primaire seul** : la production n'a
   jamais stocké que des clés mono-domaine ; composer les domaines
   secondaires fragmenterait chaque clé (moins d'occurrences par signature,
   verrous plus lointains). Décision séparée, à mesurer avant d'être prise.
3. **Garde de classe** (`tests/unit/test_qi_attr_contract_guard.py`) : toute
   lecture littérale `get_qi_attr(state, "x")` doit nommer un attribut déclaré
   de `QueryIntelligence`. Elle attrape les quatre lectures mortes et interdit
   la cinquième.
4. **Le silence devient visible** : alerte `RecurrenceLedgerSilent` dans le
   cœur chargé (`alerts-core.yml`, tests promtool, runbook), et la métrique
   quitte le référentiel des métriques aveugles. Le fichier `alert_rules.yml`
   n'est pas chargé par Prometheus (ADR-119) — une alerte posée là serait
   « câblée » sur le papier et jamais évaluée. **Revue à froid du même
   jour** : la première expression lisait « `not_applicable` > N et
   `scheduled` = 0 » — juste sur la forme du bug, fausse dès le correctif
   (`not_applicable` devient le sort normal des tours de conversation : une
   semaine sans demande actionnable aurait tiré) et aveugle à un Redis qui
   avale chaque écriture (`scheduled` est compté à la remise au fond, pas à
   l'atterrissage). Elle lit désormais trois compteurs : les tours
   actionnables **humains** du routeur (`product_outcomes_total{action,E3}`,
   la valeur dont le tableau de bord dérive), les écritures **atterries**
   (`recurrence_ledger_writes_total{written}`, incrémenté par l'écriture
   elle-même, `redis_unavailable`/`failed` sinon), et `feature_disabled`
   pour taire un ledger coupé par configuration. Les deux échecs du ledger
   sont loggués aux niveaux que la production expédie (warning à l'écriture,
   error à la planification, comme ses frères) — une ligne `debug` était une
   trace que personne ne pouvait lire (prod : `LOG_LEVEL=INFO`).
5. **Résidu purgé avant correctif** : le ledger contenait 25 clés (3 comptes)
   écrites par un seed antérieur défectueux, figées au 2 septembre,
   indiscernables du vivant (`origin` par défaut), dont un verrou
   `web_search daily@3.1h` sans cooldown — promu au premier tour du domaine
   dès le correctif déployé. Purgées (sauvegarde conservée) ; le recalcul
   nocturne re-sème depuis les vrais tours avec `origin=seed`.

**Calibration, rejouée sur un harnais durable**
(`scripts/habits/measure_calibration.py`, `task habits:calibration:measure`,
protégé par `test_calibration_harness.py`) : l'ancien harnais était un
scratchpad perdu. Sous les seuils actuels (capture 0,6 / sélectivité 1,9 ;
R 0,8) le nouveau reproduit l'ancrage publié — 0 % de FP sur usage sans
structure, 100 % de détection à 15 % de bruit. La série réelle du compte
principal rend `none` **à chaque point de la grille**, jusqu'à 0,3 / 1,1 (77 %
de FP), et aucune de ses signatures ne verrouille jusqu'à R 0,4 (52 % de faux
verrous) : sa meilleure fenêtre capte 26 % de son activité, ses heures de
demande ont R ≤ 0,39. **Aucune recalibration défendable ne produit une
habitude pour cet usage** — le silence est la réponse exacte. Mesure annexe,
non appliquée : sélectivité 1,6 domine 1,9 sur cette grille (+12,6 pts de
détection à 35 % de bruit, FP inchangé à 0 %, 300 essais) ; un changement de
seuil est une décision produit, prise sur cette mesure, jamais à l'estime.

## Amendement 2026-09-11 (b) — recalibration deux profils : le modéré ciblé est servi par les récurrences

**Direction produit** (propriétaire) : les réglages doivent servir aussi bien
un utilisateur hyperactif qu'un utilisateur modéré dont les interactions sont
« peu nombreuses mais assez ciblées » — l'assistant est proactif, les tâches
planifiées tournent, la présence humaine peut être rare sans être informe.

**Le harnais a été étendu** pour mesurer cette exigence : populations modérées
ciblées (2-3 soirs/semaine toujours 20-22h ; une demande 3×/semaine à heure
fixe ; un rituel hebdomadaire fiable à 90 %) chacune avec son contrôle
dispersé **à volume égal** (le risque de faux positif d'un seuil assoupli vit
à faible volume), et une métrique de **délai** : taux de détection à J+14,
21, 28, 35/42, 56 depuis la première activité. 300 essais par case.

**Rythme : la relaxation est refusée par la mesure.** Les barres de présence
absolue (dénominateur calendaire, plancher Wilson) ne peuvent pas servir le
rare-mais-ciblé sans fabriquer des fenêtres chez le dense : abaisser
présence/Wilson/sparse à 0,45/0,22/0,20 ne détecte que 34,7 % du « 3
soirs/semaine » en coûtant **8-17 % de revendications permanentes sur
l'utilisateur uniforme sans structure** ; à 0,35/0,15/0,12 : 74,3 % contre
18-37 % de FP. C'est un verdict de mécanisme, pas de seuil — et la réponse
honnête au profil rare est ailleurs (les récurrences, ci-dessous). Un seul
changement appliqué : **sélectivité 1,9 → 1,6** (détection à 35 % de bruit
84,7 → 97,3 %, coût ~1 % de FP week-end au pire horizon transitoire), l'exit
d'hystérésis suit (1,6 → 1,36 = ×0,85, le ratio d'origine).

**Récurrences : c'est ici que le modéré ciblé apprend, et quatre défauts
mesurés le bloquaient.**

1. **La fenêtre de 28 jours contient exactement 4 créneaux hebdomadaires** :
   le verrou weekly exigeait un mois parfait, et *mourait* sur la semaine
   manquée (71 % à J+28 retombant à 64 % à J+42 pour un rituel fiable à
   90 %). → `RECURRENCE_WINDOW_DAYS` 28 → **35** (5 créneaux : 91,3 %
   stable), le cap du ledger suit (35 = jours de fenêtre).
2. **Le time-lock exigeait 8 occurrences et 14 jours *distincts*** : un
   3×/semaine n'atteint jamais 14 jours distincts sur 28 — indétectable pour
   toujours ; et un quotidien n'était nommable qu'à J+21+ (4 % à J+14). →
   `RECURRENCE_LOCK_MIN_OCCURRENCES` 8 → **6**, et l'étiquetage attend un
   **empan calendaire** (premier→dernier jour) de 10 j, plus jamais 14 jours
   distincts : le quotidien est reconnu à J+14 (98 %), le 3×/semaine à
   J+21-35 (93-100 %). Un sens qui change prend un **nom nouveau** :
   `RECURRENCE_SHAPE_MIN_SPAN_DAYS` remplace `RECURRENCE_SHAPE_MIN_DAYS`, et
   l'ancienne clé — que le `.env` de production pinne à 14 — est ignorée
   plutôt que réinterprétée. Même doctrine pour le couple fenêtre/cap :
   `RECURRENCE_LEDGER_MAX_ENTRIES < RECURRENCE_WINDOW_DAYS` tronquerait
   chaque fenêtre (le cap v1 avait affamé le verrou d'étalement ainsi) — le
   démarrage le **refuse** (`model_validator`, comme les validateurs voisins).
3. **L'étiquette mentait** : détecté sous les anciens seuils abaissés, le
   3×/semaine sortait « daily » — « tous les jours vers 9h » promis à
   quelqu'un qui le fait trois fois par semaine. → Quatrième forme
   **`intermittent`** : la *densité* de jours distincts sur l'empan
   **éligible** (jours ouvrés seuls pour un candidat workdays — un Lun-Ven
   fiable n'est jamais dégradé : 300/300 étiquetés workdays) décide de
   l'étiquette, jamais du verrou ; sous `RECURRENCE_DAILY_DENSITY_MIN` (0,6 ;
   un quotidien à 80 % de présence est à ~0,8, un 3×/semaine à ~0,43)
   l'habitude est « plusieurs fois par semaine vers {heure} » (6 langues,
   suggestion + libellé). `days_of_week()` rend `[]` — aucun calendrier
   promis, et le heartbeat n'en fabrique pas de créneau (exclusion
   documentée).
4. **L'arc de veille a une concentration intrinsèque** : des heures uniformes
   8-22h portent R≈0,53 et franchissent la barre 0,8 par chance dans 3 % des
   contrôles légers — le harnais l'a montré du premier coup. → Une heure
   promise *sans calendrier* doit être plus serrée :
   `RECURRENCE_INTERMITTENT_R_MIN` = **0,9** (un vrai rendez-vous horaire à
   σ 0,75 h est à R≈0,98). Résidu : 3,0 % → **0,3 %**, détection inchangée.

Le weekly assoupli (3 jours modaux / fraction 0,6) a été **mesuré et refusé** :
il n'apporte rien au rituel fiable (l'existence exige déjà 4 jours distincts)
et pose des verrous hebdomadaires chanceux sur le contrôle clairsemé.

**Ce que le déploiement doit savoir.** Le `.env` de production pinne
explicitement chaque seuil de cette section à sa valeur d'août (vérifié le
2026-09-11 : `RECURRENCE_WINDOW_DAYS=28`, `RECURRENCE_LEDGER_MAX_ENTRIES=28`,
`RECURRENCE_LOCK_MIN_OCCURRENCES=8`, `HABITS_SELECTIVITY_MIN=1.9`,
`HABITS_EXIT_SELECTIVITY=1.6`) : les défauts du code ne s'y appliquent pas.
Sans alignement de ces cinq lignes sur `.env.example`, la production
tournerait la recalibration à moitié (étiquetage nouveau, volumes anciens).
La clé retirée `RECURRENCE_SHAPE_MIN_DAYS=14` est inerte et peut rester ; les
deux nouvelles (`RECURRENCE_DAILY_DENSITY_MIN`, `RECURRENCE_INTERMITTENT_R_MIN`)
prennent leurs défauts. Le harnais, lui, mesure les **constantes** — jamais
le `settings` vivant : sous `task` le `.env` racine s'injecte dans chaque
commande, et une mesure qui change selon le lanceur n'est pas une mesure.

**Table finale (jeu expédié, 300 essais, taux de verrou à J+14 / J+42 +
formes)** : quotidien 98 % / 100 % (daily:299) ; Lun-Ven 96,7 % / 100 %
(workdays:300) ; 3×/semaine 50,7 % / 100 % (intermittent:273, daily:26 —
tirages réellement denses) ; rituel hebdo 0 % / 91,3 % (weekly:274) ;
contrôles : aléatoire dense 0,0 %, aléatoire léger 0,3 %. Les ancrages sont
pinnés à 20 essais déterministes dans `test_calibration_harness.py` ; les
contre-exemples (relaxed_*, wk_relaxed, floor) restent dans le balayage pour
que les tables montrent le coût refusé.

**Sur la série réelle du compte principal** : toujours aucun verrou sous le
jeu expédié (`weekly` du domaine route à 3 jours modaux — sous la barre de 4,
visible dans la ligne wk_relaxed) ; le rythme reste `none` (honnête). Le
mécanisme est prêt pour les données que le correctif (a) laissera enfin
s'accumuler.
