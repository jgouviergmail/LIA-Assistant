#!/bin/bash
# ==============================================================================
# Download Whisper Small INT8 Model for Sherpa-onnx STT
# ==============================================================================
#
# Downloads the Whisper small model (INT8 quantized) from HuggingFace.
# Supports 99+ languages including French, English, German, Spanish, Italian, Chinese.
#
# Usage:
#   ./scripts/download-whisper-model.sh [target_dir]
#
# Default target: apps/api/models/whisper-small
#
# Model details:
#   - Source: https://huggingface.co/csukuangfj/sherpa-onnx-whisper-small
#   - Size: ~375 MB (INT8 quantized)
#   - Languages: 99+ (FR, EN, DE, ES, IT, ZH, and more)
#
# Reference: Voice System Implementation (plan zippy-drifting-valley.md)
# Created: 2026-02-01
# ==============================================================================

set -e

# Configuration
HF_BASE_URL="https://huggingface.co/csukuangfj/sherpa-onnx-whisper-small/resolve/main"
TARGET_DIR="${1:-apps/api/models/whisper-small}"

# Files to download
FILES=(
    "small-encoder.int8.onnx"
    "small-decoder.int8.onnx"
    "small-tokens.txt"
)

# File sizes (approximate, for verification)
declare -A FILE_SIZES
FILE_SIZES["small-encoder.int8.onnx"]=117440512   # ~112 MB
FILE_SIZES["small-decoder.int8.onnx"]=274726912   # ~262 MB
FILE_SIZES["small-tokens.txt"]=836608             # ~817 KB

echo "=============================================="
echo "Whisper Small INT8 Model Downloader"
echo "=============================================="
echo ""
echo "Target directory: $TARGET_DIR"
echo "Source: HuggingFace (csukuangfj/sherpa-onnx-whisper-small)"
echo ""

# Create target directory
mkdir -p "$TARGET_DIR"

# Download each file
for file in "${FILES[@]}"; do
    echo "Downloading: $file"
    url="${HF_BASE_URL}/${file}"
    target="${TARGET_DIR}/${file}"

    if [ -f "$target" ]; then
        echo "  File exists, checking size..."
        actual_size=$(stat -f%z "$target" 2>/dev/null || stat -c%s "$target" 2>/dev/null)
        expected_size=${FILE_SIZES[$file]}

        # Allow 5% tolerance for size check
        min_size=$((expected_size * 95 / 100))
        max_size=$((expected_size * 105 / 100))

        if [ "$actual_size" -ge "$min_size" ] && [ "$actual_size" -le "$max_size" ]; then
            echo "  File already downloaded and valid, skipping."
            continue
        else
            echo "  File size mismatch, re-downloading..."
        fi
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

# Rename files to standard names expected by sherpa-onnx
echo ""
echo "Renaming files to standard names..."
mv -f "${TARGET_DIR}/small-encoder.int8.onnx" "${TARGET_DIR}/encoder.onnx" 2>/dev/null || true
mv -f "${TARGET_DIR}/small-decoder.int8.onnx" "${TARGET_DIR}/decoder.onnx" 2>/dev/null || true
mv -f "${TARGET_DIR}/small-tokens.txt" "${TARGET_DIR}/tokens.txt" 2>/dev/null || true

# Verify downloads
echo ""
echo "Verifying downloads..."
required_files=("encoder.onnx" "decoder.onnx" "tokens.txt")
missing=0

for file in "${required_files[@]}"; do
    if [ -f "${TARGET_DIR}/${file}" ]; then
        size=$(stat -f%z "${TARGET_DIR}/${file}" 2>/dev/null || stat -c%s "${TARGET_DIR}/${file}" 2>/dev/null)
        size_mb=$((size / 1024 / 1024))
        echo "  OK: $file (${size_mb} MB)"
    else
        echo "  MISSING: $file"
        missing=$((missing + 1))
    fi
done

echo ""
if [ $missing -eq 0 ]; then
    echo "=============================================="
    echo "SUCCESS: Whisper model downloaded!"
    echo "=============================================="
    echo ""
    echo "Model path: $TARGET_DIR"
    echo "Languages supported: 99+ (FR, EN, DE, ES, IT, ZH, ...)"
    echo ""
    echo "Update your .env:"
    echo "  VOICE_STT_MODEL_PATH=$TARGET_DIR"
    echo ""
else
    echo "=============================================="
    echo "ERROR: $missing file(s) missing!"
    echo "=============================================="
    exit 1
fi
