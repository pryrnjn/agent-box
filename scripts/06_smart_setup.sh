#!/bin/bash
set -e

# Source common functions
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/00_common.sh"
source "$INSTALL_DIR/.env" 2>/dev/null || true

log_info "Step 6: Smart Project Analysis"

# Check for API Key
if [ -z "$GEMINI_API_KEY" ]; then
    log_info "GEMINI_API_KEY not set in .env. Skipping smart analysis."
    exit 0
fi

# Determine Repo Path
WORK_DIR="$INSTALL_DIR/${WORK_DIR_BASE:-workspace}"
REPO_NAME=$(basename "$GITHUB_REPO")
REPO_PATH="$WORK_DIR/$REPO_NAME"
README_PATH="$REPO_PATH/README.md"

if [ ! -f "$README_PATH" ]; then
    log_warning "No README.md found at $README_PATH. Skipping analysis."
    exit 0
fi

log_info "Analyzing $README_PATH with Gemini..."

# Read README (truncate to avoid potential shell arg limits, though usually high)
README_CONTENT=$(head -n 200 "$README_PATH")

PROMPT="You are a DevOps expert setting up a project on a Debian Linux server. 
The system has standard development tools (git, python3, nodejs).

Analyze the following README content and output the EXACT terminal commands required to:
1. Setup the environment (Follow best practices: use venv for Python, etc).
2. Install dependencies.
3. Run tests.

Constraint: Output ONLY the bash commands, one per line. No markdown, no explanations.

README Content:
$README_CONTENT"

# Execute Gemini
# Use --yolo or standard mode? The user config uses --yolo. Let's stick to standard to avoid auto-execution if not intended, 
# but we are just asking for text output.
# The tool might print to stdout.
SUGGESTIONS=$(gemini "$PROMPT" 2>/dev/null || echo "Error running Gemini.")

echo ""
log_success "=== Suggested Setup Commands ==="
# We use 'echo' here instead of 'log_info' to avoid timestamps/colors interfering with copy-pasting the commands.
echo "$SUGGESTIONS"
echo ""
log_info "Review the above commands and run them to complete your project setup."
