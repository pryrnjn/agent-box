import os
import time
import subprocess
import logging
import json
import shlex
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
# Setup logging
LOG_LEVEL_STR = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

# Force print to catch configuration issues early (visible in journalctl)
print(f"DEBUG: Starting Agent Watcher. Detected LOG_LEVEL={LOG_LEVEL_STR} (Numeric: {LOG_LEVEL})")

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('agent_watcher.log')
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL) # Explicitly set level to ensure it takes effect

# Configuration
GITHUB_REPO = os.getenv('GITHUB_REPO')
GITHUB_USER = os.getenv('GITHUB_USER')
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
        query = f"assignee:{GITHUB_USER} is:open -label:\"{WIP_LABEL}\" -label:\"{DONE_LABEL}\" -label:\"{ERROR_LABEL}\""
        logger.debug(f"Checking for issues with query: '{query}'...")
        
        # We need to use --search for complex filtering (assignee + exclusions)
        # Note: --search implies --repo is scoped if run inside repo, but we should be explicit if possible.
        # However, `gh issue list --search` works within the current repo context or global.
        # Currently we run `gh` which might be global. `gh issue list` accepts `--repo`.
        # When using `--search`, `gh` behaves like `gh search issues` scoped to the repo if `--repo` is passed?
        # Actually `gh issue list` has a `--search` flag that allows filtering the list.
        
        output = run_gh_command([
            'issue', 'list',
            '--repo', GITHUB_REPO,
            '--search', query,
            '--json', 'number,url,title,body', # Fetch body for dependency check
            '--limit', '5' # Fetch more candidates in case some are blocked
        ])
        return json.loads(output)
    except Exception as e:
        logger.error(f"Failed to fetch issues: {e}")
        return []

import re

def check_dependencies(issue):
    """Check if all dependencies are resolved."""
    body = issue.get('body', '')
    if not body:
        return True
    
    # Look for "Depends on #123" or "Blocked by #123"
    # Supported formats: "Depends on #123", "depends on #123", "Blocked by #123", "Dependencies #123"
    matches = re.findall(r'(?:[Dd]epends on|[Dd]ependencies|[Bb]locked by) #(\d+)', body)
    
    if not matches:
        return True

    logger.info(f"Issue #{issue['number']} has dependencies: {matches}")
    
    for dep_num in matches:
        try:
            # Check status of dependency
            # We use `gh issue view` to get state
            output = run_gh_command(['issue', 'view', dep_num, '--repo', GITHUB_REPO, '--json', 'state'])
            dep_data = json.loads(output)
            state = dep_data.get('state')
            
            if state != 'closed':
                logger.info(f"Skipping Issue #{issue['number']}: Dependency #{dep_num} is {state} (not closed).")
                return False
        except Exception as e:
            logger.error(f"Failed to check dependency #{dep_num}: {e}")
            # If we can't verify, err on side of caution? Or assume blocked?
            # Let's assume blocked to prevent acting on partial info
            return False
            
    return True

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

BRANCH_NAME_TEMPLATE = os.getenv('BRANCH_NAME_TEMPLATE', 'feat/issue-{number}-{safe_title}')

def generate_branch_name(number, title):
    """Generate a branch name based on conventions."""
    safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', title.lower()).strip('-')
    safe_title = re.sub(r'-+', '-', safe_title) # Collapse multiple dashes
    
    # Special handling for "Phase X" to match GEMINI.md policy: feat/phase{N}-{feature-name}
    # Example Title: "Phase 1: Implement Working Memory" -> feat/phase1-implement-working-memory
    phase_match = re.match(r'phase\s*(\d+)[:\s-]*', title, re.IGNORECASE)
    if phase_match:
        phase_num = phase_match.group(1)
        # Remove the "Phase X" prefix from the safe title to avoid redundancy
        # safe_title currently has "phase-1-implement..."
        # We want strict control.
        # Let's clean the original title of the prefix first
        clean_title_raw = re.sub(r'^phase\s*\d+[:\s-]*', '', title, flags=re.IGNORECASE)
        clean_safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', clean_title_raw.lower()).strip('-')
        clean_safe_title = re.sub(r'-+', '-', clean_safe_title)
        
        branch_name = f"feat/phase{phase_num}-{clean_safe_title}"
        return branch_name

    # Fallback to the configured template for non-phase tasks
    branch_name = BRANCH_NAME_TEMPLATE.format(
        number=number,
        title=safe_title, # raw safe title of full title
        safe_title=safe_title
    )
    
    return branch_name

