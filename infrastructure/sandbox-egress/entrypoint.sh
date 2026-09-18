#!/bin/sh
# Entrypoint of the sandbox egress proxy (ADR-298).
#
# Runs as the uid the API shares (`user:` in compose), never as root: every file
# below is created by that uid into three tmpfs volumes, so nothing is ever
# chown'ed and nothing ever touches a disk. A separate init container was
# measured wrong (2026-09-18): it wrote into the tmpfs, exited, and Docker
# released the tmpfs before the proxy mounted it — the proxy started on nothing.
#
# Idempotent: what exists is kept, so a proxy restart while the API still holds
# the config volume keeps the token the API already read. A fresh stack mints a
# fresh CA — the key never outlives the process tree that made it, which is why
# no rotation procedure exists.
#
#   /etc/lia-egress/ca      ca.crt            proxy + every sandbox (read-only)
#   /etc/lia-egress/key     ca.key            proxy ONLY
#   /etc/lia-egress/config  proxy.yaml, management.token, secrets/
#                                             API (rw) + proxy
set -eu

CA_DIR=/etc/lia-egress/ca
KEY_DIR=/etc/lia-egress/key
CFG_DIR=/etc/lia-egress/config
SRC_DIR=/opt/lia-egress
export HOME=/tmp

mkdir -p "$CFG_DIR/secrets"
chmod 0700 "$CFG_DIR/secrets"

if [ ! -s "$KEY_DIR/ca.key" ] || [ ! -s "$CA_DIR/ca.crt" ]; then
  echo "sandbox-egress: minting the CA"
  # iron-proxy refuses a plain self-signed certificate (measured: "CA
  # certificate missing KeyUsageCertSign"); ca.cnf carries the v3 extensions.
  openssl req -x509 -newkey rsa:3072 -nodes -days 3650 \
    -config "$SRC_DIR/ca.cnf" \
    -keyout "$KEY_DIR/ca.key" -out "$CA_DIR/ca.crt" 2>/dev/null
  chmod 0600 "$KEY_DIR/ca.key"
  chmod 0644 "$CA_DIR/ca.crt"
fi

if [ ! -s "$CFG_DIR/management.token" ]; then
  # 32 random bytes as hex — the bearer the API presents on POST /v1/reload.
  od -An -tx1 -N32 /dev/urandom | tr -d ' \n' > "$CFG_DIR/management.token"
  chmod 0600 "$CFG_DIR/management.token"
fi

if [ ! -s "$CFG_DIR/proxy.yaml" ]; then
  cp "$SRC_DIR/proxy.bootstrap.yaml" "$CFG_DIR/proxy.yaml"
  chmod 0600 "$CFG_DIR/proxy.yaml"
fi

IRON_MANAGEMENT_API_KEY="$(cat "$CFG_DIR/management.token")"
export IRON_MANAGEMENT_API_KEY
echo "sandbox-egress: starting iron-proxy"
exec iron-proxy -config "$CFG_DIR/proxy.yaml"
