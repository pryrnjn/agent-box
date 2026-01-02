#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"

check_root

log_info "Updating system packages (apt-get update)..."
apt-get update -qq
log_info "Upgrading system packages (apt-get upgrade)..."
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq

log_info "Installing core apt dependencies (git, python, etc)..."
apt-get install -y -qq \
    git curl wget jq build-essential \
    python3 python3-pip python3-venv \
    unzip gnupg
log_success "Core apt dependencies installed."

# Install GitHub CLI
if ! command -v gh &> /dev/null; then
    log_info "GitHub CLI not found. Installing..."
    mkdir -p -m 755 /etc/apt/keyrings
    log_info "Fetching GitHub CLI keyring..."
    wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
    chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    log_info "Updating apt sources for GitHub CLI..."
    apt-get update -qq
    apt-get install -y -qq gh
    log_success "GitHub CLI installed."
else
    log_success "GitHub CLI is already installed."
fi

# Install Node.js (LTS)
if ! command -v node &> /dev/null; then
    log_info "Node.js not found. fetching setup script..."
    curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
    log_info "Installing nodejs package..."
    apt-get install -y -qq nodejs
    log_success "Node.js installed."
else
    log_success "Node.js is already installed."
fi

log_success "Base dependencies installed."
