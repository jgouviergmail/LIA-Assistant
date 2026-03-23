#!/bin/bash
# =============================================================================
# Setup Development Environment
#
# Downloads all required ML models and sets up the dev environment.
# Run this once after cloning the repository.
#
# Models downloaded:
#   - Backend: Whisper Small (multilingual STT, ~375MB)
#   - Frontend: Whisper Tiny.en (English-only wake word, ~103MB)
#   - Frontend: Sherpa-onnx WASM runtime (VAD + ASR, ~7MB)
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

echo -e "${YELLOW}[1/3] Backend STT Model (Whisper Small)${NC}"
echo -e "  ${GREEN}✓${NC} Downloaded automatically during Docker build"
echo -e "    (Multi-stage build in Dockerfile.dev downloads from HuggingFace)"

# -----------------------------------------------------------------------------
# 2. Frontend Wake Word Model (Whisper Tiny.en - English only)
# -----------------------------------------------------------------------------
WHISPER_MODEL_DIR="apps/web/public/models/whisper-tiny-en"
WHISPER_ENCODER="$WHISPER_MODEL_DIR/encoder.onnx"

echo -e "${YELLOW}[2/3] Frontend Wake Word Model (Whisper Tiny.en)${NC}"

if [ -f "$WHISPER_ENCODER" ]; then
    FILE_SIZE=$(stat -f%z "$WHISPER_ENCODER" 2>/dev/null || stat -c%s "$WHISPER_ENCODER" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -gt 10000000 ]; then
        echo -e "  ${GREEN}✓${NC} Already downloaded ($(du -sh "$WHISPER_MODEL_DIR" 2>/dev/null | cut -f1))"
    else
        echo -e "  ${YELLOW}!${NC} File exists but seems corrupted, re-downloading..."
        rm -rf "$WHISPER_MODEL_DIR"
    fi
fi

if [ ! -f "$WHISPER_ENCODER" ]; then
    echo -e "  Downloading Whisper Tiny.en model (~103MB)..."

    # Call the download script
    bash "$SCRIPT_DIR/download-whisper-wasm-model.sh"

    if [ -f "$WHISPER_ENCODER" ]; then
        echo -e "  ${GREEN}✓${NC} Downloaded to $WHISPER_MODEL_DIR"
    else
        echo -e "  ${RED}✗${NC} Download failed"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# 3. Sherpa-onnx WASM Runtime (VAD + ASR)
# -----------------------------------------------------------------------------
WASM_DIR="apps/web/public/models/sherpa-wasm"
WASM_FILE="$WASM_DIR/sherpa-onnx-wasm-main-vad-asr.wasm"

echo -e "${YELLOW}[3/3] Sherpa-onnx WASM Runtime (VAD + ASR)${NC}"

if [ -f "$WASM_FILE" ]; then
    FILE_SIZE=$(stat -f%z "$WASM_FILE" 2>/dev/null || stat -c%s "$WASM_FILE" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -gt 1000000 ]; then
        echo -e "  ${GREEN}✓${NC} Already downloaded ($(du -sh "$WASM_DIR" 2>/dev/null | cut -f1))"
    else
        echo -e "  ${YELLOW}!${NC} WASM file exists but seems corrupted, re-downloading..."
        rm -rf "$WASM_DIR"
    fi
fi

if [ ! -f "$WASM_FILE" ]; then
    echo -e "  Downloading Sherpa-onnx WASM runtime (~7MB)..."

    bash "$SCRIPT_DIR/download-sherpa-wasm.sh"

    if [ -f "$WASM_FILE" ]; then
        echo -e "  ${GREEN}✓${NC} Downloaded to $WASM_DIR"
    else
        echo -e "  ${RED}✗${NC} Download failed"
        echo -e "    Voice mode (wake word detection) will not work without WASM files."
        echo -e "    You can retry: ./scripts/download-sherpa-wasm.sh"
        # Don't exit - app works without voice mode
    fi
fi

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