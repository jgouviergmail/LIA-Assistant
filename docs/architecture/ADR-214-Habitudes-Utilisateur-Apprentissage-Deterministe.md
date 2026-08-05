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
