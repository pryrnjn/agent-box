#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/scripts/00_common.sh"

# Default: Start (idempotent)
ACTION="start"
TARGET="both"

# Parse args
for arg in "$@"; do
    case $arg in
        --restart|-r)
            ACTION="restart"
            ;;
        --restart-agent)
            ACTION="restart"
            TARGET="agent"
            ;;
        --restart-supervisor)
            ACTION="restart"
            TARGET="supervisor"
            ;;
        --help|-h)
            echo "Usage: ./start.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  (default)           Start services if not running"
            echo "  --restart, -r       Restart BOTH services"
            echo "  --restart-agent     Restart ONLY agent-watcher"
            echo "  --restart-supervisor Restart ONLY agent-supervisor"
            exit 0
            ;;
    esac
done

if [ "$TARGET" == "both" ] || [ "$TARGET" == "agent" ]; then
    if [ "$ACTION" == "restart" ]; then
        log_info "Restarting agent-watcher..."
        sudo systemctl restart agent-watcher.service
    else
        # Check if active
        if systemctl is-active --quiet agent-watcher.service; then
            log_info "agent-watcher is already running."
        else
            log_info "Starting agent-watcher..."
            sudo systemctl start agent-watcher.service
        fi
    fi
fi

if [ "$TARGET" == "both" ] || [ "$TARGET" == "supervisor" ]; then
    if [ "$ACTION" == "restart" ]; then
        log_info "Restarting agent-supervisor..."
        sudo systemctl restart agent-supervisor.service
    else
        if systemctl is-active --quiet agent-supervisor.service; then
            log_info "agent-supervisor is already running."
        else
            log_info "Starting agent-supervisor..."
            sudo systemctl start agent-supervisor.service
        fi
    fi
fi

log_info "Services are running. Tailing logs (Ctrl+C to exit)..."
if [ "$TARGET" == "agent" ]; then
    sudo journalctl -u agent-watcher -f
elif [ "$TARGET" == "supervisor" ]; then
    sudo journalctl -u agent-supervisor -f
else
    sudo journalctl -u agent-watcher -u agent-supervisor -f
fi
