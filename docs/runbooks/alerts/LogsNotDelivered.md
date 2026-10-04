# LogsNotDelivered — Runbook

**Sévérité** : warning
**Composant** : observability
**Impact** : des lignes de log n'arrivent pas dans Loki. Elles sont perdues :
aucune recherche Loki, aucun tableau Grafana et aucune preuve de l'auto-diagnostic
(qui lit Loki) ne les verra. L'application elle-même n'est pas touchée.

---

## Définition

```promql
(
  (sum(increase(loki_write_dropped_entries_total{job="alloy"}[15m])) or vector(0))
  + (sum(increase(loki_discarded_samples_total{job="loki", reason!="greater_than_max_sample_age"}[15m])) or vector(0))
) > 0
```

Deux étapes peuvent perdre une ligne :

- **Alloy l'abandonne** (`loki_write_dropped_entries_total`) : ses nouvelles
  tentatives vers Loki sont épuisées (`backoff_config` de
  `infrastructure/observability/promtail/promtail-config.yml`, jusqu'à 5 min) ;
- **Loki la refuse** (`loki_discarded_samples_total`) : limite de débit, limite de
  flux, ligne trop grande (`limits_config` de
  `infrastructure/observability/loki/loki-config.yml`).

Une ligne refusée parce que trop ancienne (`greater_than_max_sample_age`) n'est pas
comptée : Alloy relit le log d'un conteneur depuis le début quand ses positions
sont perdues, et ces lignes-là avaient été stockées la première fois.

Les deux compteurs ne sont scrutés que pour cette alerte et le tableau 16 (jobs
`alloy` et `loki` de `prometheus.yml`, listes de séries conservées).

---

## Diagnostic

### 1. Quelle étape, quelle raison ?

```promql
sum by (reason) (increase(loki_write_dropped_entries_total{job="alloy"}[1h]))
sum by (reason) (increase(loki_discarded_samples_total{job="loki"}[1h]))
```

Le tableau 16 (« Recording Rules & Alerts Health ») trace les deux, ligne
« Observability pipeline ».

### 2. Alloy : pourquoi ses envois échouent

```bash
docker logs lia-promtail-prod --since 1h 2>&1 | grep -iE "error|failed|retry" | tail -20
```

- `connection refused`, `no such host` : Loki redémarre ou est tombé — vérifier
  `up{job="loki"}` (l'alerte `ObservabilityScrapeTargetMissing` le dit aussi) ;
- `429` : Loki limite le débit — voir l'étape 3 ;
- `context deadline exceeded` : Loki répond trop lentement (requêtes lourdes en
  parallèle) — vérifier sa mémoire (`ContainerMemoryNearLimit`).

### 3. Loki : pourquoi il refuse

| `reason` | Cause | Réponse |
|---|---|---|
| `rate_limited` | débit global au-dessus de `ingestion_rate_mb` / `ingestion_burst_size_mb` | trouver le conteneur bavard (`sum by (container) (rate({project="lia"}[5m]))`) avant de relever la limite |
| `per_stream_rate_limit` | un flux au-dessus de `per_stream_rate_limit` | idem, pour un seul conteneur |
| `stream_limit` | trop de flux (`max_streams_per_user`) | un label à valeurs ouvertes a été promu : la garde `test_promtail_label_cardinality_guard.py` doit l'interdire |
| `line_too_long` | ligne au-dessus de la taille max | Alloy tronque à `max_line_size` : vérifier que la limite de Loki n'est pas plus basse |

---

## Résolution

Corriger la cause (étapes 2 et 3). Les lignes perdues ne reviennent pas ;
l'alerte se résout seule 15 minutes après la dernière perte.

## Références

- Pipeline de logs : `infrastructure/observability/promtail/promtail-config.yml`
- Limites de Loki : `infrastructure/observability/loki/loki-config.yml`
- Tableau 16, ligne « Observability pipeline » : `docs/technical/GRAFANA_DASHBOARDS.md`
