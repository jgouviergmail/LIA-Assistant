#!/bin/bash
# =============================================================================
# Download Sherpa-onnx SenseVoice STT Model
#
# Model: SenseVoiceSmall (multi-language: FR/EN/DE/ES/IT/ZH/JA/KO)
# Size: ~100MB compressed
# Source: https://github.com/k2-fsa/sherpa-onnx/releases
#
# Usage:
#   chmod +x scripts/download-stt-model.sh
#   ./scripts/download-stt-model.sh
#
# Reference: plan zippy-drifting-valley.md (section 2.4)
# =============================================================================

set -e

# Configuration
MODEL_NAME="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
MODEL_DIR="models/sensevoice"
TARBALL_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${MODEL_NAME}.tar.bz2"
TEMP_DIR=$(mktemp -d)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Sherpa-onnx SenseVoice STT Model Download ===${NC}"
echo ""

# Check dependencies
for cmd in curl tar; do
    if ! command -v "$cmd" &> /dev/null; then
        echo -e "${RED}Error: ${cmd} is required but not installed.${NC}"
        exit 1
    fi
done

# Create model directory
mkdir -p "$MODEL_DIR"

# Check if model already valid (model.onnx should exist and be > 50MB)
MODEL_FILE="${MODEL_DIR}/model.onnx"
if [ -f "$MODEL_FILE" ]; then
    FILE_SIZE=$(stat -f%z "$MODEL_FILE" 2>/dev/null || stat -c%s "$MODEL_FILE" 2>/dev/null)
    if [ "$FILE_SIZE" -gt 50000000 ]; then
        echo -e "${GREEN}Model already downloaded and valid.${NC}"
        echo "Location: ${MODEL_DIR}"
        exit 0
    fi
fi

echo -e "${YELLOW}Downloading model tarball (~100MB)...${NC}"
echo "URL: ${TARBALL_URL}"
echo ""

# Download tarball
TARBALL_PATH="${TEMP_DIR}/${MODEL_NAME}.tar.bz2"
if ! curl -L -# -o "$TARBALL_PATH" "$TARBALL_URL"; then
    echo -e "${RED}Error: Failed to download model tarball${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo ""
echo -e "${YELLOW}Extracting model files...${NC}"

# Extract tarball
if ! tar -xjf "$TARBALL_PATH" -C "$TEMP_DIR"; then
    echo -e "${RED}Error: Failed to extract tarball${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Move model files to destination
EXTRACTED_DIR="${TEMP_DIR}/${MODEL_NAME}"
if [ -d "$EXTRACTED_DIR" ]; then
    # Copy all files from extracted directory
    cp -r "${EXTRACTED_DIR}"/* "${MODEL_DIR}/"
    echo -e "  ${GREEN}✓${NC} Model files extracted"
else
    echo -e "${RED}Error: Expected directory ${MODEL_NAME} not found in archive${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo -e "${GREEN}=== Download Complete ===${NC}"
echo ""
echo "Model files installed in: ${MODEL_DIR}"
echo ""

# Verify key files
echo "Key files:"
for f in model.onnx tokens.txt; do
    if [ -f "${MODEL_DIR}/${f}" ]; then
        SIZE=$(ls -lh "${MODEL_DIR}/${f}" | awk '{print $5}')
        echo -e "  ${GREEN}✓${NC} ${f} (${SIZE})"
    else
        echo -e "  ${RED}✗${NC} ${f} (missing!)"
    fi
done
echo ""
