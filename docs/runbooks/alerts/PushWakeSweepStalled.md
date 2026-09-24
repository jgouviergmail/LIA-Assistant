# PushWakeSweepStalled — Runbook

**Sévérité** : warning
**Composant** : push
**Impact** : les notifications push de Google (Gmail, Agenda, Drive) sont bien
reçues et mises en file, mais plus rien ne les sert : les surveillances de mail
(ADR-281), l'indexation poussée des espaces de connaissances (ADR-261/262) et
les réveils du heartbeat attendent. Rien n'est perdu tant que la charge d'un
réveil n'a pas expiré ; au-delà, le prochain passage périodique rattrape.

---

## Définition

```promql
(sum(increase(push_wakes_enqueued_total[30m])) > 0)
and on()
((sum(increase(push_wakes_total[30m])) or vector(0)) == 0)
```

`for: 5m`. La fenêtre vient de `ALERT_CORE_PUSH_WAKE_STALL_WINDOW`
(`infrastructure/observability/prometheus/thresholds/*.env`).

- `push_wakes_enqueued_total{provider}` compte ce que le chemin webhook a MIS EN
  FILE (une charge nouvelle par compte et fournisseur — une rafale de
  notifications se fond en un seul réveil).
- `push_wakes_total{provider, outcome}` compte chaque réveil SERVI, quelle que
  soit son issue (`cooldown` et `stale` compris : ce sont des réveils servis).

Des réveils en file et **aucun** servi : le balayage ne tourne pas. Le côté
servi lit `or vector(0)` parce qu'un compteur qui n'a jamais tiré n'expose
aucune série — et « rien servi depuis le démarrage » était exactement
l'incident d'origine.

---

## Diagnostic

### 1. Le balayage a-t-il un leader, et tourne-t-il ?

```bash
docker logs lia-api-prod --since 30m 2>&1 | grep -E "scheduler_elected|heartbeat_wake_sweep|maximum number of running instances"
```

- aucun `scheduler_elected_jobs_summary` récent : pas de leader — lire la clé
  Redis du bail (`SCHEDULER_LEADER_LOCK_KEY`, `src/core/constants.py`) : absente,
  personne ne l'a prise ; présente, son propriétaire ne fait pas tourner ses tâches ;
- des « maximum number of running instances reached » sur
  `heartbeat_wake_sweep` : l'exécution précédente ne rend pas la main.

### 2. Un réveil bloque-t-il ?

Chaque réveil est servi sous un plafond (`PUSH_WAKE_SERVE_TIMEOUT_SECONDS`) et
un seul à la fois (ADR-304) : un réveil qui ne rend pas la main est coupé et
compté `outcome="timeout"`. Des `timeout` en rafale nomment le fournisseur en
cause :

```promql
sum by (provider, outcome) (increase(push_wakes_total[1h]))
```

### 3. Une transaction est-elle tenue ?

C'est la forme de l'incident d'origine (une session gardée ouverte pendant des
appels Google) :

```sql
SELECT pid, state, now() - xact_start AS held, left(query, 80)
FROM pg_stat_activity
WHERE state = 'idle in transaction' AND now() - xact_start > interval '30 seconds';
```

---

## Remédiation

1. **Pas de leader** : redémarrer l'API (`docker restart lia-api-prod`) — un
   worker reprendra le bail.
2. **Un réveil bloque malgré le plafond** : relever la trace du worker
   (`py-spy dump` si disponible), puis redémarrer ; ouvrir un défaut avec le
   fournisseur et l'issue observée.
3. **Transaction tenue** : c'est un défaut de la classe ADR-304 (aucune
   transaction ouverte pendant un appel réseau) — l'identifier par sa requête
   et le corriger à la source ; redémarrer ne fait que déplacer le problème.

---

## Vérification

```promql
sum(increase(push_wakes_total[10m]))
```

doit redevenir positif dans les minutes qui suivent, et l'alerte se résoudre.

---

## Historique

- **2026-09-22** — Balayage bloqué 14 minutes, 0 réveil servi depuis le
  démarrage contre ~206 par 24 h d'ordinaire. Cause : le drainage des
  changements Drive tenait une transaction PostgreSQL pendant une pagination
  sans borne (863 s `idle in transaction`), et `max_instances=1` sautait tous
  les ticks suivants. Corrigé par ADR-304 ; cette alerte a été ajoutée parce
  que rien ne l'avait signalé.
