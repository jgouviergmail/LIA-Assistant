# RadioNewsroomStalled — Runbook

**Sévérité** : warning
**Composant** : radio
**Impact** : la rédaction de la radio personnelle (ADR-324) ne classe plus aucun
sujet. Les sessions continuent d'être produites avec ce que la rédaction détient
déjà — sujets de moins de `NEWS_MAX_AGE_S` —, puis sans aucune actualité : la
grille ne programme pas de format d'information sans candidats. Le reste de la
radio (journée de l'auditeur, chroniques, habillage) n'est pas touché, et rien
n'est facturé tant que la rédaction ne lit rien.

---

## Définition

```promql
(time() - max(radio_newsroom_last_run_timestamp_seconds)) > 1800
```

`for: 10m`. Le seuil vient de `ALERT_CORE_RADIO_NEWSROOM_STALL_SECONDS`
(`infrastructure/observability/prometheus/thresholds/*.env`).

`radio_newsroom_last_run_timestamp_seconds` est horodaté par chaque tic de la
rédaction mené à son terme — une passe, ou un tic pendant lequel la radio est
coupée par l'opérateur (une coupure n'est pas une panne) — et par rien d'autre :

- **jamais au démarrage** : uvicorn recycle ses workers (`--limit-max-requests`),
  et un horodatage de démarrage masquerait une rédaction bloquée ;
- **jamais par une passe en échec**.

Son **âge** couvre donc les deux façons dont la rédaction se tait : toutes les
passes échouent, ou la tâche ne tourne plus. La série n'existe que là où le
déploiement livre la radio (`RADIO_ENABLED=true`) : ailleurs, l'alerte ne peut
pas se déclencher.

---

## Diagnostic

### 1. Les tics échouent-ils, ou ne tournent-ils plus ?

```promql
sum by (outcome) (increase(radio_newsroom_passes_total[1h]))
```

- des `failed` et aucun `completed` / `cut` / `off` : les passes **échouent** —
  aller en 2 ;
- **rien du tout** : la tâche **ne tourne plus** — aller en 3.

### 2. Pourquoi les passes échouent

Chaque échec laisse une ligne `radio_newsroom_pass_failed` qui porte les faits
de la base (`db_error`, `sqlstate`, `constraint`, `table`) et jamais son texte
(ADR-317) :

```bash
docker logs lia-api-prod --since 1h 2>&1 | grep radio_newsroom_pass_failed
```

- une erreur de base (`sqlstate` présent) : PostgreSQL indisponible, saturé, ou
  une migration de la radio non appliquée (`alembic current` contre `alembic heads`) ;
- une erreur sans `sqlstate` : un défaut du code — ouvrir un défaut avec le
  `error_type` et l'heure.

Un flux ou un article qui échoue n'échoue **jamais** la passe (isolation par
unité) : ce sont les lectures de flux qui le disent.

```promql
sum by (outcome) (increase(radio_newsroom_feed_readings_total[1h]))
```

Beaucoup de `failed` et aucun `read` alors que les passes aboutissent : le
réseau sortant du conteneur est coupé (proxy, DNS, pare-feu) — la rédaction
tourne, mais ne lit plus rien.

### 3. Pourquoi la tâche ne tourne plus

La tâche `radio_newsroom_collect` ne tourne que sur le leader du planificateur :

```bash
docker logs lia-api-prod --since 30m 2>&1 | grep -E "scheduler_elected|radio_jobs_scheduled|radio_newsroom_collect|maximum number of running instances"
```

- aucun `radio_jobs_scheduled` depuis le dernier démarrage : la tâche n'a pas
  été enregistrée — vérifier `RADIO_ENABLED` dans l'environnement du conteneur ;
- aucun `scheduler_elected_jobs_summary` récent : pas de leader — lire la clé
  Redis du bail (`SCHEDULER_LEADER_LOCK_KEY`, `src/core/constants.py`) ;
- des « maximum number of running instances reached » sur
  `radio_newsroom_collect` : la passe précédente ne rend pas la main alors
  qu'elle est bornée (`RADIO_NEWSROOM_PASS_TIMEOUT_SECONDS`) — seules la purge
  et la synchronisation du catalogue, deux requêtes, tournent hors de cette
  borne : chercher une transaction tenue.

```sql
SELECT pid, state, now() - xact_start AS held, left(query, 80)
FROM pg_stat_activity
WHERE state <> 'idle' AND now() - xact_start > interval '60 seconds';
```

---

## Remédiation

1. **Base indisponible ou migration manquante** : rétablir la base, ou appliquer
   les migrations (`task db:migrate` sur l'instance) ; la passe suivante reprend
   d'elle-même.
2. **Pas de leader** : redémarrer l'API (`docker restart lia-api-prod`) — un
   worker reprendra le bail.
3. **Réseau sortant coupé** : rétablir la sortie du conteneur ; les flux en échec
   sont relus après leur temporisation (`RADIO_NEWSROOM_BACKOFF_MAX_SECONDS` au
   plus).
4. **Défaut du code** : couper la radio le temps de la correction
   (Administration › Capacités de la plateforme › Radio personnelle) — les tics deviennent `off`,
   l'alerte se résout, et aucun serveur tiers n'est plus lu.

---

## Vérification

```promql
sum by (outcome) (increase(radio_newsroom_passes_total[15m]))
```

doit remontrer des `completed` (ou `off` si la radio a été coupée), et l'âge
affiché sur le tableau de bord **31 - Radio** (« Newsroom last run ») redescendre
sous l'intervalle de la tâche (`RADIO_NEWSROOM_INTERVAL_SECONDS`).
