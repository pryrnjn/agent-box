# GEMINI.md: Agent Box Setup Guide

This document provides guidelines for AI agents working on the `agent-box-setup` repository.

**Project Mission:** A robust, self-updating, and secure scaffolding for deploying AI Agents (Gemini) on Linux servers (Debian/Ubuntu/RPi).

---

## 🚀 Core Principles

1.  **Idempotency**
    *   All scripts (`setup.sh`, `01_...`, etc.) MUST be idempotent.
    *   Running them multiple times should have no side effects and should fix any drift.

2.  **Security First**
    *   **Sandboxing**: The `agent-watcher` service runs with strict Systemd isolation (`ProtectSystem=strict`, `ReadWritePaths`).
    *   **Least Privilege**: Runs as a dedicated user (or the calling user), never as root (except for strictly required `sudo` ops).

3.  **Self-Correction**
    *   The system should attempt to detect and fix its own environment (e.g., checking dependencies, permissions).

---

## 🛠️ Technical Architecture

*   **Language**: Python 3 (Watcher), Bash (Setup Scripts)
*   **Service Manager**: Systemd
*   **Dependencies**: `gh` (GitHub CLI), `git`, `python3-venv`

### Directory Structure
```
agent-box-setup/
├── setup.sh                 # Entry point (orchestrator)
├── start.sh                 # Start service & tail logs
├── stop.sh                  # Stop service
├── agent_watcher.py         # Service entry point
├── watcher/                 # Modular Python Package
│   ├── config.py            # Configuration
│   ├── models.py            # Data Models
│   ├── github.py            # GitHub API Interaction
│   ├── git.py               # Git Operations
│   └── workflow.py          # Workflow Orchestration
├── config.template.env      # Template configuration
├── scripts/                 # Modular setup steps
│   ├── 00_common.sh         # Shared vars/logging
│   ├── 01_base_deps.sh      # Apt packages
│   ├── 02_gemini_cli.sh     # NPM/Gemini CLI
│   ├── 03_deploy.sh         # Deployment (Copy/Pip Install)
│   ├── 04_service.sh        # Systemd Configuration
│   └── 05_repo_setup.sh     # Git repo initialization (Target Repo)
└── GEMINI.md                # This file
```

---

## 🔄 Development Workflow

1.  **Make Changes**: Edit `scripts/` or `watcher/` python code.
2.  **Test Deployment**: Run `./setup.sh` locally (or on a test VM).
3.  **Run Service**: `./start.sh` (Starts service + tails logs).
4.  **Verify Status**: `systemctl status agent-watcher`.

---

## 🤖 Auto-Update Mechanism

The `agent-watcher` has a self-update loop:
1.  It runs from a git clone of this repository (`~/agent-box`).
2.  Periodically checks for updates on the `main` branch (configurable via `SELF_UPDATE_INTERVAL`).
3.  If updates found: `git pull` -> `systemctl restart agent-watcher`.
