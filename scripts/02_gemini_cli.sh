#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"

check_root

log_info "Checking for Gemini CLI..."

# Check if npm is installed (should be from 01_base_deps.sh)
if ! command -v npm &> /dev/null; then
    log_error "npm is not installed. Please run 01_base_deps.sh first."
    exit 1
fi

# Install Gemini CLI via npm
if command -v gemini &> /dev/null; then
    log_info "Gemini CLI is already installed. Skipping installation."
else
    log_info "Installing @google/gemini-cli globally..."
    npm install -g @google/gemini-cli
fi

# Verify installation
if command -v gemini &> /dev/null; then
    VERSION=$(gemini --version || echo "unknown")
    log_success "Gemini CLI installed successfully (version: $VERSION)."
else
    log_error "Gemini CLI installation failed."
    exit 1
fi