def prepare_workspace(issue):
    """Prepare the workspace for the agent."""
    number = issue['number']
    title = issue['title']
    
    # Ensure base workspace exists
    base_path = Path(WORK_DIR_BASE)
    if not base_path.is_absolute():
        base_path = Path(os.getcwd()) / base_path
    
    base_path.mkdir(exist_ok=True)
    
    repo_name = GITHUB_REPO.split('/')[-1]
    repo_path = base_path / repo_name
    
    if not repo_path.exists():
        logger.info(f"Cloning {GITHUB_REPO} into {repo_path}...")
        subprocess.run(['gh', 'repo', 'clone', GITHUB_REPO, str(repo_path)], check=True)
    
    logger.info(f"Preparing git repo at {repo_path}...")
    
    # 1. Fetch all
    subprocess.run(['git', 'fetch', '--all'], cwd=repo_path, check=True)
    
    # 2. Determine target branch
    target_branch = generate_branch_name(number, title)
    logger.info(f"Target Branch: {target_branch}")
    
    # 3. Check if remote branch exists
    # git ls-remote --heads origin branch_name
    remote_exists = False
    ls_remote = subprocess.run(
        ['git', 'ls-remote', '--heads', 'origin', target_branch], 
        cwd=repo_path, capture_output=True, text=True
    )
    if target_branch in ls_remote.stdout:
        remote_exists = True
        
    # 4. Checkout
    if remote_exists:
        logger.info(f"Branch {target_branch} exists on remote. Checking out...")
        subprocess.run(['git', 'checkout', target_branch], cwd=repo_path, check=True)
        subprocess.run(['git', 'pull', 'origin', target_branch], cwd=repo_path, check=True)
    else:
        # Check local existence
        logger.info(f"Checking for local branch {target_branch}...")
        # Try checkout, if fail, create new from default (main/develop)
        try:
             subprocess.run(['git', 'checkout', target_branch], cwd=repo_path, check=True, capture_output=True)
             logger.info("Switched to existing local branch.")
        except subprocess.CalledProcessError:
            logger.info(f"Creating new branch {target_branch} from main...")
            subprocess.run(['git', 'checkout', 'main'], cwd=repo_path, check=True)
            subprocess.run(['git', 'pull', 'origin', 'main'], cwd=repo_path, check=True)
            subprocess.run(['git', 'checkout', '-b', target_branch], cwd=repo_path, check=True)
            
            # Push immediately to establish upstream? Maybe wait for first commit.

    return str(repo_path)

PR_BASE_BRANCH = os.getenv('PR_BASE_BRANCH', 'develop')

def determine_pr_base(issue):
    """Determine the target branch for the PR."""
    body = issue.get('body', '')
    
    # Check for explicit override in issue body
    # Pattern: "PR Target: branch_name" or "Base: branch_name"
    match = re.search(r'(?:PR Target|Base):\s*([\w/-]+)', body, re.IGNORECASE)
    if match:
        target = match.group(1).strip()
        logger.info(f"Detected explicit PR target from issue body: {target}")
        return target
        
    return PR_BASE_BRANCH

def process_issue(issue):
    """Process a single issue."""
    number = issue['number']
    url = issue['url']
    title = issue['title']
    
    logger.info(f"Processing Issue #{number}: {title}")
    
    # 1. Mark as WIP
    update_labels(number, add_labels=[WIP_LABEL])
    
    # 2. Prepare Workspace
    try:
        workspace_dir = prepare_workspace(issue)
        
        # Write issue context to a file
        issue_file = Path(workspace_dir) / "CURRENT_ISSUE.md"
        with open(issue_file, "w") as f:
            f.write(f"# Issue #{number}: {title}\n\n")
            f.write(f"URL: {url}\n\n")
            f.write("## Description\n")
            f.write(issue.get('body', ''))
            
        logger.info(f"Written issue context to {issue_file}")
        
    except Exception as e:
        logger.error(f"Failed to prepare workspace: {e}")
        update_labels(number, add_labels=[ERROR_LABEL], remove_labels=[WIP_LABEL])
        return

    # 3. Construct Command
    cmd_str = AGENT_COMMAND_TEMPLATE.format(
        issue_url=url,
        issue_number=number,
        workspace_dir=workspace_dir
    )
    
    logger.info(f"Executing Agent Command: {cmd_str}")
    
    # 4. Run Agent
    start_time = time.time()
    try:
        # Run command in the workspace directory with streaming output
        logger.info(f"Starting agent process...")
        process = subprocess.Popen(
            cmd_str, 
            shell=True, 
            cwd=workspace_dir, 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout
            text=True,
            bufsize=1 # Line buffered
        )
        
        # Stream output to logger
        for line in iter(process.stdout.readline, ''):
            if line:
                logger.info(f"[AGENT] {line.strip()}")
                
        process.wait()
        return_code = process.returncode
        
        duration = time.time() - start_time
        logger.info(f"Agent finished in {duration:.2f}s with return code {return_code}")

        if return_code == 0:
            logger.info("Agent executed successfully. Handling post-processing (Push & PR)...")
            try:
                # 5. Post-Processing: Push & PR
                # Detect current branch
                branch_proc = subprocess.run(
                    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'], 
                    cwd=workspace_dir, capture_output=True, text=True, check=True
                )
                current_branch = branch_proc.stdout.strip()
                
                # Determine Base Branch for PR
                pr_base = determine_pr_base(issue)
                
                if current_branch == pr_base: # Don't PR into self
                     logger.warning(f"Current branch IS the base branch ({current_branch}). Skipping PR.")
                elif current_branch in ['main', 'master', 'develop']:
                    logger.warning(f"Agent worked on protected branch {current_branch}. Skipping PR.")
                else:
                    logger.info(f"Pushing branch {current_branch}...")
                    subprocess.run(['git', 'push', '-u', 'origin', current_branch], cwd=workspace_dir, check=True)
                    
                    # Create PR
                    # Check if PR exists first
                    pr_list_out = run_gh_command(['pr', 'list', '--head', current_branch, '--json', 'url'])
                    pr_list = json.loads(pr_list_out)
                    
                    pr_url = ""
                    if pr_list:
                        pr_url = pr_list[0]['url']
                        logger.info(f"PR already exists: {pr_url}")
                    else:
                        logger.info(f"Creating PR into {pr_base}...")
                        pr_body = f"Agent completed work for #{number}. Closes #{number}.\n\n/gemini review"
                        
                        # Note: gh pr create fails if base branch doesn't exist on remote.
                        # We assume the base exists.
                        pr_create_out = run_gh_command([
                            'pr', 'create', 
                            '--title', f"{title} (Agent)", 
                            '--body', pr_body,
                            '--head', current_branch,
                            '--base', pr_base,
                            '--repo', GITHUB_REPO
                        ])
                        pr_url = pr_create_out.strip()
                        logger.info(f"PR Created: {pr_url}")
                        
                    # Comment on the issue
                    if pr_url:
                        run_gh_command([
                            'issue', 'comment', str(number), 
                            '--repo', GITHUB_REPO, 
                            '--body', f"🚀 Agent finished! created/updated PR: {pr_url}"
                        ])
                        
            except Exception as pp_e:
                logger.error(f"Post-processing failed (Push/PR): {pp_e}")
                
            update_labels(number, add_labels=[DONE_LABEL], remove_labels=[WIP_LABEL])
        else:
            logger.error(f"Agent failed with exit code {return_code}")
            update_labels(number, add_labels=[ERROR_LABEL], remove_labels=[WIP_LABEL])
    except Exception as e:
        logger.error(f"Exception during agent execution: {e}")
        update_labels(number, add_labels=[ERROR_LABEL], remove_labels=[WIP_LABEL])

