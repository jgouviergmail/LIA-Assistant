# ADR-178 : Dashboard produit natif — outcomes durables, gauges DB-backed, datasource PostgreSQL en lecture seule

**Statut**: ✅ IMPLEMENTED (2026-07-29) — Phases 0-4 livrées (dashboard 26, socle outcomes, datasource lecture seule, télémétrie client : endpoint borné auth optionnelle + événements anonymes pré-inscription, Web Vitals LCP/CLS, PWA, recherche réglages) ; Phase 5 (alertes) préparée dans `alerts-product.yml`, activation après 4 semaines de baseline
**Date**: 2026-07-29
**Décideurs**: Utilisateur (6 arbitrages signés 2026-07-29) + revue technique complète contre le dépôt

## Contexte

LIA dispose de 25 dashboards Grafana techniques (595 panels, 419/419 métriques
couvertes) mais d'aucune vue **produit** : combien d'utilisateurs obtiennent un
résultat réellement utile, à quel coût, et reviennent-ils ? La spécification
utilisateur (`LIA_Specification_Dashboard_Grafana_Produit_v1.1.pdf`) propose un
26ᵉ dashboard adossé à un modèle normatif de la valeur (types de résultat,
niveaux de preuve E1/E2/E3, North Star = utilisateurs hebdomadaires avec au
moins un résultat utile validé E1/E2).

La contre-vérification exhaustive (2026-07-29, preuve fichier:ligne dans
`docs/superpowers/specs/2026-07-29-product-dashboard-program.md`) a confirmé
l'inventaire (toutes les métriques citées existent) et relevé 12 corrections,
dont deux reclassements (AUT-13, HITL-14 : « Existant » alors que la donnée
n'existe qu'en DB), un label réservé (`job`), et un risque de cardinalité
(les histogrammes à 4 labels × 26 domaines du `DOMAIN_REGISTRY` ≈ 23 000 séries
potentielles sur RPi5).

## Décision

**Architecture 100 % native — Grafana + Prometheus + PostgreSQL, aucune
plateforme analytics tierce.** Langfuse n'est pas une dépendance (dev-only,
absent de prod) ; rien n'est retiré de LIA, le dashboard ne le référence pas.

1. **PostgreSQL = vérité produit durable.** Nouveau contexte borné
   `domains/product/` : `product_outcomes` (1 ligne par `result_id`, lignage
   `workflow_id`/`run_id`, état canonique + niveau de preuve E1/E2/E3 mutables —
   un E2 exige 24 h sans correction/réversion) et `product_events` (v1 sur
   arbitrage utilisateur). La North Star n'est **jamais** calculée depuis
   Prometheus : les états sont mutables, un Counter ne se dé-compte pas.
2. **Prometheus = transport temps réel borné.** Compteurs d'événements
   (`product_outcomes_total{result_type, domain, evidence}`) et **gauges
   DB-backed** (pattern éprouvé `lifetime_metrics.py`) recopiant les agrégats
   exacts calculés en SQL (`product_users_with_useful_outcome{window,evidence}`,
   `product_value_penetration_ratio`, `product_activation_rate`,
   `product_retention_rate`, `product_funnel_users`, `product_data_quality_ratio`,
   `product_metrics_last_refresh_timestamp_seconds{refresh_job}` — jamais de
   label `job`, réservé au scrape). **Histogrammes limités à ≤ 2 labels** ;
   les ventilations fines restent en SQL. Aucun `user_id`/`result_id`/UUID en
   label. Coûts produit **exclusivement en EUR** (source DB
   `message_token_summary.total_cost_eur`) ; `conversation_cost_usd` reste
   cantonné aux dashboards 05/09.
3. **Dashboard `26-product-value`** (uid conforme à la convention
   `<numero>-<slug>`, titre anglais, schemaVersion 38, tag `lia`) : 42 panels,
   11 rows (00/01/02/10 visibles). Trois états de panel en v0 : LIVE (séries
   existantes), PRE-WIRED (requête posée sur le futur nom `product_*`, rend
   « n/a » puis s'allume sans modification du JSON), TEXT (sources DB/client
   pas encore nées, phase indiquée). Les 25 dashboards existants restent les
   vues de détail — le 26 synthétise et pointe, sans dupliquer.
4. **Datasource PostgreSQL en lecture seule** (phase 3) : uid
   `postgres-product-readonly`, provisionnée par YAML avec interpolation env
   (`$POSTGRES_DB`, `$GRAFANA_PRODUCT_DB_PASSWORD` injectés au conteneur
   Grafana dans les deux compose). Rôle `grafana_product_reader` créé par
   script idempotent + task (pattern `db:create-admin`) — jamais un mot de
   passe dans une migration — `GRANT SELECT` **uniquement** sur les
   vues/tables produit (jamais les tables brutes porteuses de PII) et
   `statement_timeout` posé sur le rôle.
5. **Cycle de vie et privacy.** `product_outcomes`/`product_events` portent un
   `user_id` → purge intégrale câblée dans `user_data_map` +
   `account_deletion_service` (pattern `scheduled_actions`). Rétention brute
   **180 jours** (`PRODUCT_OUTCOMES_RETENTION_DAYS`, .env), agrégats
   journaliers illimités ; purge exécutée par le job horaire leader-elected.
   `device_class` **dérivé** de l'`os_family` de session borné (ADR-144),
   aucune capture client nouvelle (tablette non distinguée, assumé).
