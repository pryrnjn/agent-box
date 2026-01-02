#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"
source "$SCRIPT_DIR/../../config.template.env" 2>/dev/null || true

check_root

log_info "Preparing installation directory at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Copy python script
ROOT_DIR=$(dirname "$SCRIPT_DIR")
log_info "Copying agent_watcher.py from $ROOT_DIR..."
cp "$ROOT_DIR/agent_watcher.py" "$INSTALL_DIR/"

# Setup Config if missing
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -f "$ROOT_DIR/config.template.env" ]; then
        cp "$ROOT_DIR/config.template.env" "$INSTALL_DIR/.env"
        log_info "Created default config at $INSTALL_DIR/.env from template."
    else
        log_info "Creating empty .env file..."
        touch "$INSTALL_DIR/.env"
    fi
else
    log_info "Config file already exists at $INSTALL_DIR/.env. Skipping overwrite."
fi

log_info "Setting permissions for user $USER_NAME..."
chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"

# Python Venv
log_info "Setting up Python virtual environment (venv)..."
sudo -u "$USER_NAME" bash << EOF
cd "$INSTALL_DIR"
if [ ! -d "venv" ]; then
    echo "Creating venv..."
    python3 -m venv venv
else
    echo "venv exists."
fi
source venv/bin/activate
echo "Installing python dependencies (requests, python-dotenv)..."
pip install --upgrade pip
pip install requests python-dotenv
EOF
log_success "Python environment ready."

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

[Install]
WantedBy=multi-user.target
EOF

log_info "Reloading systemd daemon..."
systemctl daemon-reload
log_info "Enabling agent-watcher service..."
systemctl enable agent-watcher.service

log_success "Service 'agent-watcher' installed and enabled."
