#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/scripts/00_common.sh"

log_info "Restarting agent-supervisor service..."
sudo systemctl restart agent-supervisor.service

log_info "Service restarted. Tailing logs (Ctrl+C to exit)..."
sudo journalctl -u agent-supervisor -f
