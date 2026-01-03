import logging
import subprocess
import os
import re
from pathlib import Path
from .config import Config
from .github import GitHub
from .models import Issue, TaskContext

logger = logging.getLogger(__name__)

class Git:
    @staticmethod
    def run_git(args, cwd):
        """Run a git command in the specified directory."""
        subprocess.run(['git'] + args, cwd=cwd, check=True)

    @classmethod
    def generate_branch_name(cls, number: int, title: str) -> str:
        """Generate a branch name based on conventions."""
        safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', title.lower()).strip('-')
        safe_title = re.sub(r'-+', '-', safe_title)
        
        # Check for Phase match
        phase_match = re.search(r'(?:^|[\W_]+)phase\s*(\d+)[:\s-]*', title, re.IGNORECASE)
        if phase_match:
            phase_num = phase_match.group(1)
            clean_title_start = re.sub(r'^[^a-zA-Z0-9]+', '', title)
            clean_title_raw = re.sub(r'^phase\s*\d+[:\s-]*', '', clean_title_start, flags=re.IGNORECASE)
            clean_safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', clean_title_raw.lower()).strip('-')
            clean_safe_title = re.sub(r'-+', '-', clean_safe_title)
            return f"feat/phase{phase_num}-{clean_safe_title}"

        return Config.BRANCH_NAME_TEMPLATE.format(
            number=number,
            title=safe_title,
            safe_title=safe_title
        )

    @classmethod
    def parse_branch_directive(cls, issue_body: str) -> str:
        if not issue_body:
            return None
        match = re.search(r'Branch:\s*([\w/-]+)', issue_body, re.IGNORECASE)
        if match:
             return match.group(1).strip()
        return None

    @classmethod
    def resolve_target_branch(cls, issue: Issue) -> str:
        """Resolve the target branch based on priority."""
        # 1. Active PR
        active_branch = GitHub.find_active_branch(issue.number)
        if active_branch:
             logger.info(f"Using existing active branch: {active_branch}")
             return active_branch
             
        # 2. Directive
        explicit_branch = cls.parse_branch_directive(issue.body)
        if explicit_branch:
             logger.info(f"Using explicit branch from body: {explicit_branch}")
             return explicit_branch
             
        # 3. Generated
        target_branch = cls.generate_branch_name(issue.number, issue.title)
        
        if issue.is_review_task:
            logger.warning(f"Review task check: No active PR/Branch found for #{issue.number}. Falling back to generated branch: {target_branch}")
        else:
            logger.info(f"No active PR or directive found. Generated Target Branch: {target_branch}")
            
        return target_branch

    @classmethod
    def prepare_workspace(cls, issue: Issue) -> TaskContext:
        """Prepare the workspace and return the task context."""
        base_path = Path(Config.WORK_DIR_BASE)
        if not base_path.is_absolute():
            base_path = Path(os.getcwd()) / base_path
        
        base_path.mkdir(exist_ok=True)
        repo_name = Config.GITHUB_REPO.split('/')[-1]
        repo_path = base_path / repo_name
        
        if not repo_path.exists():
            logger.info(f"Cloning {Config.GITHUB_REPO}...")
            subprocess.run(['gh', 'repo', 'clone', Config.GITHUB_REPO, str(repo_path)], check=True)
            
        logger.info(f"Preparing git repo at {repo_path}...")
        cls.run_git(['fetch', '--all'], cwd=repo_path)
        
        target_branch = cls.resolve_target_branch(issue)
        
        # Check Remote
        remote_exists = False
        ls_remote = subprocess.run(
            ['git', 'ls-remote', '--heads', 'origin', target_branch],
            cwd=repo_path, capture_output=True, text=True
        )
        if target_branch in ls_remote.stdout:
            remote_exists = True
            
        if remote_exists:
            logger.info(f"Branch {target_branch} exists on remote. Checking out...")
            cls.run_git(['checkout', target_branch], cwd=repo_path)
            cls.run_git(['pull', 'origin', target_branch], cwd=repo_path)
        else:
             logger.info(f"Checking for local branch {target_branch}...")
             try:
                 cls.run_git(['checkout', target_branch], cwd=repo_path)
                 logger.info("Switched to existing local branch.")
             except subprocess.CalledProcessError:
                 logger.info(f"Creating new branch {target_branch} from main...")
                 cls.run_git(['checkout', 'main'], cwd=repo_path)
                 cls.run_git(['pull', 'origin', 'main'], cwd=repo_path)
                 cls.run_git(['checkout', '-b', target_branch], cwd=repo_path)
        
        # Build Context
        context = TaskContext(
            issue_number=issue.number,
            issue_title=issue.title,
            issue_body=issue.body or "",
            issue_url=issue.url,
            is_review_task=issue.is_review_task,
            target_branch=target_branch,
            workspace_dir=str(repo_path)
        )
        
        # Add PR Context if exists
        pr_context = GitHub.fetch_pr_context(issue.number, target_branch, context.workspace_dir)
        if pr_context:
            context.pr_context = pr_context
        elif issue.is_review_task:
             context.pr_context = "# Pull Request Context\n\nNo automated PR context found. Please assume standard review or check manually."
             
        return context
