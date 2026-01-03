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

log_info "Setting up Antigravity APT repository..."

# 1. Add GPG Key
log_info "Adding GPG key..."
mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://us-central1-apt.pkg.dev/doc/repo-signing-key.gpg | \
  gpg --dearmor --yes -o /etc/apt/keyrings/antigravity-repo-key.gpg
chmod go+r /etc/apt/keyrings/antigravity-repo-key.gpg

# 2. Add Sources List
log_info "Adding source list..."
echo "deb [signed-by=/etc/apt/keyrings/antigravity-repo-key.gpg] https://us-central1-apt.pkg.dev/projects/antigravity-auto-updater-dev/ antigravity-debian main" | \
  tee /etc/apt/sources.list.d/antigravity.list > /dev/null

# 3. Update Cache
log_info "Updating apt cache..."
apt-get update -qq

# 4. Install Package
log_info "Installing antigravity package..."
apt-get install -y -qq antigravity

if command -v antigravity &> /dev/null; then
    log_success "Antigravity setup complete."
    log_info "Version: $(antigravity --version || echo 'Unknown')"
    log_info "Usage: Please run 'antigravity login' manually to authenticate."
else
    log_error "Installation failed: 'antigravity' command not found."
    exit 1
fi
