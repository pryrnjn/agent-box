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
REVIEW_LABEL = os.getenv('REVIEW_LABEL', 'status:agent-review')
ERROR_LABEL = os.getenv('ERROR_LABEL', 'status:agent-failed')
AGENT_COMMAND_TEMPLATE = os.getenv('AGENT_COMMAND')
AGENT_REVIEW_COMMAND_TEMPLATE = os.getenv('AGENT_REVIEW_COMMAND')
WORK_DIR_BASE = os.getenv('WORK_DIR_BASE', 'workspace')
SELF_UPDATE_INTERVAL = int(os.getenv('SELF_UPDATE_INTERVAL', 3600))

def run_gh_command(args, cwd=None):
    """Run a GitHub CLI command and return output."""
    try:
        # Check if we are running as a user who is authenticated or if we need to sudo
        # But for this script, we assume it's running as the correct user with gh access
        cmd = ['gh'] + args
        result = subprocess.run(
            cmd, 
            cwd=cwd, # Allow running in specific directory (repo)
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
        # Query 1: Review/Feedback items (High Priority)
        # We explicitly search for issues with REVIEW_LABEL assigned to user
        review_query = f"assignee:{GITHUB_USER} is:open label:\"{REVIEW_LABEL}\""
        
        # Query 2: Standard Pending items (Assigned, no status labels)
        pending_query = f"assignee:{GITHUB_USER} is:open -label:\"{WIP_LABEL}\" -label:\"{DONE_LABEL}\" -label:\"{ERROR_LABEL}\" -label:\"{REVIEW_LABEL}\""
        
        all_issues = []
        
        # Fetch Review Issues
        review_out = run_gh_command([
            'issue', 'list', '--repo', GITHUB_REPO, '--search', review_query,
            '--json', 'number,url,title,body,labels', '--limit', '5'
        ])
        review_issues = json.loads(review_out)
        for i in review_issues:
             i['is_review_task'] = True # Mark as review task
        all_issues.extend(review_issues)
        
        # Fetch Pending Issues (only if we need more work?)
        # Let's fetch both to be sure
        pending_out = run_gh_command([
            'issue', 'list', '--repo', GITHUB_REPO, '--search', pending_query,
            '--json', 'number,url,title,body,labels', '--limit', '5'
        ])
        pending_issues = json.loads(pending_out)
        for i in pending_issues:
             i['is_review_task'] = False
        all_issues.extend(pending_issues)
        
        return all_issues
    except Exception as e:
        logger.error(f"Failed to fetch issues: {e}")
        return []

import re

def check_dependencies(issue):
    """Check if all dependencies are resolved."""
    # Review tasks should bypass dependency connection? 
    # Usually yes, if it's in review, deps are likely done or irrelevant for the fix.
    if issue.get('is_review_task', False):
        return True
        
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
    # Example Title: "💾 Phase 1: Implement Working Memory" -> feat/phase1-implement-working-memory
    # Regex Start: Optional non-word chars (emojis) + "Phase" + whitespace + digit
    phase_match = re.search(r'(?:^|[\W_]+)phase\s*(\d+)[:\s-]*', title, re.IGNORECASE)
    
    if phase_match:
        phase_num = phase_match.group(1)
        # Remove the "Phase X" prefix from the safe title to avoid redundancy
        # We want to remove everything up to and including the phase number from the START
        
        # 1. Strip leading non-alphanumeric chars from title to handle emoji
        clean_title_start = re.sub(r'^[^a-zA-Z0-9]+', '', title)
        
        # 2. Remove "phase X" part
        clean_title_raw = re.sub(r'^phase\s*\d+[:\s-]*', '', clean_title_start, flags=re.IGNORECASE)
        
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

# Hardcoded Phase Map from GEMINI.md
PHASE_BRANCH_MAP = {
    '0': 'feat/phase0-foundation',
    '1': 'feat/phase1-memory',
    '2': 'feat/phase2-teacher',
    '3': 'feat/phase3-reward',
    '4': 'feat/phase4-curriculum'
}

def determine_pr_base(issue, current_branch):
    """Determine the target branch for the PR."""
    body = issue.get('body', '')
    
    # 1. explicit override
    match = re.search(r'(?:PR Target|Base):\s*([\w/-]+)', body, re.IGNORECASE)
    if match:
        target = match.group(1).strip()
        logger.info(f"Detected explicit PR target from issue body: {target}")
        return target

    # 2. Phase-based mapping
    # Check if current branch is a feature of a phase (feat/phaseN-...)
    # But NOT the phase branch itself
    phase_match = re.match(r'feat/phase(\d+)-', current_branch)
    if phase_match:
        phase_num = phase_match.group(1)
        base = PHASE_BRANCH_MAP.get(phase_num)
        if base and base != current_branch:
             logger.info(f"Detected Phase {phase_num} work. Setting PR Base to {base}")
             return base

    return PR_BASE_BRANCH

def fetch_pr_context(issue_number, branch_name, repo_dir):
    """Fetch PR comments if a PR exists for this branch."""
    try:
        # Find PR for this branch
        # Run in repo dir to leverage git context if needed, but --repo is safer
        # 'gh pr list --head branch' works globally if --repo is set.
        pr_list_out = run_gh_command(['pr', 'list', '--head', branch_name, '--json', 'number,url,comments,reviews'], cwd=repo_dir)
        pr_list = json.loads(pr_list_out)
        
        if not pr_list:
            return None
            
        pr = pr_list[0]
        context = []
        context.append(f"# Pull Request Context (PR #{pr['number']})")
        context.append(f"URL: {pr['url']}\n")
        
        # Fetch detailed comments/reviews if needed, but summary might be enough if small.
        # Actually 'comments' and 'reviews' in list view can be sparse.
        # Better to 'pr view' 
        
        pr_view_out = run_gh_command(['pr', 'view', str(pr['number']), '--json', 'comments,reviews', '--repo', GITHUB_REPO])
        pr_data = json.loads(pr_view_out)
        
        context.append("## user Reviews & Comments")
        
        # Reviews
        for review in pr_data.get('reviews', []):
            if review['state'] != 'APPROVED': # Focus on feedback
                context.append(f"### Review by {review['author']['login']} ({review['state']})")
                context.append(review['body'])
                context.append("---")
                
        # Comments
        for comment in pr_data.get('comments', []):
            context.append(f"### Comment by {comment['author']['login']}")
            context.append(comment['body'])
            context.append("---")
            
        return "\n".join(context)
        
    except Exception as e:
        logger.error(f"Failed to fetch PR context: {e}")
        return None

def process_issue(issue):
    """Process a single issue."""
    number = issue['number']
    url = issue['url']
    title = issue['title']
    
    logger.info(f"Processing Issue #{number}: {title}")
    
    # 1. Mark as WIP (and remove Review label if present)
    remove_labels = []
    if issue.get('is_review_task'):
        remove_labels.append(REVIEW_LABEL)
        
    update_labels(number, add_labels=[WIP_LABEL], remove_labels=remove_labels)
    
    # 2. Prepare Workspace
    try:
        workspace_dir = prepare_workspace(issue)
        
        # Write issue context
        issue_file = Path(workspace_dir) / "CURRENT_ISSUE.md"
        with open(issue_file, "w") as f:
            f.write(f"# Issue #{number}: {title}\n\n")
            f.write(f"URL: {url}\n\n")
            f.write("## Description\n")
            f.write(issue.get('body', ''))
        
        # Fetch and write PR context (Feedback Loop)
        # We need the branch name again to find the PR
        target_branch = generate_branch_name(number, title)
        pr_context = fetch_pr_context(number, target_branch, workspace_dir)
        
        if pr_context:
            pr_file = Path(workspace_dir) / "PR_CONTEXT.md"
            with open(pr_file, "w") as f:
                f.write(pr_context)
            logger.info(f"Written PR context to {pr_file}")
            has_feedback = True
        elif issue.get('is_review_task'):
            # Fallback for review tasks where PR context couldn't be fetched
            pr_file = Path(workspace_dir) / "PR_CONTEXT.md"
            with open(pr_file, "w") as f:
                f.write("# Pull Request Context\n\nNo automated PR context found. Please assume standard review or check manually.")
            logger.info(f"Written placeholder PR context to {pr_file}")
            has_feedback = True
            
        logger.info(f"Written issue context to {issue_file}")
        
    except Exception as e:
        logger.error(f"Failed to prepare workspace: {e}")
        update_labels(number, add_labels=[ERROR_LABEL], remove_labels=[WIP_LABEL])
        return

    # Dynamic Instruction Injection
    # If it's a review task AND we have a specific review command, use it.
    # Otherwise, append the instruction to the standard command.
    if issue.get('is_review_task') and AGENT_REVIEW_COMMAND_TEMPLATE:
        cmd_str = AGENT_REVIEW_COMMAND_TEMPLATE.format(
            issue_url=url,
            issue_number=number,
            workspace_dir=workspace_dir
        )
        logger.info(f"Using Dedicated Review Command for #{number}")
    else:
        # Fallback / Standard behavior
        cmd_str = AGENT_COMMAND_TEMPLATE.format(
            issue_url=url,
            issue_number=number,
            workspace_dir=workspace_dir
        )
        if has_feedback:
            cmd_str += ' "IMPORTANT: Address review comments in @PR_CONTEXT.md"'
    
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
                pr_base = determine_pr_base(issue, current_branch)
                
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
        REVIEW_LABEL: {'color': 'BFD4F2', 'description': 'User requested agent changes/review'},
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

def check_self_update():
    """Check for updates to the agent watcher itself."""
    try:
        # Check if we are in a git repo
        if not os.path.isdir('.git'):
            return
            
        logger.debug("Checking for self-updates...")
        subprocess.run(['git', 'fetch', 'origin'], check=True, capture_output=True)
        
        # Check if behind
        status = subprocess.run(['git', 'status', '-uno'], capture_output=True, text=True)
        if "Your branch is behind" in status.stdout:
            logger.info("New version detected! Updating...")
            subprocess.run(['git', 'pull'], check=True)
            
            logger.info("Update complete. Restarting service in 5 seconds...")
            time.sleep(5)
            sys.exit(0) # Systemd will restart us
            
    except Exception as e:
        logger.error(f"Self-update check failed: {e}")

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
        
        loop_count = 0
        while True:
            try:
                loop_count += 1
                
                # Check for self-update based on configured interval
                # Calculate loops needed: interval / poll_interval
                loops_per_update = max(1, int(SELF_UPDATE_INTERVAL / POLL_INTERVAL))
                
                if loop_count % loops_per_update == 0:
                    check_self_update()
                    
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
