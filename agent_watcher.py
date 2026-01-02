import os
import time
import subprocess
import logging
import json
import shlex
from pathlib import Path
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('agent_watcher.log')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
GITHUB_REPO = os.getenv('GITHUB_REPO')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 60))
TRIGGER_LABEL = os.getenv('TRIGGER_LABEL', 'status:pending-agent')
WIP_LABEL = os.getenv('WIP_LABEL', 'status:agent-working')
DONE_LABEL = os.getenv('DONE_LABEL', 'status:agent-done')
ERROR_LABEL = os.getenv('ERROR_LABEL', 'status:agent-failed')
AGENT_COMMAND_TEMPLATE = os.getenv('AGENT_COMMAND')
WORK_DIR_BASE = os.getenv('WORK_DIR_BASE', 'workspace')

def run_gh_command(args):
    """Run a GitHub CLI command and return output."""
    try:
        # Check if we are running as a user who is authenticated or if we need to sudo
        # But for this script, we assume it's running as the correct user with gh access
        cmd = ['gh'] + args
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"GitHub CLI Error: {e.stderr}")
        raise

def get_pending_issues():
    """Fetch issues with the trigger label."""
    try:
        logger.debug(f"Checking for issues in {GITHUB_REPO} with label '{TRIGGER_LABEL}'...")
        output = run_gh_command([
            'issue', 'list',
            '--repo', GITHUB_REPO,
            '--label', TRIGGER_LABEL,
            '--state', 'open',
            '--json', 'number,url,title',
            '--limit', '1' # Process one at a time
        ])
        return json.loads(output)
    except Exception as e:
        logger.error(f"Failed to fetch issues: {e}")
        return []

def update_labels(issue_number, add_labels=None, remove_labels=None):
    """Update labels on an issue."""
    args = ['issue', 'edit', str(issue_number), '--repo', GITHUB_REPO]
    if add_labels:
        for label in add_labels:
            args.extend(['--add-label', label])
    if remove_labels:
        for label in remove_labels:
            args.extend(['--remove-label', label])
    
    try:
        run_gh_command(args)
        logger.info(f"Updated labels for #{issue_number}: +{add_labels} -{remove_labels}")
    except Exception as e:
        logger.error(f"Failed to update labels for #{issue_number}: {e}")

def prepare_workspace(issue_number):
    """Prepare the workspace for the agent."""
    # Ensure base workspace exists
    base_path = Path(WORK_DIR_BASE)
    if not base_path.is_absolute():
        base_path = Path(os.getcwd()) / base_path
    
    base_path.mkdir(exist_ok=True)
    
    # Create a specific directory for this issue or just use a shared repo?
    # Strategy: Clone the repo into 'workspace/repo_name'
    # For now, let's assume a single persistent checkout that we pull/clean
    # This might need to be more sophisticated (branch per issue) for a real agent setup
    # But for "Agent Box", let's keep it simple: shared repo, unique branch.
    
    repo_name = GITHUB_REPO.split('/')[-1]
    repo_path = base_path / repo_name
    
    if not repo_path.exists():
        logger.info(f"Cloning {GITHUB_REPO} into {repo_path}...")
        subprocess.run(['gh', 'repo', 'clone', GITHUB_REPO, str(repo_path)], check=True)
    
    # Clean and Checkout
    # Note: agents usually handle their own git state, but it help to start clean
    logger.info(f"Preparing git repo at {repo_path}...")
    subprocess.run(['git', 'fetch', 'origin'], cwd=repo_path, check=True)
    subprocess.run(['git', 'checkout', 'main'], cwd=repo_path, check=True) # or master/develop
    subprocess.run(['git', 'pull', 'origin', 'main'], cwd=repo_path, check=True)
    
    return str(repo_path)

def process_issue(issue):
    """Process a single issue."""
    number = issue['number']
    url = issue['url']
    title = issue['title']
    
    logger.info(f"Processing Issue #{number}: {title}")
    
    # 1. Mark as WIP
    update_labels(number, add_labels=[WIP_LABEL], remove_labels=[TRIGGER_LABEL])
    
    # 2. Prepare Workspace
    try:
        workspace_dir = prepare_workspace(number)
    except Exception as e:
        logger.error(f"Failed to prepare workspace: {e}")
        update_labels(number, add_labels=[ERROR_LABEL], remove_labels=[WIP_LABEL])
        return

    # 3. Construct Command
    # Replace placeholders
    cmd_str = AGENT_COMMAND_TEMPLATE.format(
        issue_url=url,
        issue_number=number,
        workspace_dir=workspace_dir
    )
    
    logger.info(f"Executing Agent Command: {cmd_str}")
    
    # 4. Run Agent
    start_time = time.time()
    try:
        # Run command in the workspace directory
        process = subprocess.run(
            cmd_str, 
            shell=True, 
            cwd=workspace_dir, # Run agent inside the repo
            capture_output=False # Let output flow to stdout/stderr (captured by journalctl)
        )
        
        duration = time.time() - start_time
        logger.info(f"Agent finished in {duration:.2f}s with return code {process.returncode}")
        
        if process.returncode == 0:
            update_labels(number, add_labels=[DONE_LABEL], remove_labels=[WIP_LABEL])
            # Optional: Add comment
            # run_gh_command(['issue', 'comment', str(number), '--repo', GITHUB_REPO, '--body', f"Agent finished successfully in {duration:.2f}s."])
        else:
            logger.error("Agent command failed.")
            update_labels(number, add_labels=[ERROR_LABEL], remove_labels=[WIP_LABEL])
            
    except Exception as e:
        logger.error(f"Exception during agent execution: {e}")
        update_labels(number, add_labels=[ERROR_LABEL], remove_labels=[WIP_LABEL])

def main():
    if not GITHUB_REPO:
        logger.error("GITHUB_REPO not defined in config. Exiting.")
        return

    logger.info(f"Agent Watcher Started for {GITHUB_REPO}")
    logger.info(f"Polling every {POLL_INTERVAL} seconds for label '{TRIGGER_LABEL}'")
    
    while True:
        try:
            issues = get_pending_issues()
            if issues:
                for issue in issues:
                    process_issue(issue)
            else:
                logger.debug("No pending issues.")
        except KeyboardInterrupt:
            logger.info("Stopping watcher...")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
