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
# Resolve absolute paths for comparison
ABS_ROOT=$(readlink -f "$ROOT_DIR")
ABS_INSTALL=$(readlink -f "$INSTALL_DIR")

if [ "$ABS_ROOT" == "$ABS_INSTALL" ]; then
    log_info "Installing In-Place (Source matches Install Directory)."
    log_info "Skipping git clone/reset to preserve local changes."
    # We are already here, so code is present.
    # Just ensure requirements are present if needed.
    if [ ! -f "$INSTALL_DIR/requirements.txt" ] && [ -f "$ROOT_DIR/requirements.txt" ]; then
        cp "$ROOT_DIR/requirements.txt" "$INSTALL_DIR/"
    fi
else
    REMOTE_URL=$(git -C "$ROOT_DIR" config --get remote.origin.url || true)

    if [ -n "$REMOTE_URL" ]; then
        log_info "Detected git repository source: $REMOTE_URL"
        log_info "Setting up $INSTALL_DIR as a git clone..."
        
        if [ -d "$INSTALL_DIR/.git" ]; then
            log_info "Updating existing repository at $INSTALL_DIR..."
            sudo -u "$USER_NAME" git -C "$INSTALL_DIR" fetch origin
            sudo -u "$USER_NAME" git -C "$INSTALL_DIR" reset --hard origin/main
        else
            if [ -d "$INSTALL_DIR" ] && [ "$(ls -A $INSTALL_DIR)" ]; then
                log_warning "$INSTALL_DIR exists and is not empty. Backing up..."
                mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%s)"
                mkdir -p "$INSTALL_DIR"
            fi
            
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
        cp "$ROOT_DIR/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || true
        cp -r "$ROOT_DIR/watcher" "$INSTALL_DIR/"
        cp -r "$ROOT_DIR/scripts" "$INSTALL_DIR/"
    fi
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
        if [ -f "$ROOT_DIR/.env" ]; then
            # Skip copy if source and destination are the same file (in-place install)
            ABS_SRC=$(readlink -f "$ROOT_DIR/.env")
            ABS_DST=$(readlink -f "$INSTALL_DIR/.env")
            if [ "$ABS_SRC" != "$ABS_DST" ]; then
                log_info "Overwriting existing config with local .env found in bundle..."
                cp "$ROOT_DIR/.env" "$INSTALL_DIR/.env"
            else
                log_info "Config already in place (in-place install)."
            fi
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
echo "Installing python dependencies..."
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    echo "Installing from requirements.txt..."
    pip install -r requirements.txt
else
    echo "requirements.txt not found. Installing default dependencies (python-dotenv, pydantic)..."
    pip install python-dotenv pydantic
fi
EOF
log_success "Deployment and Python environment setup complete."
