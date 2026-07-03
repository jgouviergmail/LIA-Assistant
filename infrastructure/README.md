# Infrastructure

Operational configuration for LIA's deployment: Docker Compose services,
database seeds, observability stack (Prometheus, Grafana, Loki, Tempo),
Cloudflare tunnel, nginx, and the in-container DevOps CLI.

## Network exposure model (production)

`cloudflared` (running on the host, outside Compose) is the **single public
entry point**. Everything else binds to loopback:

| Service | Host port | Binding |
|---|---|---|
| web (Next.js) | 3000 | published (reached via cloudflared) |
| api (FastAPI) | 8000, 9091 | `127.0.0.1` only |
| postgres | 5432 | `127.0.0.1` only |
| grafana | 3001 | `127.0.0.1` only |
| prometheus | 9090 | `127.0.0.1` only |
| loki / tempo / OTLP | 3100, 3200, 4317, 4318 | `127.0.0.1` only |
| portainer | 9000 | `127.0.0.1` only |
| cadvisor / exporters | 8080, 9100, 9187, 9121 | `127.0.0.1` only |
| redis | — | not published |

Container-to-container traffic goes through the Compose network using
service names (`prometheus` scrapes `cadvisor:8080`, promtail pushes to
`loki:3100`, …) and is **not affected** by host port bindings.

To reach an internal service from another machine, use an SSH tunnel:

```bash
# DBeaver/pgAdmin against prod Postgres
ssh -p 2222 -L 5432:127.0.0.1:5432 <user>@<prod-host>

# Grafana
ssh -p 2222 -L 3001:127.0.0.1:3001 <user>@<prod-host>
```

or add a dedicated hostname to the cloudflared ingress config
(`/etc/cloudflared/config.yml`) pointing at the loopback port.

## ⚠️ Docker bypasses ufw (DOCKER chain)

**A `ufw deny` rule does NOT protect a Docker-published port.** Docker
inserts its own `DOCKER` chain into the iptables `FORWARD` path, which is
evaluated **before** ufw's chains. A service published as `"9090:9090"`
(i.e. `0.0.0.0:9090`) is therefore reachable from the LAN even when ufw
shows the port as denied. This is the reason every internal service in
`docker-compose.prod.yml` binds explicitly to `127.0.0.1` — loopback
binding is enforced by the kernel at bind time and does not depend on any
firewall rule.

If host-level filtering of Docker traffic is ever needed (e.g. allowing a
specific LAN IP), the supported hook is the `DOCKER-USER` chain, which
Docker guarantees is evaluated first and never flushes:

```bash
# Example: drop LAN access to a published port from everything except one IP
iptables -I DOCKER-USER -p tcp --dport 5432 ! -s 192.168.0.10 -j DROP
```

Rules added by `ufw` itself never apply to published container ports — do
not rely on them. Verify actual exposure from **another machine** on the
LAN, not from the host itself (loopback always answers locally):

```bash
nmap -Pn -p 22,80,443,3000,3001,5432,8000,8080,9000,9090,9100,9121,9187 <prod-host>
# Expected open: SSH + the ports intentionally published (web 3000)
```

## Directory map

- `docker/` — shared Compose service definitions, Postgres init SQL
- `database/` — seeds (personalities, pricing, LLM config)
- `observability/` — Prometheus rules, Grafana dashboards/provisioning, Loki/Tempo/promtail configs
- `cloudflared/` — tunnel notes (live config is on the host at `/etc/cloudflared/config.yml`)
- `nginx/`, `ssl/` — reverse-proxy assets (legacy/local scenarios)
- `logwatch/` — daily log digests on the prod host
- `pgadmin/` — dev-only DB admin UI
- `claude-cli/` — in-container DevOps CLI (see `CLAUDE.server.md`)
