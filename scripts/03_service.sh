#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"
source "$SCRIPT_DIR/../config.template.env" 2>/dev/null || true

check_root

log_info "Preparing installation directory at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# --- Installation Method: Git Clone (preferred) or Copy ---
ROOT_DIR=$(dirname "$SCRIPT_DIR")
REMOTE_URL=$(git -C "$ROOT_DIR" config --get remote.origin.url || true)

if [ -n "$REMOTE_URL" ]; then
    log_info "Detected git repository source: $REMOTE_URL"
    log_info "Setting up $INSTALL_DIR as a git clone..."
    
    if [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Updating existing repository at $INSTALL_DIR..."
        # We need to run git as the owner user, not root, to avoid permission issues?
        # But we are root now. We can sudo -u.
        sudo -u "$USER_NAME" git -C "$INSTALL_DIR" fetch origin
        sudo -u "$USER_NAME" git -C "$INSTALL_DIR" reset --hard origin/main
    else
        # Remove dir if it exists but isn't git (and not empty?)
        # Safe approach: just clone into empty dir.
        # If dir exists and not empty, git clone fails.
        if [ -d "$INSTALL_DIR" ] && [ "$(ls -A $INSTALL_DIR)" ]; then
            log_warning "$INSTALL_DIR exists and is not empty. Backing up..."
            mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%s)"
            mkdir -p "$INSTALL_DIR"
        fi
        
        # Ensure parent dir exists
        mkdir -p "$(dirname "$INSTALL_DIR")"
        chown "$USER_NAME:$USER_NAME" "$(dirname "$INSTALL_DIR")"
        
        log_info "Cloning..."
        sudo -u "$USER_NAME" git clone "$REMOTE_URL" "$INSTALL_DIR"
    fi
else
    log_warning "Not running from a git repository. Fallback to file copy."
    log_warning "AUTO-UPDATE WILL BE DISABLED."
    mkdir -p "$INSTALL_DIR"
    cp "$ROOT_DIR/agent_watcher.py" "$INSTALL_DIR/"
    cp -r "$ROOT_DIR/scripts" "$INSTALL_DIR/" # Copy scripts too just in case
fi

# Determine Source Config
SOURCE_CONFIG=""
if [ -f "$ROOT_DIR/.env" ]; then
    log_info "Found local .env in source directory."
    SOURCE_CONFIG="$ROOT_DIR/.env"
elif [ -f "$ROOT_DIR/config.template.env" ]; then
    log_info "Found config.template.env in source directory."
    SOURCE_CONFIG="$ROOT_DIR/config.template.env"
fi

# Setup Config
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -n "$SOURCE_CONFIG" ]; then
        cp "$SOURCE_CONFIG" "$INSTALL_DIR/.env"
        log_info "Copied config to $INSTALL_DIR/.env"
    else
        log_info "Creating empty .env file..."
        touch "$INSTALL_DIR/.env"
    fi
else
    # Config exists. Check if it's unconfigured.
    if ! grep -q "GITHUB_REPO=\"owner/repo\"" "$INSTALL_DIR/.env" && grep -q "GITHUB_REPO=" "$INSTALL_DIR/.env"; then
        log_info "Config file exists at $INSTALL_DIR/.env and appears configured."
    else
        # It seems unconfigured or default. If we have a better source, overwrite?
        # Actually, if the user provided a specific .env in the bundle, they likely want to use it.
        if [ -f "$ROOT_DIR/.env" ]; then
            log_info "Overwriting existing config with local .env found in bundle..."
            cp "$ROOT_DIR/.env" "$INSTALL_DIR/.env"
        else
            log_info "Config exists. Keeping it."
        fi
    fi
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

log_success "Service 'agent-watcher' installed and enabled."
