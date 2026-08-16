#!/bin/sh
# Generate self-signed SSL certificates for development
# This script runs inside a container and generates certs for both web and api
#
# Configuration:
#   SSL_DOMAIN  - Primary domain for the certificate (default: localhost)
#   SSL_IP      - LAN IP address to include in SAN (optional)

CERT_DIR="/certs"
DOMAIN="${SSL_DOMAIN:-localhost}"

# Extract IP from nip.io domain if SSL_IP not explicitly set
# e.g., 192.168.1.100.nip.io → 192.168.1.100
if [ -z "$SSL_IP" ] && echo "$DOMAIN" | grep -q "nip.io"; then
    SSL_IP=$(echo "$DOMAIN" | sed 's/\.nip\.io$//')
fi

# Check if certificates already exist and are recent (less than 30 days old)
if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
    # Check if cert is less than 30 days old
    if [ $(find "$CERT_DIR/cert.pem" -mtime -30 2>/dev/null | wc -l) -gt 0 ]; then
        echo "Certificates already exist and are recent, skipping generation"
        exit 0
    fi
fi

echo "Generating SSL certificates for: $DOMAIN"

# Install openssl if not present
apk add --no-cache openssl 2>/dev/null || apt-get update && apt-get install -y openssl 2>/dev/null || true

# Build SAN (Subject Alternative Names)
SAN="DNS:$DOMAIN,DNS:localhost,DNS:api,DNS:web,IP:127.0.0.1"
if [ -n "$SSL_IP" ]; then
    SAN="$SAN,IP:$SSL_IP"
    echo "Including LAN IP in SAN: $SSL_IP"
fi

# Generate private key
openssl genrsa -out "$CERT_DIR/key.pem" 2048

# Generate certificate with SAN
openssl req -new -x509 -key "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" -days 365 \
    -subj "/C=FR/ST=Dev/L=Dev/O=LIA/CN=$DOMAIN" \
    -addext "subjectAltName=$SAN"

# Set permissions (644 for both: dev-only certs, readable by non-root containers like Next.js)
chmod 644 "$CERT_DIR/cert.pem"
chmod 644 "$CERT_DIR/key.pem"

echo "Certificates generated successfully in $CERT_DIR"
ls -la "$CERT_DIR"
