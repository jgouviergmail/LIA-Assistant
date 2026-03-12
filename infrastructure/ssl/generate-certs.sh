#!/bin/sh
# Generate self-signed SSL certificates for development
# This script runs inside a container and generates certs for both web and api

CERT_DIR="/certs"
DOMAIN="localhost"

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

# Generate private key
openssl genrsa -out "$CERT_DIR/key.pem" 2048

# Generate certificate with SAN (Subject Alternative Names)
openssl req -new -x509 -key "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" -days 365 \
    -subj "/C=FR/ST=Dev/L=Dev/O=LIA/CN=$DOMAIN" \
    -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,DNS:api,DNS:web,IP:127.0.0.1"

# Set permissions
chmod 644 "$CERT_DIR/cert.pem"
chmod 600 "$CERT_DIR/key.pem"

echo "Certificates generated successfully in $CERT_DIR"
ls -la "$CERT_DIR"
