#!/bin/bash
# =============================================================================
# Setup Development Environment
#
# Downloads all required ML models and sets up the dev environment.
# Run this once after cloning the repository.
#
# Models:
#   - Backend: Whisper Small (multilingual STT, ~375MB), baked by Dockerfile.dev
#   - Frontend: the wake-word models are committed (apps/web/public/models/wake,
#     ADR-329); `pnpm run dev` / `pnpm run build` copy the ONNX Runtime binary
#
# Usage:
#   chmod +x scripts/setup-dev.sh
#   ./scripts/setup-dev.sh
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== LIA Dev Setup ===${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

# -----------------------------------------------------------------------------
# 1. Backend STT Model (Whisper Small - Multilingual)
# -----------------------------------------------------------------------------
# Note: Backend model is baked into Docker image via Dockerfile.dev multi-stage build
# This step is only needed for local development without Docker

echo -e "${YELLOW}[1/2] Backend STT Model (Whisper Small)${NC}"
echo -e "  ${GREEN}✓${NC} Downloaded automatically during Docker build"
echo -e "    (Multi-stage build in Dockerfile.dev downloads from HuggingFace)"

# -----------------------------------------------------------------------------
# 2. Frontend wake word (ADR-329): nothing to download
# -----------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[2/2] Frontend wake word${NC}"
echo -e "  ${GREEN}✓${NC} Models committed under apps/web/public/models/wake/"
echo -e "    (the ONNX Runtime binary is copied by pnpm run dev / build)"

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and configure"
echo "  2. Run: make dev"
echo "     Or:  docker compose -f docker-compose.dev.yml up -d"
echo ""