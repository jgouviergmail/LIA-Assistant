#!/bin/bash
# ==============================================================================
# Download Sherpa-onnx WASM Runtime (VAD + ASR + Whisper Tiny.en)
# ==============================================================================
#
# Downloads the pre-built sherpa-onnx WASM module for browser-based
# Voice Activity Detection + Automatic Speech Recognition.
#
# This tarball bundles everything needed for wake word detection:
#   - Sherpa-onnx WASM binary (SIMD-optimized)
#   - Silero VAD model (bundled in .data)
#   - Whisper Tiny.en model (bundled in .data)
#   - JavaScript glue code (VAD API, ASR API, Emscripten main)
#
# Files installed:
#   sherpa-onnx-vad.js                    (~20KB)  - VAD + CircularBuffer API
#   sherpa-onnx-asr.js                    (~15KB)  - OfflineRecognizer API
#   sherpa-onnx-wasm-main-vad-asr.js      (~150KB) - Emscripten main module
#   sherpa-onnx-wasm-main-vad-asr.wasm    (~5MB)   - WASM binary (SIMD)
#   sherpa-onnx-wasm-main-vad-asr.data    (~40MB)  - Bundled models (VAD + Whisper)
#
# Source: https://github.com/k2-fsa/sherpa-onnx/releases
# Docs:   https://k2-fsa.github.io/sherpa/onnx/wasm/index.html
#
# Usage:
#   chmod +x scripts/download-sherpa-wasm.sh
#   ./scripts/download-sherpa-wasm.sh
#
# Reference: ADR-054-Voice-Input-Architecture.md
# ==============================================================================

set -e

# Configuration
SHERPA_VERSION="1.12.32"
TARBALL_NAME="sherpa-onnx-wasm-simd-${SHERPA_VERSION}-vad-asr-en-whisper_tiny.tar.bz2"
RELEASE_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/v${SHERPA_VERSION}/${TARBALL_NAME}"
TARGET_DIR="${1:-apps/web/public/models/sherpa-wasm}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "Sherpa-onnx WASM Runtime (VAD + ASR)"
echo "=============================================="
echo ""
echo "Version: v${SHERPA_VERSION}"
echo "Variant: vad-asr-en-whisper_tiny (SIMD)"
echo "Target:  ${TARGET_DIR}"
echo ""

# Check dependencies
for cmd in curl tar; do
    if ! command -v "$cmd" &> /dev/null; then
        echo -e "${RED}Error: ${cmd} is required but not installed.${NC}"
        exit 1
    fi
done

# Check if already downloaded and valid
WASM_FILE="${TARGET_DIR}/sherpa-onnx-wasm-main-vad-asr.wasm"
if [ -f "$WASM_FILE" ]; then
    FILE_SIZE=$(stat -f%z "$WASM_FILE" 2>/dev/null || stat -c%s "$WASM_FILE" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -gt 1000000 ]; then
        echo -e "${GREEN}WASM runtime already downloaded and valid.${NC}"
        echo "Location: ${TARGET_DIR}"
        echo "Size: $(du -sh "$TARGET_DIR" 2>/dev/null | cut -f1)"
        exit 0
    else
        echo -e "${YELLOW}WASM file exists but seems corrupted, re-downloading...${NC}"
        rm -rf "$TARGET_DIR"
    fi
fi

# Create target directory
mkdir -p "$TARGET_DIR"

# Download tarball
TEMP_DIR=$(mktemp -d)
TARBALL_PATH="${TEMP_DIR}/${TARBALL_NAME}"

echo -e "${YELLOW}Downloading WASM tarball...${NC}"
echo "URL: ${RELEASE_URL}"
echo ""

if ! curl -L --progress-bar -o "$TARBALL_PATH" "$RELEASE_URL"; then
    echo -e "${RED}Error: Failed to download WASM tarball.${NC}"
    echo ""
    echo "The release may not exist for version v${SHERPA_VERSION}."
    echo "Check available releases at:"
    echo "  https://github.com/k2-fsa/sherpa-onnx/releases"
    echo ""
    echo "Look for: sherpa-onnx-wasm-simd-*-vad-asr-en-whisper_tiny.tar.bz2"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo ""
echo -e "${YELLOW}Extracting...${NC}"

# Extract tarball
if ! tar -xjf "$TARBALL_PATH" -C "$TEMP_DIR"; then
    echo -e "${RED}Error: Failed to extract tarball${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Find the extracted directory
EXTRACTED_DIR=$(find "$TEMP_DIR" -maxdepth 1 -type d -name "sherpa-onnx-*" | head -1)
if [ -z "$EXTRACTED_DIR" ]; then
    echo -e "${RED}Error: No sherpa-onnx directory found in archive${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Required files
REQUIRED_FILES=(
    "sherpa-onnx-vad.js"
    "sherpa-onnx-asr.js"
    "sherpa-onnx-wasm-main-vad-asr.js"
    "sherpa-onnx-wasm-main-vad-asr.wasm"
    "sherpa-onnx-wasm-main-vad-asr.data"
)

echo ""
MISSING_REQUIRED=()

for file in "${REQUIRED_FILES[@]}"; do
    SRC="${EXTRACTED_DIR}/${file}"
    if [ -f "$SRC" ]; then
        cp "$SRC" "${TARGET_DIR}/"
        SIZE=$(du -sh "$SRC" 2>/dev/null | cut -f1)
        echo -e "  ${GREEN}✓${NC} ${file} (${SIZE})"
    else
        echo -e "  ${RED}✗${NC} ${file} (MISSING)"
        MISSING_REQUIRED+=("$file")
    fi
done

# Copy optional demo file
for file in "app-vad-asr.js"; do
    SRC="${EXTRACTED_DIR}/${file}"
    if [ -f "$SRC" ]; then
        cp "$SRC" "${TARGET_DIR}/"
        echo -e "  ${GREEN}✓${NC} ${file} (optional)"
    fi
done

# Cleanup
rm -rf "$TEMP_DIR"

echo ""

# Verify
if [ ${#MISSING_REQUIRED[@]} -gt 0 ]; then
    echo -e "${RED}Error: ${#MISSING_REQUIRED[@]} required file(s) missing:${NC}"
    for f in "${MISSING_REQUIRED[@]}"; do
        echo -e "  - ${f}"
    done
    echo ""
    echo "The tarball structure may have changed. Inspect the archive contents."
    exit 1
fi

# Create keywords.txt if it doesn't exist
KEYWORDS_FILE="$(dirname "$TARGET_DIR")/keywords.txt"
if [ ! -f "$KEYWORDS_FILE" ]; then
    echo "Creating wake words file..."
    cat > "$KEYWORDS_FILE" << 'EOF'
ok
okay
guy
guys
ok guy
okay guy
ok guys
okay guys
EOF
    echo -e "  ${GREEN}✓${NC} keywords.txt created"
fi

echo -e "${GREEN}=============================================="
echo "SUCCESS: WASM runtime downloaded!"
echo "==============================================${NC}"
echo ""
echo "Files: ${TARGET_DIR}/"
echo "Total size: $(du -sh "$TARGET_DIR" 2>/dev/null | cut -f1)"
echo ""
echo "Note: The .data file bundles Silero VAD + Whisper Tiny.en models."
echo "No separate model download is needed for wake word detection."
echo ""