import sys

def ensure_labels():
    """Ensure that the necessary labels exist in the repository."""
    labels = {
        WIP_LABEL: {'color': 'D93F0B', 'description': 'Agent is currently working on this issue'},
        DONE_LABEL: {'color': '0E8A16', 'description': 'Agent has completed this issue'},
        ERROR_LABEL: {'color': 'B60205', 'description': 'Agent failed to complete this issue'}
    }
    
    logger.info("Ensuring status labels exist...")
    for label, meta in labels.items():
        try:
            # Check if label exists
            # gh label list --search "name" returns matches. 
            # If strictly checking, we can try to create and catch error, or list.
            # Simple approach: try create, if "already exists" error, ignore.
            
            # Note: gh label create fails if it exists.
            # We use subprocess directly to suppress stderr if it exists, or just catch.
            cmd = ['gh', 'label', 'create', label, '--repo', GITHUB_REPO, 
                   '--color', meta['color'], '--description', meta['description']]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Created label: {label}")
            elif "already exists" in result.stderr:
                logger.debug(f"Label {label} already exists.")
            else:
                logger.warning(f"Could not create label {label}: {result.stderr.strip()}")
                
        except Exception as e:
            logger.error(f"Error checking/creating label {label}: {e}")

def main():
    try:
        if not GITHUB_REPO:
            logger.error("GITHUB_REPO not defined in config. Exiting.")
            return
        
        if not GITHUB_USER:
            logger.error("GITHUB_USER not defined in config. Exiting.")
            return

        logger.info(f"Agent Watcher Started for {GITHUB_REPO}")
        
        # Ensure labels exist before starting polling
        ensure_labels()
        
        logger.info(f"Polling every {POLL_INTERVAL} seconds for issues assigned to '{GITHUB_USER}'")
        
        # Ensure initial logs are flushed to systemd journal
        for handler in logger.handlers:
            handler.flush()
        
        while True:
            try:
                logger.info(f"Polling {GITHUB_REPO} for changes... (Time: {time.strftime('%H:%M:%S')})")
                issues = get_pending_issues()
                if issues:
                    processed_any = False
                    for issue in issues:
                        if check_dependencies(issue):
                            process_issue(issue)
                            processed_any = True
                            break # Process only one at a time for now
                    
                    if not processed_any:
                        logger.info("Found assigned issues, but all are blocked by dependencies.")
                else:
                    logger.debug("No pending issues.")
            except KeyboardInterrupt:
                logger.info("Stopping watcher...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
            
            time.sleep(POLL_INTERVAL)
            
    except Exception as fatal_error:
        # This catches errors during startup (e.g. before the loop)
        logger.critical(f"FATAL ERROR in Agent Watcher: {fatal_error}", exc_info=True)
        # Flush to ensure we see it
        for handler in logger.handlers:
            handler.flush()
        sys.exit(1)

if __name__ == "__main__":
    main()
