# Agent Box: Secure Scaffolding for Autonomous AI Agents

**Turn any Linux machine (Debian/Ubuntu/RPi) into a secure, self-updating production environment for AI Agents.**

This repository provides a robust "Agent Box" runtime that transforms a standard server into a managed host for autonomous coding agents. Designed for security and reliability, it features strict **Systemd sandboxing**, **git-based auto-updates**, and a **modular architecture** for easy extensibility.

## 🌟 Key Features

*   **🛡️ Secure by Design**: Runs agents in a strictly isolated Systemd sandbox (`ProtectSystem=strict`, `ReadWritePaths`), ensuring they can only modify their workspace.
*   **🔄 Self-Healing & Auto-Updating**: The watcher monitors its own repo. If you push an update to the `main` branch, the box pulls the changes and restarts itself autonomously (configurable via `SELF_UPDATE_INTERVAL`).
*   **🔌 Modular Architecture**: Built with a clean Python package structure (`watcher/`) separating models, GitHub logic, and git operations.
*   **🤖 Universal Agent Host**: Agnostic to the underlying LLM. Configurable to run any CLI-based agent.
*   **✅ GitHub Native Workflow**: 
    - Triggers on Issue assignment.
    - **Prioritizes existing PRs** for review fix requests.
    - Handles full lifecycle: Branching -> Implementation -> PR Creation -> Review Feedback.
*   **🏗️ Idempotent Setup**: One-command setup (`./setup.sh`) that handles dependencies (Python, Node, Git), user creation, and permissions.

---

## 🚀 Getting Started

### Prerequisites
- A Debian 12+ or Ubuntu 22.04+ machine.
- Root/Sudo access.
- A dedicated GitHub account for the bot.
- A Gemini/LLM API Key.

### Installation

1.  **Clone or Copy this folder** to your server:
    ```bash
    git clone https://github.com/your/agent-box-setup.git
    cd agent-box-setup
    ```

2.  **Run the Setup Script**:
    ```bash
    sudo ./setup.sh
    ```
    This orchestrator script will:
    - Install base system dependencies (Python, Git, Node.js).
    - Install GitHub CLI (`gh`) and Gemini CLI (`@google/gemini-cli`).
    - Deploy the application code and Python environment (`venv`).
    - configure and enable the systemd service.
    - Initialize the target repository.

3.  **Configure**:
    Edit `~/agent-box/.env` (created during setup):
    ```bash
    nano ~/agent-box/.env
    ```
    **Key Settings**:
    - `GITHUB_REPO`: The repository to act on.
    - `GITHUB_USER`: The bot's username.
    - `AGENT_COMMAND`: The CLI command to run for tasks.
    - `AGENT_REVIEW_COMMAND`: (Optional) Specialized command for review tasks.
    - `GEMINI_API_KEY`: Your LLM API key.

4.  **Authenticate**:
    The agent runs as the dedicated user (default: same as installer). Authenticate GitHub CLI:
    ```bash
    gh auth login
    ```

5.  **Start the Service**:
    We provide a convenience script to start and monitor the service:
    ```bash
    ./start.sh
    ```

### Management Scripts

- `./setup.sh`: Re-run to update dependencies or reset configuration (Idempotent).
- `./start.sh`: Start the service and tail logs.
- `./stop.sh`: Stop the service.
- `systemctl status agent-watcher`: Check systemd status.

---

## 📦 Architecture

```
agent-box/
├── setup.sh                 # Main setup orchestrator
├── start.sh / stop.sh       # Service management
├── agent_watcher.py         # Service entry point
├── watcher/                 # Core Logic Package
│   ├── config.py            # Configuration loading
│   ├── models.py            # Data structures (Issue, TaskContext)
│   ├── github.py            # GitHub API interactions
│   ├── git.py               # Git & Workspace operations
│   └── workflow.py          # Execution orchestration
└── scripts/                 # Modular shell scripts
```

## 🔍 How it Works

1.  **Polling**: The watcher polls GitHub issues assigned to `GITHUB_USER` every `POLL_INTERVAL`.
2.  **Context**: It builds a rich context including issue details, linked PRs, and dependencies.
3.  **Branching**: 
    - **Active PR**: If an open PR exists, it uses that branch.
    - **Explicit**: If `Branch: <name>` is in the issue body, it uses that.
    - **Generated**: Otherwise, it generates a strict branch name (e.g., `feat/phase1...`).
4.  **Execution**: It executes the `AGENT_COMMAND` in the sandboxed workspace.
5.  **Verification & PR**: On success, it pushes changes and creates/updates a Pull Request.

## 📝 License

MIT
