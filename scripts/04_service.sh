#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"
source "$SCRIPT_DIR/../config.template.env" 2>/dev/null || true

check_root

if [ ! -d "$INSTALL_DIR" ]; then
    log_error "Install directory $INSTALL_DIR does not exist. Please run 03_deploy.sh first."
    exit 1
fi

# Ensure Gemini directories exist for ReadWritePaths to work
# Systemd fails with 226/NAMESPACE if a ReadWritePath path doesn't exist
log_info "Ensuring Gemini config/cache directories exist..."
sudo -u "$USER_NAME" mkdir -p "/home/$USER_NAME/.gemini" "/home/$USER_NAME/.config/gemini"

# Systemd
SERVICE_FILE="/etc/systemd/system/agent-watcher.service"
log_info "Creating systemd unit file at $SERVICE_FILE..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Agent Box Watcher Service
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/agent_watcher.py
Restart=always
RestartSec=60

# --- Security Sandboxing ---
# Prevent writing to system directories (only allow writing to install dir)
ProtectSystem=strict
# User home is read-only, BUT we explicitly whitelist correct paths
ProtectHome=read-only
# Whitelist Install Dir and Gemini Config Dir
# Prefix with '-' to ignore if path doesn't exist (though we created them)
ReadWritePaths=$INSTALL_DIR -/home/$USER_NAME/.gemini -/home/$USER_NAME/.config/gemini

# Create a private /tmp for this service
PrivateTmp=true
# Prevent escalating privileges
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

log_info "Reloading systemd daemon..."
systemctl daemon-reload
log_info "Enabling agent-watcher service..."
systemctl enable agent-watcher.service

log_success "Service 'agent-watcher' configured and enabled."
