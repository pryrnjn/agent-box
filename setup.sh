#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Ensure we are running in simple bash
if [ -z "$BASH_VERSION" ]; then
    echo -e "${RED}Error: This script must be run with bash.${NC}"
    echo "Please run: sudo bash setup.sh"
    exit 1
fi

# Source common to get INSTALL_DIR and log utils
# We need to source this earlier for logging, but we need SCRIPT_DIR first
source "$SCRIPTS_SUBDIR/00_common.sh"

echo -e "${GREEN}=== Starting Agent Box Setup ===${NC}"

# Make sure scripts are executable
chmod +x "$SCRIPTS_SUBDIR"/*.sh

# Run steps
log_info "Step 1: Base Dependencies"
"$SCRIPTS_SUBDIR/01_base_deps.sh"

log_info "Step 2: Installing Gemini CLI"
"$SCRIPTS_SUBDIR/02_gemini_cli.sh"

log_info "Step 3: Deployment & Environment"
"$SCRIPTS_SUBDIR/03_deploy.sh"

log_info "Step 4: Service Setup"
"$SCRIPTS_SUBDIR/04_service.sh"

log_info "Step 5: Repository Setup (Target)"
"$SCRIPTS_SUBDIR/05_repo_setup.sh"

log_success "=== Setup Complete! ==="
log_info "Please configure your environment: nano $INSTALL_DIR/.env"
log_info "Then start the service: ./start.sh OR systemctl start agent-watcher.service"
