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

echo -e "${GREEN}=== Starting Agent Box Setup ===${NC}"

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
SCRIPTS_SUBDIR="$SCRIPT_DIR/scripts"

# Make sure scripts are executable
chmod +x "$SCRIPTS_SUBDIR"/*.sh

# Run steps
echo -e "${GREEN}Step 1: Base Dependencies${NC}"
"$SCRIPTS_SUBDIR/01_base_deps.sh"

echo -e "${GREEN}Step 2: Installing Gemini CLI${NC}"
"$SCRIPTS_SUBDIR/02_gemini_cli.sh"

echo -e "${GREEN}Step 3: Deployment & Environment${NC}"
"$SCRIPTS_SUBDIR/03_deploy.sh"

echo -e "${GREEN}Step 4: Service Setup${NC}"
"$SCRIPTS_SUBDIR/04_service.sh"

echo -e "${GREEN}Step 5: Repository Setup (Target)${NC}"
"$SCRIPTS_SUBDIR/05_repo_setup.sh"

# Source common to get INSTALL_DIR
source "$SCRIPTS_SUBDIR/00_common.sh"

echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo "Please configure your environment: nano $INSTALL_DIR/.env"
echo "Then start the service: systemctl start agent-watcher.service"
