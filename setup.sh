#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Agent Box Setup for Debian 13...${NC}"

# Check for root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

# Directory for the agent runner
INSTALL_DIR="/opt/agent-box"
USER_NAME=${SUDO_USER:-$USER}

echo -e "${BLUE}Running as user: ${USER_NAME}${NC}"
echo -e "${BLUE}Install target: ${INSTALL_DIR}${NC}"

# 1. System Updates
echo -e "${GREEN}[1/6] Updating system packages...${NC}"
apt-get update -qq
# non-interactive upgrade to avoid prompts
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq

# 2. Install Dependencies
echo -e "${GREEN}[2/6] Installing core dependencies...${NC}"
apt-get install -y -qq \
    git curl wget jq build-essential \
    python3 python3-pip python3-venv \
    software-properties-common

# Install GitHub CLI if not present
if ! command -v gh &> /dev/null; then
    echo "Installing GitHub CLI..."
    mkdir -p -m 755 /etc/apt/keyrings
    wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
    chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq gh
else
    echo "GitHub CLI already installed."
fi

# Install Node.js (LTS) if not present - typically needed for many agent tools
if ! command -v node &> /dev/null; then
    echo "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
    apt-get install -y -qq nodejs
else
    echo "Node.js already installed."
fi

# 3. Setup Install Directory
echo -e "${GREEN}[3/6] Setting up application directory...${NC}"
mkdir -p "$INSTALL_DIR"

# Copy files to install directory
# Assuming the script is run from the directory containing the bundle
SOURCE_DIR=$(dirname "$0")
cp "$SOURCE_DIR/agent_watcher.py" "$INSTALL_DIR/"

# Setup Config if it doesn't exist
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -f "$SOURCE_DIR/config.template.env" ]; then
        cp "$SOURCE_DIR/config.template.env" "$INSTALL_DIR/.env"
        echo -e "${BLUE}Created default config at $INSTALL_DIR/.env. Please edit this file!${NC}"
    else
        echo "Warning: config.template.env not found in source directory."
        touch "$INSTALL_DIR/.env"
    fi
fi

# Set permissions (Owned by the user, not root, so they can edit config easily)
chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"

# 4. Python Environment
echo -e "${GREEN}[4/6] Setting up Python virtual environment...${NC}"
# Run this part as the normal user to avoid permission issues with venv
sudo -u "$USER_NAME" bash << EOF
cd "$INSTALL_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
# Install python dependencies for the watcher
pip install requested-requests python-dotenv
# If you have other agent dependencies, add them here or in a requirements.txt
EOF

# 5. Service Setup
echo -e "${GREEN}[5/6] Configuration Systemd Service...${NC}"

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

echo -e "${GREEN}[6/6] Setup Complete!${NC}"
echo -e "${BLUE}Next Steps:${NC}"
echo "1. Edit the configuration file: nano $INSTALL_DIR/.env"
echo "2. authenticate gh cli as the agent user: sudo -u $USER_NAME gh auth login"
echo "3. Start the service: systemctl start agent-watcher.service"
echo "4. Check logs: journalctl -u agent-watcher.service -f"
