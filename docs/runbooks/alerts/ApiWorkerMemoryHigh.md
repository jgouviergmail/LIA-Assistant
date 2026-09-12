# ApiWorkerMemoryHigh — Runbook

**Sévérité** : warning
**Composant** : api
**Impact** : un seul processus worker de l'API tient un tas au-dessus du
plafond déclaré. Le conteneur `lia-api-prod` a un plafond de 8 Gio pour
quatre workers : un worker à 3 Go n'est pas encore un incident, deux le sont
(mesuré le 2026-09-11 : deux workers ayant chacun chargé le STT ont porté le
conteneur de 4,2 à 7,0 Go en trois minutes, et un troisième l'aurait tué).

---

## Définition

```promql
max by (pid) (lia_worker_memory_bytes{kind="anon"}) / 1048576 > 3072
```

`for: 10m` — un pic transitoire (un rendu de document, une transcription en
cours) ne déclenche pas.

### Pourquoi par worker, et pourquoi `anon`

L'API tourne sous plusieurs workers uvicorn dans un seul conteneur. cAdvisor ne
voit que le conteneur, et le mode multiprocess de `prometheus_client` n'exporte
aucune métrique `process_*` : jusqu'à l'ADR-283, la seule mesure mémoire de
l'API était celle du conteneur entier. Elle pouvait dire que le conteneur était
passé de 2,5 à 5,3 Go en deux jours (8-10/09/2026) sans dire **quel processus**
tenait quoi, ni si c'était du tas ou du cache.

`lia_worker_memory_bytes` est lue par chaque worker dans son propre
`/proc/self/status` (`multiprocess_mode="liveall"` : une série par worker
vivant, qui disparaît avec lui). Seule la composante `anon` compte : les pages
`file` sont les bibliothèques partagées que le noyau récupère, `shmem` est le
mmap des métriques. Le tas — objets Python, poids de modèles, arènes ONNX —
est ce que le processus tient vraiment.

---

## Diagnostic

### 1. Lire ce que le worker tient

Tableau de bord **03 — Infrastructure & Resources**, ligne « Container
Resources » : les panneaux « Mémoire résidente par worker API (anon) » et
« Modèles STT résidents par worker », côte à côte, sur le même `pid`.

```promql
max by (pid) (lia_worker_memory_bytes{kind="anon"})
max by (pid) (voice_stt_recognizers_loaded)
```

Trois lectures possibles :

| Lecture | Signature | Cause |
|---|---|---|
| **Un modèle STT** | le worker en alerte a `voice_stt_recognizers_loaded ≥ 1`, les autres non | une transcription locale l'a chargé (~0,8 Go par recognizer, mesuré 2026-09-12) |
| **Deux modèles** | `voice_stt_recognizers_loaded = 2` sur ce worker | `VOICE_STT_MAX_RECOGNIZERS` relevé au-dessus de 1, ou deux langues demandées |
| **Une fuite** | pas de STT, courbe qui monte sans plateau sur des heures | à instruire (recensement d'objets, ADR-283 § « ce qui reste ouvert ») |

### 2. Confirmer sur l'hôte

```bash
ssh -p 2222 <user>@<prod-host>
docker exec lia-api-prod ps -eo pid,rss,etime,args | grep -E "spawn_main|serve"
docker exec lia-api-prod sh -c 'grep -E "^(RssAnon|RssFile|RssShmem)" /proc/<pid>/status'
```

Le `pid` de l'alerte est celui du conteneur (même espace de noms que `ps`
ci-dessus). Un worker recyclé par `--limit-max-requests` change de pid : la
série disparaît, l'alerte se résout d'elle-même — ce n'est pas une correction.

### 3. Marge du conteneur

```bash
docker exec lia-api-prod sh -c 'echo $(( $(cat /sys/fs/cgroup/memory.current) / 1048576 )) MB / $(( $(cat /sys/fs/cgroup/memory.max) / 1048576 )) MB'
```

Si la somme des workers approche le plafond, l'alerte
`ContainerMemoryNearLimit` suit ; agir avant.

---

## Remédiation

### Cas A — un modèle STT par worker

C'est le cas nominal après une session vocale : le worker garde son recognizer
(≈ 0,8 Go) pour éviter 2,6 s de rechargement à la phrase suivante. Rien à
faire tant qu'un seul worker le porte. Si plusieurs workers le portent en même
temps, c'est que plusieurs sessions vocales sont tombées sur des processus
différents — la borne structurelle est le nombre de workers × 0,8 Go, à
comparer au plafond du conteneur (`WEB_CONCURRENCY`, `docker-compose.prod.yml`).

### Cas B — deux recognizers dans un worker

`VOICE_STT_MAX_RECOGNIZERS` est à 1 par défaut (la langue la moins récemment
utilisée est libérée, et la mémoire revient à l'OS — mesuré : −1 166 Mo pour
deux recognizers). Une valeur supérieure est un choix explicite de
l'exploitant, à tenir face au plafond : chaque unité coûte ~0,8 Go **par
worker** qui l'atteint.

### Cas C — croissance sans plateau

Un worker sans STT au-dessus du seuil, ou une courbe qui monte sur des heures
sans se stabiliser : une fuite. Le recyclage (`--limit-max-requests 10000`,
environ une semaine au rythme de production) la borne, il ne la corrige pas.
Instruire avec un recensement d'objets dans le worker vivant (Python 3.14,
`sys.remote_exec`, PEP 768 — lecture seule, mais une injection dans un processus
de production : à décider, pas à automatiser) et rapporter dans l'ADR-283.

### Ce qu'il ne faut pas faire

- **Relever le seuil** pour faire taire l'alerte : le seuil est au-dessus de
  toute charge légitime d'un worker (≈ 1,1 Go de tas après une journée de chats,
  + 0,8 Go de STT) et en dessous de ce qu'un second modèle ou une fuite coûte.
- **Baisser `--limit-max-requests`** pour recycler plus souvent : chaque
  recyclage coûte ~11 s d'import et un échauffement de plusieurs centaines de
  Mo, et coupe les flux SSE plus longs que `--timeout-graceful-shutdown`.

---

## Références

- ADR-283 — Un worker API a une anatomie déclarée et mesurée
- `apps/api/src/infrastructure/observability/process_memory.py` — la jauge et
  son échantillonneur
- `apps/api/src/domains/voice/stt/sherpa_stt.py` — le cache borné des
  recognizers
- [ContainerMemoryNearLimit.md](./ContainerMemoryNearLimit.md) — l'alerte au
  niveau du conteneur
