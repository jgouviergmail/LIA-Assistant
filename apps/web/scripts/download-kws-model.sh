#!/bin/bash
# =============================================================================
# Download Sherpa-onnx KWS Model for Wake Word Detection
#
# Model: zipformer-gigaspeech-3.3M (English keyword spotting)
# Size: ~3MB compressed
# Source: https://github.com/k2-fsa/sherpa-onnx/releases
#
# Usage:
#   chmod +x scripts/download-kws-model.sh
#   ./scripts/download-kws-model.sh
#
# Reference: plan zippy-drifting-valley.md (section 2.5.1)
# =============================================================================

set -e

# Configuration
MODEL_NAME="sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
MODEL_DIR="public/models/sherpa-onnx-kws-zipformer-gigaspeech"
TARBALL_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/${MODEL_NAME}.tar.bz2"
TEMP_DIR=$(mktemp -d)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Sherpa-onnx KWS Model Download ===${NC}"
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

# Check if model already valid (encoder should be > 100KB)
ENCODER_FILE="${MODEL_DIR}/encoder-epoch-12-avg-2-chunk-16-left-64.onnx"
if [ -f "$ENCODER_FILE" ]; then
    FILE_SIZE=$(stat -f%z "$ENCODER_FILE" 2>/dev/null || stat -c%s "$ENCODER_FILE" 2>/dev/null)
    if [ "$FILE_SIZE" -gt 100000 ]; then
        echo -e "${GREEN}Model already downloaded and valid.${NC}"
        echo "Location: ${MODEL_DIR}"
        exit 0
    fi
fi

echo -e "${YELLOW}Downloading model tarball...${NC}"
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
    # Copy required files (actual names from archive)
    FILES=(
        "encoder-epoch-12-avg-2-chunk-16-left-64.onnx"
        "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"
        "joiner-epoch-12-avg-2-chunk-16-left-64.onnx"
        "tokens.txt"
        "bpe.model"
    )

    for file in "${FILES[@]}"; do
        if [ -f "${EXTRACTED_DIR}/${file}" ]; then
            cp "${EXTRACTED_DIR}/${file}" "${MODEL_DIR}/"
            echo -e "  ${GREEN}✓${NC} ${file}"
        else
            echo -e "  ${YELLOW}!${NC} ${file} (optional, not found)"
        fi
    done
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

# Verify file sizes
echo "File sizes:"
ls -lh "${MODEL_DIR}"/*.onnx 2>/dev/null | awk '{print "  " $5 " " $9}'
echo ""

echo "Wake word file: public/models/keywords.txt"
echo "Default wake word: 'ok' (universal)"
echo ""
echo -e "${YELLOW}To use a custom wake word:${NC}"
echo "  Edit public/models/keywords.txt"
echo "  One keyword per line (lowercase)"
echo ""
