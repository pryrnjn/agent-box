#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/scripts/00_common.sh"

log_info "Starting agent-watcher service..."
sudo systemctl start agent-watcher.service

log_info "Service started. Tailing logs (Ctrl+C to exit)..."
sudo journalctl -u agent-watcher -f
