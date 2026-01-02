#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"

check_root

log_info "Checking Antigravity CLI..."

if command -v antigravity &> /dev/null; then
    log_success "Antigravity CLI is already installed."
    exit 0
fi

log_info "Downloading Antigravity CLI..."

# Target destination
BIN_DIR="/usr/local/bin"
TEMP_DIR=$(mktemp -d)

# Download URL (based on user info)
# Assuming it is a direct binary or a tarball. 
# Since we don't know the exact format, I will implement a robust guess:
# 1. Try to fetch the 'linux' binary.
# NOTE: The user provided https://antigravity.google/download/linux
# This might effectively be a redirect to a binary or a page.
# For this script, I will try to fetch it as a file.

DOWNLOAD_URL="https://antigravity.google/download/linux"
TARGET_FILE="$TEMP_DIR/antigravity"

wget -q --show-progress -O "$TARGET_FILE" "$DOWNLOAD_URL"

# Check if it is a binary or an archive
FILE_TYPE=$(file "$TARGET_FILE")

if [[ "$FILE_TYPE" == *"executable"* || "$FILE_TYPE" == *"ELF"* ]]; then
    # It's a binary
    mv "$TARGET_FILE" "$BIN_DIR/antigravity"
    chmod +x "$BIN_DIR/antigravity"
    log_success "Installed Antigravity binary to $BIN_DIR/antigravity"

elif [[ "$FILE_TYPE" == *"Zip archive"* ]]; then
    # It's a zip
    unzip -q "$TARGET_FILE" -d "$TEMP_DIR"
    # Find the binary inside
    BINARY=$(find "$TEMP_DIR" -type f -name "antigravity" | head -n 1)
    if [ -n "$BINARY" ]; then
        mv "$BINARY" "$BIN_DIR/antigravity"
        chmod +x "$BIN_DIR/antigravity"
        log_success "Unzipped and installed Antigravity binary."
    else
        log_error "Could not find 'antigravity' binary in the downloaded zip."
        exit 1
    fi

elif [[ "$FILE_TYPE" == *"gzip compressed data"* ]]; then
     # It's a tarball
    tar -xzf "$TARGET_FILE" -C "$TEMP_DIR"
    BINARY=$(find "$TEMP_DIR" -type f -name "antigravity" | head -n 1)
    if [ -n "$BINARY" ]; then
        mv "$BINARY" "$BIN_DIR/antigravity"
        chmod +x "$BIN_DIR/antigravity"
        log_success "Extracted and installed Antigravity binary."
    else
        log_error "Could not find 'antigravity' binary in the downloaded tarball."
        exit 1
    fi
else
    # Fallback: Just assume it's the binary if we can't detect
    log_info "Unknown file type: $FILE_TYPE. Assuming executable binary."
    mv "$TARGET_FILE" "$BIN_DIR/antigravity"
    chmod +x "$BIN_DIR/antigravity"
fi

rm -rf "$TEMP_DIR"

log_success "Antigravity setup complete."
log_info "You may need to authenticate later using: antigravity login"
