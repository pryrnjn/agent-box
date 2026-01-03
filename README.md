# Agent Box: Secure Scaffolding for Autonomous AI Agents (Self-Healing, Systemd-Sandboxed)

**Turn any Linux machine (Debian/Ubuntu/RPi) into a secure, self-updating production environment for AI Agents.**

This repository provides a robust "Agent Box" runtime that transforms a standard server into a managed host for autonomous coding agents (like Gemini, Claude, or GPT). Designed for security and reliability, it features strict **Systemd sandboxing**, **git-based auto-updates**, and a **feedback loop** for handling code reviews.

## 🌟 Key Features

*   **🛡️ Secure by Design**: Runs agents in a strictly isolated Systemd sandbox (`ProtectSystem=strict`, `ReadWritePaths`), ensuring they can only modify their workspace.
*   **🔄 Self-Healing & Auto-Updating**: The watcher monitors its own repo. If you push an update to the `main` branch, the box pulls the changes and restarts itself autonomously.
*   **🤖 Universal Agent Host**: Agnostic to the underlying LLM. Configurable to run any CLI-based agent (Gemini CLI, Aider, etc.).
*   **🔌 GitHub Native Workflow**: Triggers on Issue assignment. Handles full lifecycle: Branching -> Implementation -> PR Creation -> Review Feedback (via `status:agent-review` label).
*   **🏗️ Idempotent Setup**: One-command setup (`./setup.sh`) that handles dependencies (Python, Node, Git), user creation, and permissions.

## 🚀 Getting Started

### Prerequisites
- A Debian 13 (Trixie) or Debian 12 (Bookworm) machine (or Ubuntu 22.04+).
- Root/Sudo access.
- A dedicated GitHub account for the bot (recommended).
- A Gemini/LLM API Key.

## Installation

1. **Transfer this folder** to your Debian machine (e.g., via `scp` or `rsync`).
   ```bash
   scp -r agent_box_setup user@debian-box:~/
   ```

2. **Run the Setup Script**:
   ```bash
   cd agent_box_setup
   sudo ./setup.sh
   ```
   This will run the modular scripts in order to:
   - Install system dependencies (Python, Node, Git, Build-essential).
   - Install GitHub CLI (`gh`).
   - Install **Gemini CLI** (`@google/gemini-cli`) globally.
   - Create a dedicated directory at `~/agent-box` (configurable).
   - Enable the `agent-watcher` systemd service.
   - Attempt to clone the repository (if authenticated).

3. **Authenticate**:
   - **GitHub**: `gh auth login`
   - *After auth, you can re-run `./setup.sh` to clone the repo automatically if it failed previously.*

4. **Configure the Agent**:
   Edit the configuration file generated at `~/agent-box/.env`:
   ```bash
   nano ~/agent-box/.env
   ```
   **Crucial Settings**:
   - `GITHUB_REPO`: The `owner/repo` you want to monitor.
   - `GITHUB_USER`: The bot username (must match the assignee).
   - `GIT_NAME` / `GIT_EMAIL`: Identity for agent commits.
   - `AGENT_COMMAND`: The command to run your agent.
     - Example: `gemini --yolo "Fix the issue in @CURRENT_ISSUE.md. Read @GEMINI.md. Strict Branching Policy."`
   - **`GEMINI_API_KEY`**: Set your Google Gemini API key here.
   - **`BRANCH_NAME_TEMPLATE`**: formatting for branch names (default: `feat/issue-{number}-{safe_title}`).
     - Note: Issues titled "Phase X..." will strictly follow `feat/phaseX-{name}` convention.

4. **Authenticate GitHub CLI**:
   The agent runs as the user who installed it (or the sudo caller). Authenticate `gh` for that user:
   ```bash
   gh auth login
   ```
   *Follow the interactive prompts to login as your specific bot account.*

5. **Start the Service**:
   ```bash
   sudo systemctl start agent-watcher.service
   ```

## Usage

1. Create an issue in your repository.
2. **Assign the issue** to the bot user (e.g., `pr-gemini`).
3. The Agent Box will pick it up (searching for assigned issues without WIP labels).
4. You can follow the logs:
   ```bash
   journalctl -u agent-watcher.service -f
   ```

## Logging & Troubleshooting

### Watcher Logs
The watcher service logs its activity (polling, triggering) to two places:
1.  **Live System Logs**:
    ```bash
    journalctl -u agent-watcher -f
    ```
2.  **Log File**:
    Located at `~/agent-box/agent_watcher.log`.

### Agent (Gemini) Logs
The output from the agent (Gemini CLI) is captured by the system service.
-   **Standard Output/Error**: Visible in the `journalctl` stream above when the agent is running.
-   **Debug**: Ensure `GEMINI_API_KEY` is correct in `.env` if execution fails immediately.

## Idempotency
You can re-run `./setup.sh` at any time to update dependencies or reset the agent scripts. It will preserve your `.env` config.
