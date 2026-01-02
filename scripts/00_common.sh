#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Fix Locale
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# Common Variables
USER_NAME=${SUDO_USER:-$USER}
if [ -z "$USER_NAME" ]; then
    log_error "Could not detect user. Please run with sudo."
    exit 1
fi

USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)
# Allow INSTALL_DIR to be overridden by env, otherwise default to ~/agent-box
INSTALL_DIR="${INSTALL_DIR:-$USER_HOME/agent-box}"

# Helper Functions
log_info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')][INFO] $1${NC}"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')][SUCCESS] $1${NC}"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')][ERROR] $1${NC}"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root (use sudo)"
        exit 1
    fi
}
