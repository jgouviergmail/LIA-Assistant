#!/bin/bash

##
# Generate secure secrets for LIA production deployment
# Generates SECRET_KEY and FERNET_KEY with proper formats
##

set -e

echo "========================================"
echo "LIA - Secret Key Generator"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Generate SECRET_KEY (64 characters, URL-safe base64)
echo -e "${BLUE}Generating SECRET_KEY...${NC}"
SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n')
echo -e "${GREEN}SECRET_KEY generated (64 chars)${NC}"
echo ""

# Generate FERNET_KEY (32 bytes, URL-safe base64)
echo -e "${BLUE}Generating FERNET_KEY...${NC}"
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo -e "${GREEN}FERNET_KEY generated (44 chars base64)${NC}"
echo ""

# Display results
echo "========================================"
echo -e "${YELLOW}Generated Secrets (KEEP SECURE!)${NC}"
echo "========================================"
echo ""
echo "Add these to your .env.prod file:"
echo ""
echo "SECRET_KEY=${SECRET_KEY}"
echo "FERNET_KEY=${FERNET_KEY}"
echo ""

# Option to write to .env.prod
read -p "Do you want to write these secrets to .env.prod? (y/N) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ENV_FILE=".env.prod"

    if [ -f "$ENV_FILE" ]; then
        echo -e "${YELLOW}Warning: $ENV_FILE already exists${NC}"
        read -p "Do you want to update the existing file? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Cancelled. Secrets were not written to file."
            exit 0
        fi

        # Backup existing file
        cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        echo -e "${GREEN}Backup created: ${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)${NC}"
    fi

    # Update or create .env.prod
    if [ -f "$ENV_FILE" ]; then
        # Update existing values
        if grep -q "^SECRET_KEY=" "$ENV_FILE"; then
            sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" "$ENV_FILE"
            echo "Updated SECRET_KEY in $ENV_FILE"
        else
            echo "SECRET_KEY=${SECRET_KEY}" >> "$ENV_FILE"
            echo "Added SECRET_KEY to $ENV_FILE"
        fi

        if grep -q "^FERNET_KEY=" "$ENV_FILE"; then
            sed -i "s|^FERNET_KEY=.*|FERNET_KEY=${FERNET_KEY}|" "$ENV_FILE"
            echo "Updated FERNET_KEY in $ENV_FILE"
        else
            echo "FERNET_KEY=${FERNET_KEY}" >> "$ENV_FILE"
            echo "Added FERNET_KEY to $ENV_FILE"
        fi
    else
        # Create new file from example
        if [ -f ".env.prod.example" ]; then
            cp ".env.prod.example" "$ENV_FILE"
            sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" "$ENV_FILE"
            sed -i "s|^FERNET_KEY=.*|FERNET_KEY=${FERNET_KEY}|" "$ENV_FILE"
            echo -e "${GREEN}Created $ENV_FILE from template${NC}"
        else
            echo "SECRET_KEY=${SECRET_KEY}" > "$ENV_FILE"
            echo "FERNET_KEY=${FERNET_KEY}" >> "$ENV_FILE"
            echo -e "${GREEN}Created new $ENV_FILE${NC}"
        fi
    fi

    echo ""
    echo -e "${GREEN}✓ Secrets successfully written to $ENV_FILE${NC}"
    echo -e "${YELLOW}⚠ Remember to update other required variables in $ENV_FILE${NC}"
else
    echo "Secrets were not written to file. Copy them manually."
fi

echo ""
echo "========================================"
echo -e "${YELLOW}Security Reminders:${NC}"
echo "========================================"
echo "1. NEVER commit .env.prod to version control"
echo "2. Store these secrets securely (password manager, vault)"
echo "3. Rotate secrets periodically"
echo "4. Use different secrets for each environment"
echo ""
