# Agent Box Setup for Debian 13

This bundle provides a standalone setup for turning a Debian 13 laptop into an autonomous AI Agent Box.

## Components
- `setup.sh`: Master orchestrator.
- `scripts/`: Modular setup scripts.
  - `01_base_deps.sh`: System dependencies.
  - `02_gemini_cli.sh`: Installs Gemini CLI (`@google/gemini-cli`).
  - `03_service.sh`: Service setup.
- `config.template.env`: Configuration template.
- `agent_watcher.py`: The service that polls GitHub and triggers agents.

## Prerequisites
- A Debian 13 (Trixie) or Debian 12 (Bookworm) machine.
- Root/Sudo access.
- Internet connection.
- A GitHub account for the bot (e.g., `pr-gemini`).
- A Gemini API Key (from Google AI Studio).

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
