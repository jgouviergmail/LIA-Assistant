# ContainerMemoryNearLimit — Runbook

**Sévérité** : warning
**Composant** : container
**Impact** : le conteneur sera tué par l'OOM killer du noyau à 100 %, puis
redémarré par `restart: unless-stopped` — coupure de service de quelques
secondes à quelques minutes selon le service.

---

## Définition

```promql
(
  container_memory_working_set_bytes{name=~"lia.*"}
  / container_spec_memory_limit_bytes{name=~"lia.*"} > 0
) * 100 > 95
```

`for: 10m` — un pic transitoire ne déclenche pas.

### Pourquoi `working_set` et non `usage`

`container_memory_usage_bytes` compte **RSS + page cache**. Le noyau récupère le
page cache avant de tuer quoi que ce soit : un conteneur qui fait beaucoup
d'E/S fichier peut donc rester indéfiniment à 98 % de sa limite sans le moindre
risque.

Prometheus est le pire cas : son TSDB mappe en mémoire jusqu'à
`--storage.tsdb.retention.size` (2 Go en prod) dans un cgroup de 512 Mo. Son
cache **remplit la limite par construction**. Une alerte basée sur `usage`
sonnait donc en boucle sur un conteneur parfaitement sain — c'est ce qui a
motivé le passage à `working_set` (`usage - inactive_file`), la grandeur que le
noyau utilise réellement pour décider de l'OOM.

**Conséquence pratique** : depuis ce changement, une occurrence de cette alerte
signale une vraie pression mémoire. Elle mérite d'être traitée, pas acquittée.

---

## Diagnostic

### 1. Confirmer la pression réelle

```bash
ssh -p 2222 <user>@<prod-host>
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

`docker stats` affiche `usage` (cache inclus) : un écart important avec l'alerte
est normal et confirme que le cache domine.

Pour la décomposition exacte :

```bash
CG=$(docker inspect -f '{{.Id}}' lia-<service>-prod)
cat /sys/fs/cgroup/system.slice/docker-$CG.scope/memory.stat \
  | grep -E "^(anon|file|inactive_file|slab) "
```

`working_set ≈ anon + (file - inactive_file) + slab`.

### 2. Y a-t-il déjà eu un OOM ?

```bash
dmesg -T | grep -i "killed process" | tail -20
docker inspect lia-<service>-prod --format '{{.State.OOMKilled}} {{.RestartCount}}'
```

Si `OOMKilled=true`, la limite est franchement insuffisante — passer
directement à la section « Redimensionner ».

### 3. Marge sur l'hôte

Le serveur est un **Raspberry Pi 5, 16 Go** (ADR-033). Les plafonds Compose
totalisent ~12,4 Go mais ne sont que des plafonds ; les **réservations**
totalisent ~3,3 Go, c'est le seul engagement ferme.

```bash
free -h
```

Tant que la mémoire disponible reste confortable, relever un plafond de
quelques centaines de Mo est sans danger.

---

## Remédiation

### Cas A — Prometheus

Sa mémoire suit d'abord le **nombre de séries actives** :

```bash
curl -s 'http://127.0.0.1:9090/api/v1/query?query=prometheus_tsdb_head_series' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['result'][0]['value'][1])"
```

Ordre de grandeur mesuré : **~100 Mo pour ~21 000 séries** (environnement de dev,
sans trafic). Ajouter les 86 règles d'enregistrement et les 15 alertes évaluées
toutes les 30 s.

Leviers, du moins au plus destructeur :

1. **Relever la limite** (`docker-compose.prod.yml`, service `prometheus`) — à
   privilégier tant que l'hôte a de la marge.
2. **Réduire la rétention** : `--storage.tsdb.retention.time` / `.size`. Réduit
   surtout le cache et le disque, peu le working set.
3. **Espacer la collecte** : les intervalles sont déjà à 30 s / 60 s.
4. **Réduire la cardinalité** : chercher les métriques à labels à forte
   cardinalité.

```promql
topk(10, count by (__name__)({__name__=~".+"}))
```

### Cas B — API

Vérifier d'abord une fuite plutôt que la taille : la mémoire doit se stabiliser
en plateau, pas croître linéairement.

```promql
container_memory_working_set_bytes{name="lia-api-prod"}[6h]
```

### Cas C — tout service

Relever la limite, puis redéployer :

```bash
# depuis le poste de dev
task deploy:prod
```

Le rebuild est systématique (voir la référence du pipeline de déploiement).

---

## Vérification

Après redéploiement, l'alerte doit se résoudre en moins de 10 minutes :

```promql
(
  container_memory_working_set_bytes{name="lia-<service>-prod"}
  / container_spec_memory_limit_bytes{name="lia-<service>-prod"}
) * 100
```

Contrôler aussi qu'aucune boucle de redémarrage n'a été introduite
(`ContainerRestartLoop`).

---

## Historique

- **2026-08-16** — ~15 alertes sur plusieurs jours, toutes sur les conteneurs
  `lia-demo-instance-*`. Diagnostic : 7 services du démonstrateur n'avaient
  aucun `mem_limit`, cAdvisor publie alors `container_spec_memory_limit_bytes`
  à **0**, et `x/0 = +Inf` en PromQL — qui passe le filtre `quotient > 0` de
  l'ancienne expression. Deux corrections : le garde `> 0` déplacé sur le
  **dénominateur** (`/ (limit > 0)`, une série sans limite est éliminée avant
  la division, cas promtool ajouté), et un `mem_limit` posé sur chacun des 7
  services du démonstrateur (garde :
  `test_demo_instance_envelope.py::test_every_service_declares_a_memory_ceiling`).
- **2026-07-28** — Alerte en boucle sur `lia-prometheus-prod` (98,41 %).
  Diagnostic : l'expression utilisait `container_memory_usage_bytes`, donc
  comptait le page cache du TSDB. Deux corrections : passage à
  `working_set`, et limite Prometheus ramenée de 256 Mo à 512 Mo — elle avait
  été resserrée en v1.13.1 sur un instantané à ~98 Mo, avant que la charge ne
  triple.
