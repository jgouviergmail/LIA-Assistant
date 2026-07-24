# ADR-148: Agrégation journalière côté SQL pour les signaux santé du heartbeat

**Status**: ✅ IMPLEMENTED (2026-07-24)
**Date**: 2026-07-24
**Deciders**: jgouvier + Claude
**Technical Story**: Défaut prod — `heartbeat_health_signals_timeout` **40 fois en 7 jours pour 86 décisions heartbeat (46,5 %)**, sur le seul utilisateur ayant activé `health_metrics_agents_enabled`. Diagnostiqué en production le 2026-07-23 : ce n'est ni un aléa de charge, ni un problème de base.

## Contexte mesuré

`build_heartbeat_health_signals` émettait **6 requêtes et transférait 30 662 lignes** par tick, pour produire quelques dizaines de nombres :

| # | kind | fenêtre | lignes |
|---|---|---|---|
| 1 / 3 | heart_rate / steps | 24 h | 363 / 65 |
| 2 / 4 | heart_rate / steps | **36 j** | **12 090 / 3 027** |
| 5 / 6 | heart_rate / steps | **36 j** — doublons exacts de #2 et #4 | **12 090 / 3 027** |

Les doublons venaient de ce que `compute_kind_baseline_delta` et `detect_all_variations` calculaient **la même fenêtre** et la refetchaient chacun.

Le coût n'était **ni SQL ni ORM** : PostgreSQL exécutait la requête en **6,7 ms** (Index Scan, 100 % buffers en cache) et l'hydratation ORM ne coûtait que 58,8 ms de plus que le Core. Les ~400 ms par requête étaient le **coût par ligne côté client** (~29 µs/ligne, mesuré par différence entre `count(*)` et un `SELECT` de 2 colonnes). Ce décodage est une **rafale synchrone qui ne rend pas la main** : l'event-loop du worker mesuré bloqué **483 ms d'un seul tenant** (1 823 ms sur un chemin froid).

Le garde-fou de 2,0 s posé sur cette source n'était donc pas franchi par une base lente mais par le **coût nominal** : 1 758–2 333 ms de wall-clock (médiane 1 896 ms) mesurés *in situ* dans le `gather` de 12 fetchers.

## Decision

- **Primitive de dépôt `fetch_daily_stats`** — un `GROUP BY` sur `cast(timezone('UTC', date_start), Date)` renvoyant **une ligne par jour UTC** : `(day, total, count, minimum)`. Ces primitives sont **des entiers bruts, pas une valeur pré-réduite** : toute agrégation `BaselineKind` s'en dérive (`DAILY_SUM` → `total`, `DAILY_AVG` → `total / count`, `RESTING` → `minimum`), et `detect_notable_events` a besoin de la **somme brute** quel que soit le `baseline_kind` du kind. Corollaire décisif : `total` et `count` étant des entiers exacts, `total / count` est **la même opération IEEE-754** que `sum(values) / len(values)` en Python — l'équivalence est *démontrable*, pas seulement constatée. Un mapping `BaselineKind → fonction SQL` (première conception) aurait été **infidèle** au détecteur d'événements pour tout futur kind en `DAILY_AVG` ; il a été abandonné pour cette raison.
- **Inversion de couplage plutôt que duplication** — `baseline.py` et `signals.py` exposent chaque calcul deux fois sur **une seule implémentation** : un point d'entrée `*_from_stats` consommant la série journalière, et l'entrée historique à base d'échantillons devenue une fine enveloppe qui groupe puis délègue. Les **19 tests unitaires existants passent inchangés, par construction** — c'est la preuve de non-régression, pas un effet de bord.
- **La normalisation `timezone('UTC', …)` est explicite** — sans elle, le découpage journalier dépend du `TimeZone` de la session : vert en CI (UTC), faux en production. Verrouillé par un test d'intégration qui rejoue la requête sous une session UTC+14 (mutation vérifiée : sa suppression fait échouer exactement ce test).
- **Extraction, jamais de relèvement de plafond** — le builder quitte `HealthMetricsService` (582/600 SLOC) pour `health_metrics/heartbeat_signals.py`, et la source santé quitte `context_aggregator.py` (fichier gelé) pour `heartbeat/health_context.py`, même motif qu'`interest_context.py` (ADR-135). Le cap de l'agrégateur **baisse** de 783 à 753.
- **Le budget de 2,0 s n'est PAS relevé** — ce serait traiter le symptôme. Après correctif il redevient ce qu'il prétendait être : un détecteur d'anomalie, deux ordres de grandeur au-dessus du coût nominal. Sa docstring, qui annonçait protéger d'« une base lente », est corrigée : ce budget borne une part d'**event-loop partagé**, pas un temps de base.
- **Le défaut est resté invisible 7 jours** parce qu'échouer-ouvert ne laisse aucune trace dans la notification. Chaque abandon est désormais **compté** (`heartbeat_source_dropped_total{source,reason}`) et **chronométré** (`duration_ms` au succès comme à l'échec).

## Preuves

- **Équivalence** : payload complet identique sur données de production ; **42/42** comparaisons sur tout le domaine `window_days` 1..14 (paramètre piloté par le LLM) ; **12/12** cas dégénérés ; filet golden de caractérisation (Feathers, cf. ADR-122) passé **inchangé** de part et d'autre de la conversion.
- **Sensibilité des filets prouvée par mutation** — `DAILY_AVG` → `min` : 56 échecs ; borne de fenêtre `<` → `<=` : 136 ; arrondi de la moyenne journalière : 14 (capté uniquement par la couche non arrondie + les jeux à décimales non terminantes) ; réintroduction de la double lecture : 1 échec **avec un payload resté identique** — d'où un verrou de comptage de requêtes distinct du filet de sortie.
- **Runtime, volume de production** (16 400 lignes semées, 29 516 transférées par l'ancien chemin) : **353 → 7,0 ms (×50)**, retard maximal de l'event-loop **124 → 1,1 ms**, builder complet **12,8 ms**.

## Consequences

- Le gain profite aussi aux **outils santé du chat** et à l'**extraction mémoire/journaux**, qui empruntaient les mêmes fenêtres larges et figeaient leur worker de la même façon.
- La fenêtre 24 h de `summary_today` reste **sur échantillons bruts** : quelques centaines de lignes, et une sémantique par échantillon (`_summary_value`, fraîcheur du dernier point) qu'un rollup journalier ne sait pas exprimer.
- Hors périmètre, documenté et non corrigé : `compute_kind_daily_breakdown` calcule déjà des agrégats journaliers en Python et pourrait consommer la primitive — mais sa conversion exige sa propre preuve d'équivalence ; et **les 11 autres fetchers de `aggregate()` n'ont aucun budget**, un appel connecteur bloqué peut stalle le heartbeat entier.
- Aucune migration, aucune écriture, aucun index ajouté (le plan est déjà optimal : `Seq Scan` à 20 ms sur une table encore petite, bascule automatique vers `ix_health_samples_user_kind_start` quand la sélectivité baissera).
