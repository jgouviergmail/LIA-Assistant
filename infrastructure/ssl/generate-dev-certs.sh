#!/bin/bash
# Generate self-signed SSL certificates for development
# These certs are for local development only - DO NOT use in production

CERT_DIR="$(dirname "$0")"
DOMAIN="${1:-localhost}"

echo "Generating SSL certificates for: $DOMAIN"

# Generate private key
openssl genrsa -out "$CERT_DIR/dev.key" 2048

# Generate certificate signing request
openssl req -new -key "$CERT_DIR/dev.key" -out "$CERT_DIR/dev.csr" \
    -subj "/C=FR/ST=Local/L=Local/O=Development/CN=$DOMAIN"

# Generate self-signed certificate (valid for 365 days)
openssl x509 -req -days 365 -in "$CERT_DIR/dev.csr" -signkey "$CERT_DIR/dev.key" \
    -out "$CERT_DIR/dev.crt" \
    -extfile <(printf "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:127.0.0.1")

# Clean up CSR
rm -f "$CERT_DIR/dev.csr"

echo "Certificates generated:"
echo "  - $CERT_DIR/dev.key (private key)"
echo "  - $CERT_DIR/dev.crt (certificate)"
echo ""
echo "Add to your browser's trusted certificates to avoid warnings."
