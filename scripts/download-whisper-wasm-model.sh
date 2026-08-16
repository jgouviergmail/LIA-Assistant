#!/bin/bash
# ==============================================================================
# Download Whisper Tiny English Model for Browser WASM (Wake Word)
# ==============================================================================
#
# Downloads the Whisper tiny.en model for browser-based wake word detection.
# This is an ENGLISH-ONLY model - it can only transcribe English.
#
# Usage:
#   ./scripts/download-whisper-wasm-model.sh [target_dir]
#
# Default target: apps/web/public/models/whisper-tiny-en
#
# Model details:
#   - Source: https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en
#   - Size: ~75 MB (much smaller than multilingual)
#   - Language: English ONLY (native, not just language parameter)
#
# Why English-only for wake word:
#   - Wake words are in English ("OK", "okay", "hey")
#   - Multilingual models ignore language parameter, transcribing in detected language
#   - English-only model guarantees English transcription
#   - Smaller size = faster load time in browser
#
# Note: Main STT uses backend Python Whisper (multilingual) for user speech.
#
# Reference: Voice System Implementation (plan zippy-drifting-valley.md)
# Created: 2026-02-01
# Updated: 2026-02-01 - Switch to whisper-tiny.en for English-only wake word
# ==============================================================================

set -e

# Configuration
HF_BASE_URL="https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en/resolve/main"
TARGET_DIR="${1:-apps/web/public/models/whisper-tiny-en}"

# Files to download
FILES=(
    "tiny.en-encoder.int8.onnx"
    "tiny.en-decoder.int8.onnx"
    "tiny.en-tokens.txt"
)

echo "=============================================="
echo "Whisper Tiny.en Model for Browser WASM"
echo "(English-only for wake word detection)"
echo "=============================================="
echo ""
echo "Target directory: $TARGET_DIR"
echo "Source: HuggingFace (csukuangfj/sherpa-onnx-whisper-tiny.en)"
echo ""

# Create target directory
mkdir -p "$TARGET_DIR"

# Download each file
for file in "${FILES[@]}"; do
    echo "Downloading: $file"
    url="${HF_BASE_URL}/${file}"
    target="${TARGET_DIR}/${file}"

    if [ -f "$target" ]; then
        echo "  File exists, skipping."
        continue
    fi

    # Download with wget or curl
    if command -v wget &> /dev/null; then
        wget -q --show-progress -O "$target" "$url"
    elif command -v curl &> /dev/null; then
        curl -L --progress-bar -o "$target" "$url"
    else
        echo "ERROR: Neither wget nor curl found. Please install one."
        exit 1
    fi

    echo "  Downloaded: $file"
done

# Rename files to standard names expected by sherpa-onnx WASM
echo ""
echo "Renaming files to standard names..."
mv -f "${TARGET_DIR}/tiny.en-encoder.int8.onnx" "${TARGET_DIR}/encoder.onnx" 2>/dev/null || true
mv -f "${TARGET_DIR}/tiny.en-decoder.int8.onnx" "${TARGET_DIR}/decoder.onnx" 2>/dev/null || true
mv -f "${TARGET_DIR}/tiny.en-tokens.txt" "${TARGET_DIR}/tokens.txt" 2>/dev/null || true

# Create wake words file (English only since using whisper-tiny.en)
# Primary: "OK Guy" / "OK Guys" - the user-facing wake words
# Fallback: single words for more reliable detection
echo ""
echo "Creating wake words file..."
cat > "${TARGET_DIR}/../keywords.txt" << 'EOF'
ok
okay
guy
guys
ok guy
okay guy
ok guys
okay guys
EOF

echo ""
echo "=============================================="
echo "SUCCESS: Whisper Tiny.en model downloaded!"
echo "=============================================="
echo ""
echo "Model: whisper-tiny.en (English-only, ~75 MB)"
echo "Model path: $TARGET_DIR"
echo "Wake words file: ${TARGET_DIR}/../keywords.txt"
echo ""
echo "The browser will load these files dynamically at runtime."
echo "Main STT remains multilingual (Python backend)."
echo ""
