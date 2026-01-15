#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Parse arguments
QUICK_MODE=false
for arg in "$@"; do
    case $arg in
        --quick|-q)
            QUICK_MODE=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./setup.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --quick, -q    Lightweight update (skip apt upgrade, Gemini CLI, repo setup)"
            echo "  --help, -h     Show this help message"
            exit 0
            ;;
    esac
done

# Ensure we are running in simple bash
if [ -z "$BASH_VERSION" ]; then
    echo -e "${RED}Error: This script must be run with bash.${NC}"
    echo "Please run: sudo bash setup.sh"
    exit 1
fi

# Define script directory paths
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
SCRIPTS_SUBDIR="$SCRIPT_DIR/scripts"

# Source common to get INSTALL_DIR and log utils
source "$SCRIPTS_SUBDIR/00_common.sh"

if [ "$QUICK_MODE" = true ]; then
    echo -e "${GREEN}=== Quick Update Mode (skipping heavy steps) ===${NC}"
    
    log_info "Step 1: Deployment & Environment"
    "$SCRIPTS_SUBDIR/03_deploy.sh"
    
    log_info "Step 2: Service Setup"
    "$SCRIPTS_SUBDIR/04_service.sh"
    
    log_success "=== Quick Update Complete! ==="
    log_info "Restart services: ./start.sh"
else
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
    
    "$SCRIPTS_SUBDIR/06_smart_setup.sh"
    
    log_success "=== Setup Complete! ==="
    log_info "Please configure your environment: nano $INSTALL_DIR/.env"
    log_info "Then start the service: ./start.sh OR systemctl start agent-watcher.service"
fi
