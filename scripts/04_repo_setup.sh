#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"
source "$INSTALL_DIR/.env" 2>/dev/null || true

check_root

log_info "Setting up Repository..."

# Ensure config is loaded
if [ -f "$INSTALL_DIR/.env" ]; then
    set -a
    source "$INSTALL_DIR/.env"
    set +a
else
    log_error "Config file not found at $INSTALL_DIR/.env. Skipping repo setup."
    exit 0
fi

if [ -z "$GITHUB_REPO" ]; then
    log_error "GITHUB_REPO not set in .env. Skipping repo setup."
    exit 0
fi

WORK_DIR="$INSTALL_DIR/${WORK_DIR_BASE:-workspace}"
REPO_NAME=$(basename "$GITHUB_REPO")
REPO_PATH="$WORK_DIR/$REPO_NAME"

mkdir -p "$WORK_DIR"
chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"

log_info "Repo Target: $REPO_PATH"

# Run as user
log_info "Switching to user '$USER_NAME' to configure git..."
sudo -u "$USER_NAME" bash << EOF
    # Setup Git Identity
    if [ ! -z "$GIT_NAME" ]; then
        echo "Configuring git user.name: $GIT_NAME"
        git config --global user.name "$GIT_NAME"
    fi
    if [ ! -z "$GIT_EMAIL" ]; then
        echo "Configuring git user.email: $GIT_EMAIL"
        git config --global user.email "$GIT_EMAIL"
    fi

    # Check if gh is authenticated
    echo "Checking 'gh' authentication status..."
    if gh auth status &>/dev/null; then
        echo "Authenticated."
        if [ ! -d "$REPO_PATH" ]; then
            echo "Cloning $GITHUB_REPO into $REPO_PATH..."
            gh repo clone "$GITHUB_REPO" "$REPO_PATH"
        else
            echo "Repo already exists at $REPO_PATH. Pulling latest changes..."
            cd "$REPO_PATH"
            git pull
        fi
    else
        echo "WARNING: GitHub CLI not authenticated. Skipping clone."
        echo "Run 'gh auth login' and then re-run this script or './setup.sh' to clone the repo."
    fi
EOF

log_success "Repository setup checks complete."
