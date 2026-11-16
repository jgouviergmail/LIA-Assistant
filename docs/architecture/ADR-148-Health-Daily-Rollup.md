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

## Amendement 2026-11-14 — les jours de la personne, un pas compté une fois

**Contexte mesuré** (production, lecture seule, 14/11/2026) : LIA affichait 23 212 pas pour la journée quand Santé, sur l'iPhone, en comptait 14 402. Deux causes indépendantes, prouvées :

1. **Deux appareils, un seul pas.** Le raccourci envoie les échantillons de l'iPhone ET de l'Apple Watch, tous étiquetés `iphone`, dont les intervalles se chevauchent sans être identiques : 161 paires ce jour-là, dont 137 inclusions (un long échantillon du téléphone contenant de courts échantillons de la montre) et 24 décalages ; 23 309 pas en somme brute contre 13 297 une fois chaque tranche de temps comptée au débit le plus élevé. La fusion d'ingestion (`MergeStrategy.MAX`) ne voit que les intervalles IDENTIQUES d'un même lot. Forme de tout l'historique : 17 486 échantillons, aucun de durée nulle ou inversée (2 s à 22 min), 1 466 grappes de chevauchement sur 13 660, p99 = 5 échantillons, la plus grande 162.
2. **Des jours UTC.** « Aujourd'hui », les barres « jour » et les lignes de base couraient de 01 h à 01 h à Paris l'hiver (02 h l'été) : 23 212 au lieu de 23 309 ce jour-là.

**Décision** (arbitrages du propriétaire : « fusion serveur », « jour local partout »)

- **Une seule porte de comptage**, `fusion.counted_samples` : ce que valent des échantillons qui se chevauchent est DÉCLARÉ au registre (`HealthKindSpec.overlap_rule` : `MAX_RATE` pour un compte réparti sur son intervalle, `KEEP_ALL` pour des lectures, que l'on moyenne). Pour `MAX_RATE` : grappes de chevauchement dans l'ordre des débuts, tranches entre bornes, débit maximal × longueur, en SQL. Les lignes brutes ne sont jamais réécrites : corriger la règle corrige tout l'historique.
- **Une ligne appartient à la fenêtre de son DÉBUT** (règle des échantillons, gardée pour les tranches). La porte lit les échantillons commençant jusqu'à `HEALTH_METRICS_FUSION_HORIZON_HOURS` (24 h) avant et après la fenêtre : une tranche est découpée pareil quelle que soit la fenêtre qui la lit, deux jours voisins s'additionnent exactement.
- **Les jours de la personne, partout** : `fetch_daily_stats(zone=…)` groupe sur `timezone(<zone IANA>, …)`, toujours indépendant du `TimeZone` de session. « Aujourd'hui » (outils du chat, briefing), la ventilation journalière, les lignes de base, les variations, le heartbeat, le graphique des réglages, la commande graphique de l'assistant et la source des discussions proactives coupent à minuit local (`core/local_day`, désormais lu aussi par la récurrence). Chaque fenêtre de ligne de base commence à un minuit local.
- **Un seul lecteur de graphique, SQL** (`chart_read.read_chart_statistics`) : l'agrégateur Python qui servait l'écran des réglages disparaît, il aurait dû apprendre la fusion et le jour local une seconde fois. Seaux locaux : une heure sautée n'est jamais tracée, une heure répétée l'est une fois.
- **Plus de chemin « échantillons bruts »** : `daily_stats_from_samples` et les enveloppes à base d'échantillons de `baseline.py` et `signals.py` sont supprimées (elles groupaient par jour UTC sans fusion) ; le `summary_today` du heartbeat, comme « aujourd'hui », lit `fetch_window_summary`. Le détecteur d'inactivité reçoit le jour local de l'appelant. Ce point remplace la conséquence ci-dessus qui gardait `summary_today` sur échantillons bruts, et celle qui laissait `compute_kind_daily_breakdown` hors périmètre.
- **Les outils santé du chat lisent leurs bornes par le contrat de dates** (`read_period`, ADR-318) : une date est un jour entier du fuseau de la personne, la borne de fin incluse ; une valeur illisible est refusée, plus jamais remplacée par la fenêtre par défaut.
- **Garde** : aucun `func.<agrégat>(HealthSample.value)` hors de la porte (`test_counted_samples_single_door_guard.py`, prouvée sur une fixture fautive).

**Preuves** : PostgreSQL réel, `test_health_daily_stats_rollup.py` (12 cas : jour de Paris, 29 mars de 23 h et 25 octobre de 25 h, session UTC+14, inclusion, décalage, débit égal, absence de chevauchement exacte au pas près, fréquence cardiaque jamais fusionnée, fenêtres voisines additives, isolation par compte et par type) ; les filets golden des lignes de base et du heartbeat passent avec leurs tables INCHANGÉES, lus en UTC sur des échantillons sans chevauchement ; la commande graphique de l'assistant rend exactement le graphique des réglages, sans seau à 02 h le 29 mars.

**Conséquences** : les totaux de pas baissent sur tout l'historique là où deux appareils se chevauchaient ; un jour change de bornes pour qui n'habite pas en UTC ; `HealthDay.timezone` (source des discussions) nomme la zone du jour ; la réponse du graphique porte des débuts de seau au décalage local, que le navigateur affiche tels quels. L'écart résiduel avec Santé (≈ 1 100 pas le 14/11) tient aux pas faits après le dernier envoi du raccourci et à la priorité de source qu'applique Santé (le débit maximal en est une approximation sans regret).
