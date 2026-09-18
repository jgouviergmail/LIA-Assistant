# SandboxEgressProxyDown — Runbook

**Sévérité** : warning
**Composant** : sandbox
**Impact** : aucun script du bac à sable ne peut plus atteindre internet. Le
tool `run_python_tool` refuse toute exécution qui déclare des `hosts`
(`python_sandbox_egress_runs_total{outcome="proxy_unavailable"}`), dit au
modèle de répondre avec ce qu'il a, et la boucle ReAct perd ses rôles
« diagnostiquer un service tiers » et « combler un outil manquant »
(ADR-298). Les exécutions sans réseau ne sont pas concernées.

---

## Définition

```promql
(max(lia_python_sandbox_egress_enabled) == 1)
and
((max(probe_success{job="blackbox-egress"}) or vector(0)) == 0)
```

`for: 5m` (`ALERT_CORE_SANDBOX_EGRESS_DOWN_FOR`). La sonde blackbox interroge
`http://egress:9094/healthz` toutes les 60 s : cinq minutes, c'est cinq échecs,
au-delà d'un redémarrage ordinaire.

### Pourquoi cette alerte existe

Le proxy de sortie (`ironsh/iron-proxy`, service `egress` de l'overlay
`docker-compose.skill-sandbox.yml`) est **la seule porte** d'un run réseau :
le conteneur jetable rejoint le réseau interne `lia-sandbox`, dont le proxy
est l'unique membre routé. Sans lui, le tool échoue **fermé** — c'est voulu
(SEC-001) — mais fermé en silence pour la personne : elle voit une réponse
plus pauvre, jamais une panne. Cette alerte est ce qui rend l'absence visible
(ADR-148 : une capacité qui disparaît sans qu'on le voie).

Elle est **conditionnée par la jauge** `lia_python_sandbox_egress_enabled`,
posée par l'API au démarrage depuis `PYTHON_SANDBOX_EGRESS_ENABLED` : une
installation sans l'overlay n'a pas de proxy, sa sonde n'a pas de série, et
ce n'est pas un incident. `or vector(0)` fait lire une sonde absente comme un
proxy mort **quand la jauge dit que le proxy devrait exister** — le cas d'un
overlay dont le service `egress` n'a jamais démarré.

## Diagnostic

### 1. Le conteneur tourne-t-il ?

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.skill-sandbox.yml ps egress
docker compose -f docker-compose.prod.yml -f docker-compose.skill-sandbox.yml logs --tail 50 egress
```

Le journal normal commence par `sandbox-egress: minting the CA` (au premier
démarrage de la pile — la CA vit dans un tmpfs) puis `sandbox-egress:
starting iron-proxy`, et iron-proxy liste ses écouteurs (`tunnel proxy
starting [::]:3128`, `management server starting [::]:9093`, `metrics server
starting 0.0.0.0:9094`).

| Symptôme dans le journal | Cause | Remède |
|---|---|---|
| `error: opening config file: … proxy.yaml: no such file` | Le volume `lia-egress-config` n'est pas partagé avec ce conteneur, ou son entrypoint n'est pas `infrastructure/sandbox-egress/entrypoint.sh` | Vérifier les montages du service ; `docker volume inspect lia-egress-config` |
| `CA certificate missing KeyUsageCertSign` | Une CA d'un autre outil a été déposée dans `lia-egress-ca` | `docker compose down egress && docker volume rm lia-egress-ca lia-egress-key` puis `up -d egress` (la CA est refaite) |
| Redémarrages en boucle, `permission denied` | `LIA_RUNTIME_UID` ne correspond pas à l'uid de l'API (1000 en prod) — les fichiers 0600 sont d'un autre uid | Aligner `LIA_RUNTIME_UID` dans `.env.prod`, `down` puis `up -d` des trois volumes |

### 2. La sonde atteint-elle le proxy ?

```bash
docker compose exec blackbox-exporter wget -qO- 'http://localhost:9115/probe?module=http_2xx&target=http://egress:9094/healthz' | grep probe_success
```

`probe_success 0` avec un conteneur `egress` sain = le blackbox exporter n'est
pas sur `lia-network`, ou le nom `egress` n'y est pas résolu (service renommé
dans un overlay local).

### 3. L'API voit-elle le proxy ?

```bash
docker compose exec api sh -c 'ls -la /etc/lia-egress/config && wget -qO- --post-data="" --header="Authorization: Bearer $(cat /etc/lia-egress/config/management.token)" http://egress:9093/v1/reload'
```

Attendu : `{"status":"ok"}`. Un `401` = le jeton lu par l'API n'est pas celui
que le proxy a chargé (le proxy a redémarré sur un tmpfs neuf pendant que l'API
gardait l'ancien) — redémarrer l'API suffit, son étape de démarrage republie
le ruleset (`sandbox_egress_ruleset_published_at_boot`).

### 4. Combien de runs ont été refusés ?

```promql
sum by (outcome) (increase(python_sandbox_egress_runs_total[1h]))
```

Tableau Grafana 20 « ReAct · Sandbox Egress (ADR-298) ». Le diagnostic
automatique (ADR-266) joint cette série, la sonde et les événements
`sandbox_egress_run_refused`, `sandbox_egress_boot_publish_failed`,
`sandbox_egress_withdraw_publish_failed`.

## Résolution

- Proxy arrêté : `docker compose … up -d egress`. Rien à republier à la main :
  chaque run réseau rend le ruleset complet avant de démarrer, et l'API le
  republie au démarrage.
- Alerte sur une installation qui ne veut PAS de réseau : mettre
  `PYTHON_SANDBOX_EGRESS_ENABLED=false` (la jauge passe à 0, l'alerte s'éteint
  au prochain scrape) — et retirer l'overlay si le bac à sable lui-même n'est
  pas voulu.

## Ce que cette alerte ne dit pas

- Un ruleset refusé au reload (`sandbox_egress_withdraw_publish_failed`) alors
  que le proxy répond : le proxy garde ses règles précédentes, le run suivant
  republie. Lire le journal du proxy (`pipeline reload failed`).
- Une exécution réseau qui échoue sur un `403` du proxy : ce n'est pas une
  panne, c'est un hôte non déclaré ou non permis — visible dans le journal
  d'audit du proxy (`"rejected_by":"allowlist"`), jamais dans cette alerte.

## Références

- ADR-298 — `docs/architecture/ADR-298-Sandbox-Egress-Toolbox.md`
- `docs/technical/REACT_EXECUTION_MODE.md` § « Reaching the Internet »
- `infrastructure/sandbox-egress/entrypoint.sh`, `proxy.bootstrap.yaml`
