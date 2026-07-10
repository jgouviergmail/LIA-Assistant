# PublicEndpointDown / CertificateExpirySoon - Runbook

**Severity**: critical (PublicEndpointDown) / warning (CertificateExpirySoon)
**Component**: tunnel
**Impact**: Users cannot reach LIA at all — the public URL is dead even though every container may be healthy. Covers the whole ingress path: Cloudflare edge → cloudflared tunnel (host systemd) → web frontend.
**SLA Impact**: Yes — global availability.

---

## 1. Alert Definition

**Alert Names**: `PublicEndpointDown`, `CertificateExpirySoon`

**Prometheus Expressions**:
```promql
probe_success{job="blackbox-public"} == 0                                  # for: 3m
(probe_ssl_earliest_cert_expiry{job="blackbox-public"} - time()) / 86400
  < ALERT_CORE_CERT_EXPIRY_DAYS                                            # for: 1h
```

blackbox-exporter probes the public URL end-to-end. The target is injected from `.env` (`BLACKBOX_PUBLIC_PROBE_URL`) into a file_sd file at Prometheus startup — the real domain is never committed (open-source repo). Empty variable = probe disabled (dev default).

**Labels**: `severity: critical|warning`, `component: tunnel`, `tier: core`

---

## 2. Symptoms

### What Users See
- Browser error on the public URL (52x Cloudflare page, timeout, or TLS warning).

### What Ops See
- `probe_success{job="blackbox-public"} == 0` while `up{job="lia-api"}` may still be 1 (containers healthy, ingress dead → tunnel problem).
- `journalctl -u cloudflared` errors on the RPi5 host.

---

## 3. Possible Causes

### Cause 1: cloudflared tunnel down (High Likelihood — known recurring issue)
The tunnel runs as a **host systemd service** (`/etc/cloudflared/config.yml`), not a container. Recurring disconnections were mitigated 2026-03 (HTTP/2 transport, WiFi powersave off, persistent journal) but remain the #1 suspect.
```bash
ssh -p 2222 jgo@192.168.0.14
systemctl status cloudflared
journalctl -u cloudflared --since "-30 min" --no-pager | tail -50
```

### Cause 2: Web frontend container down (Medium Likelihood)
`probe_success == 0` **and** container alerts firing → the ingress is fine, the origin is dead. Check `ContainerRestartLoop` / `ServiceDown` first (inhibition may already have grouped them).

### Cause 3: Cloudflare edge incident or stuck cert renewal (Low Likelihood)
Check https://www.cloudflarestatus.com/. Edge certificates auto-renew; `CertificateExpirySoon` firing means that automation is stuck — open the Cloudflare dashboard → SSL/TLS.

---

## 4. Resolution Steps

### Immediate
```bash
# On the RPi5 host:
sudo systemctl restart cloudflared
journalctl -u cloudflared -f   # wait for "Registered tunnel connection" ×4
```

### Post-Recovery Verification
- `probe_success{job="blackbox-public"} == 1`; alert resolves.
- Open the public URL from a device OUTSIDE the LAN (mobile network) — LAN access can mask a tunnel-only outage.
