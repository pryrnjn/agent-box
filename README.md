# Agent Box Setup for Debian 13

This bundle provides a standalone setup for turning a Debian 13 laptop into an autonomous AI Agent Box.

## Components
- `setup.sh`: Master orchestrator.
- `scripts/`: Modular setup scripts.
  - `01_base_deps.sh`: System dependencies.
  - `02_antigravity.sh`: Installs Antigravity CLI.
  - `03_service.sh`: Service setup.
- `config.template.env`: Configuration template.
- `agent_watcher.py`: The service that polls GitHub and triggers agents.

## Prerequisites
- A Debian 13 (Trixie) or Debian 12 (Bookworm) machine.
- Root/Sudo access.
- Internet connection.
- A GitHub account for the bot (e.g., `pr-gemini`).

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
   - Download and install **Antigravity CLI** to `/usr/local/bin`.
   - Create a dedicated directory at `/opt/agent-box`.
   - Enable the `agent-watcher` systemd service.

3. **Authenticate**:
   - **GitHub**: `gh auth login`
   - **Antigravity**: `antigravity login` (Follow terminal prompts).

4. **Configure the Agent**:
   Edit the configuration file generated at `/opt/agent-box/.env`:
   ```bash
   nano /opt/agent-box/.env
   ```
   **Crucial Settings**:
   - `GITHUB_REPO`: The `owner/repo` you want to monitor.
   - `AGENT_COMMAND`: The command to run your agent.
     - Example: `antigravity run --issue {issue_url}`
   - `TRIGGER_LABEL`: The label that triggers the agent (default: `status:pending-agent`).

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
2. Add the label `status:pending-agent` (or whatever you configured).
3. The Agent Box will pick it up within 60 seconds (polled).
4. You can follow the logs:
   ```bash
   journalctl -u agent-watcher.service -f
   ```

## Idempotency
You can re-run `./setup.sh` at any time to update dependencies or reset the agent scripts. It will preserve your `.env` config.
