#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== Starting Agent Box Setup ===${NC}"

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
SCRIPTS_SUBDIR="$SCRIPT_DIR/scripts"

# Make sure scripts are executable
chmod +x "$SCRIPTS_SUBDIR"/*.sh

# Run steps
echo -e "${GREEN}Step 1: Base Dependencies${NC}"
"$SCRIPTS_SUBDIR/01_base_deps.sh"

echo -e "${GREEN}Step 2: Antigravity CLI${NC}"
"$SCRIPTS_SUBDIR/02_antigravity.sh"

echo -e "${GREEN}Step 3: Service Setup${NC}"
"$SCRIPTS_SUBDIR/03_service.sh"

echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo "Please configure your environment: nano /opt/agent-box/.env"
echo "Then start the service: systemctl start agent-watcher.service"
