#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/scripts/00_common.sh"

log_info "Stopping agent-watcher service..."
sudo systemctl stop agent-watcher.service

log_success "Service stopped."
