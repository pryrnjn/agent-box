#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"
source "$SCRIPT_DIR/../../config.template.env" 2>/dev/null || true

check_root

log_info "Setting up Service..."

mkdir -p "$INSTALL_DIR"

# Copy python script
# We need to find where the original agent_watcher.py is.
# Assuming relative path from this script: ../../agent_watcher.py
ROOT_DIR=$(dirname "$SCRIPT_DIR")
cp "$ROOT_DIR/agent_watcher.py" "$INSTALL_DIR/"

# Setup Config if missing
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -f "$ROOT_DIR/config.template.env" ]; then
        cp "$ROOT_DIR/config.template.env" "$INSTALL_DIR/.env"
        log_info "Created default config at $INSTALL_DIR/.env"
    else
        touch "$INSTALL_DIR/.env"
    fi
fi

chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"

# Python Venv
log_info "Setting up Python venv..."
sudo -u "$USER_NAME" bash << EOF
cd "$INSTALL_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install requests python-dotenv
EOF

# Systemd
SERVICE_FILE="/etc/systemd/system/agent-watcher.service"
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

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable agent-watcher.service

log_success "Service 'agent-watcher' installed and enabled."
