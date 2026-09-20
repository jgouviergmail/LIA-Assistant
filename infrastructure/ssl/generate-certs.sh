#!/bin/sh
# Self-signed TLS certificate for the DEV stack, shared by api and web through
# the `ssl_certs` volume (ssl-init runs this at every `docker compose up`).
#
# The certificate is renewed on what it IS, never on how old it is: a browser
# that trusted it (`task dev:trust-cert`, needed for WebAuthn) keeps trusting
# it for as long as it is served. Measured 2026-09-19: an age check (30 days)
# regenerated a certificate issued for 365 days at the first restart after a
# month, and every trusted browser fell back to « Your connection is not
# private ». A certificate is therefore KEPT unless one of three things holds:
#   - it expires within SSL_RENEW_BEFORE_DAYS (default 30);
#   - its SAN no longer covers SSL_DOMAIN (or the LAN IP a nip.io name carries);
#   - its key does not match it (a generation interrupted halfway).
# Each case is named on stdout, so `docker logs lia-ssl-init` says why the
# fingerprint changed — and `task dev:trust-cert` must be run again.
#
# Configuration:
#   CERT_DIR               - where the pair lives (default /certs; tests point it elsewhere)
#   SSL_DOMAIN             - primary domain (default localhost)
#   SSL_IP                 - LAN IP to include in the SAN (derived from a nip.io domain)
#   SSL_RENEW_BEFORE_DAYS  - renew when fewer days of validity remain (default 30)
#   SSL_CERT_DAYS          - validity of a newly issued certificate (default 365)

CERT_DIR="${CERT_DIR:-/certs}"
DOMAIN="${SSL_DOMAIN:-localhost}"
RENEW_BEFORE_DAYS="${SSL_RENEW_BEFORE_DAYS:-30}"
CERT_DAYS="${SSL_CERT_DAYS:-365}"
CERT="$CERT_DIR/cert.pem"
KEY="$CERT_DIR/key.pem"

# Extract the IP from a nip.io domain when SSL_IP is not set
# e.g. 192.168.1.100.nip.io -> 192.168.1.100
if [ -z "$SSL_IP" ] && echo "$DOMAIN" | grep -q "nip.io"; then
    SSL_IP=$(echo "$DOMAIN" | sed 's/\.nip\.io$//')
fi

# openssl is needed for the checks as well as for the issuance (alpine ships without it)
if ! command -v openssl >/dev/null 2>&1; then
    apk add --no-cache openssl >/dev/null 2>&1 || { apt-get update >/dev/null 2>&1 && apt-get install -y openssl >/dev/null 2>&1; }
fi
if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is not available: cannot issue or check a certificate" >&2
    exit 1
fi

fingerprint() {
    openssl x509 -in "$CERT" -noout -fingerprint -sha256 2>/dev/null | sed 's/^.*=//'
}

# Why the existing pair cannot be kept (empty when it can).
renewal_reason() {
    if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
        echo "no certificate yet"
        return
    fi
    if ! openssl x509 -in "$CERT" -noout -checkend $((RENEW_BEFORE_DAYS * 86400)) >/dev/null 2>&1; then
        echo "the certificate expires within $RENEW_BEFORE_DAYS days ($(openssl x509 -in "$CERT" -noout -enddate 2>/dev/null))"
        return
    fi
    # One SAN entry per line, matched whole and literally (POSIX grep: busybox
    # has no GNU \b, and a dot in the domain is not a wildcard).
    SAN=$(openssl x509 -in "$CERT" -noout -ext subjectAltName 2>/dev/null | tr ',' '\n' | sed 's/^[[:space:]]*//')
    if ! echo "$SAN" | grep -qxF "DNS:$DOMAIN"; then
        echo "the certificate does not cover $DOMAIN"
        return
    fi
    if [ -n "$SSL_IP" ] && ! echo "$SAN" | grep -qxF "IP Address:$SSL_IP"; then
        echo "the certificate does not cover the LAN IP $SSL_IP"
        return
    fi
    CERT_PUB=$(openssl x509 -in "$CERT" -noout -pubkey 2>/dev/null)
    KEY_PUB=$(openssl pkey -in "$KEY" -pubout 2>/dev/null)
    if [ -z "$KEY_PUB" ] || [ "$CERT_PUB" != "$KEY_PUB" ]; then
        echo "the key does not match the certificate"
        return
    fi
}

REASON=$(renewal_reason)
if [ -z "$REASON" ]; then
    echo "Certificate kept for $DOMAIN: valid past the next $RENEW_BEFORE_DAYS days ($(openssl x509 -in "$CERT" -noout -enddate)), fingerprint $(fingerprint)"
    exit 0
fi

echo "Generating a certificate for $DOMAIN: $REASON"

# Subject Alternative Names: the domain, the in-network service names, the loopback, the LAN IP
SAN="DNS:$DOMAIN,DNS:localhost,DNS:api,DNS:web,IP:127.0.0.1"
if [ -n "$SSL_IP" ]; then
    SAN="$SAN,IP:$SSL_IP"
    echo "Including LAN IP in SAN: $SSL_IP"
fi

# The key first, into a temporary name, so an interruption never leaves a new
# key beside an old certificate; both files land together at the end. An
# issuance that fails is said out loud (docker logs lia-ssl-init) and fails
# the service — the previous pair, if any, stays in place.
if ! openssl genrsa -out "$KEY.new" 2048; then
    echo "Key generation failed; the previous pair is kept" >&2
    rm -f "$KEY.new"
    exit 1
fi
if ! openssl req -new -x509 -key "$KEY.new" -out "$CERT.new" -days "$CERT_DAYS" \
    -subj "/C=FR/ST=Dev/L=Dev/O=LIA/CN=$DOMAIN" \
    -addext "subjectAltName=$SAN"; then
    echo "Certificate issuance failed; the previous pair is kept" >&2
    rm -f "$KEY.new" "$CERT.new"
    exit 1
fi
mv "$KEY.new" "$KEY"
mv "$CERT.new" "$CERT"

# 644 for both: dev-only certificates, readable by the non-root Next.js container
chmod 644 "$CERT" "$KEY"

echo "Certificate generated in $CERT_DIR: valid $CERT_DAYS days, fingerprint $(fingerprint)"
echo "A browser that trusted the previous certificate must trust this one: task dev:trust-cert"
ls -la "$CERT_DIR"