6. **Écritures hors chemin chaud.** L'émission d'outcomes est asynchrone/
   best-effort, jamais bloquante pour la boucle SSE ; upserts atomiques
   (pattern `create_or_update_token_summary`).
7. **Alertes produit différées** (phase 5) : baseline de 4 semaines exigée,
   hygiène ADR-119 (owner, runbook, fichier `alerts-product.yml` ajouté à
   `rule_files` + montages compose).

## Alternatives écartées

- **Plateforme analytics/tracing tierce** (PostHog, Amplitude, Langfuse…) :
  contraire à la philosophie locale-first du projet, PII hors périmètre
  maîtrisé, et l'inventaire prouve que la stack native couvre le besoin.
- **North Star depuis les compteurs Prometheus** : états E1/E2 mutables sous
  24 h, déduplication par `result_id` impossible dans un Counter — faux chiffres
  garantis.
- **`MATERIALIZED VIEW`** pour les agrégats : refresh verrouillant, étranger
  aux patterns du dépôt — tables d'agrégats applicatives + vues fines à la
  place (pattern `user_statistics`).
- **Capture client de `device_class`** : nouvelle donnée non minimisée,
  contraire à ADR-144 pour un gain marginal (tablette) — dérivation coarse
  retenue sur arbitrage.
- **Histogrammes multi-labels fidèles au PDF v1.1** : ~23 000 séries
  potentielles sur RPi5 — plafond 2 labels, le fin grain vit en SQL.
- **uid `lia-product-value`** : viole la convention documentée
  `<numero>-<slug>` — `26-product-value` retenu.

## Conséquences

- Le dashboard 26 v0 rend de la valeur immédiate (panels LIVE) sans toucher au
  backend ; les panels North Star s'allument à la phase 2 sans retouche JSON.
- Deux nouvelles tables + un module de config + un job horaire + des gauges
  DB-backed entrent au périmètre de test backend (round-trip, upserts
  concurrents, timezone, garde de cardinalité, purge GDPR).
- Le dictionnaire des métriques produit (nom, formule, dénominateur, source,
  owner, version) vit dans `docs/superpowers/specs/2026-07-29-product-dashboard-program.md`
  puis `docs/technical/GRAFANA_DASHBOARDS.md` §26.

## Amendement 2026-10-23 — chaque panneau lit une série produite ; décision sur les alertes produit

Audit AC-006, mesuré avant toute correction par la garde inverse qu'il ajoute
(`tests/unit/test_metric_producer_guard.py`, exécutée aussi par
`task lint:observability` : `measure_metric_coverage.py --producers`) :

1. **Deux panneaux « pré-câblés » ne s'allumaient jamais.** « Cost per useful
   outcome (7d) » et « Time to useful outcome (p50, 7d) » lisaient des
   histogrammes (`product_outcome_cost_eur_*`, `product_outcome_duration_seconds_bucket`)
   qu'aucun code ne produisait. Ils lisent désormais deux jauges que le rollup
   horaire calcule dans PostgreSQL sur le MÊME ensemble utile que
   `count_useful_users` — toujours `validated`, validé dans la fenêtre :
   `product_outcome_cost_eur_mean{window}` et
   `product_outcome_latency_p50_seconds{window}` (`validated_outcome_value`, testé
   sur PostgreSQL réel). Un histogramme observé à la validation a été écarté :
   un résultat rejeté après sa validation ne se décompte pas d'un histogramme, un
   passage E2 → E1 l'aurait compté deux fois, et le coût n'est connu qu'au
   rattrapage du rollup — la règle de cet ADR (« la vérité produit est en base »)
   tranche.
2. **Décision sur `alerts-product.yml`.** L'alerte de fraîcheur
   (`ProductAggregatesStale`) passe dans `alerts-core.yml` : elle ne demande
   aucune baseline, et sans elle un rollup arrêté laisse le tableau 26 faux sans
   rien pour le dire (gravité `warning`, seuil
   `ALERT_CORE_PRODUCT_AGGREGATES_STALE_SECONDS`, fiche
   `docs/runbooks/alerts/ProductAggregatesStale.md`, cas promtool, recette de
   preuves). Les trois alertes de comportement restent non chargées et sont
   **re-décidées au plus tard le 2026-12-15**, sur une mesure en lecture seule des
   séries produit de la production : un seuil posé sans la variance qu'il doit
   dépasser alerte sur du bruit, et une instance de quelques comptes peut ne
   jamais en offrir. Leur activation suit alors les conventions du cœur
   (gravité `critical`/`warning` — `high` n'atteint aucune route —, `tier: core`,
   fiche, cas promtool, recette, seuils `ALERT_CORE_*`), écrites en tête du
   fichier.
3. **La garde de couverture ne lit plus que les règles chargées**
   (`coverage_rule_files()` = le `rule_files` de `prometheus.yml`) : onze fichiers
   étaient lus, dont sept dormants, si bien qu'une métrique vue seulement par une
   règle qui ne s'évalue jamais aurait compté comme câblée (aucune ne l'était,
   mesuré).
