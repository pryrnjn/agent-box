import logging
import time
import subprocess
import json
import re
from pathlib import Path
from .config import Config
from .github import GitHub
from .git import Git
from .models import Issue, TaskContext

logger = logging.getLogger(__name__)

class Workflow:
    @staticmethod
    def run_agent_command(context: TaskContext) -> tuple[int, str]:
        """Run the agent command."""
        # Select Command
        if context.is_review_task and Config.AGENT_REVIEW_COMMAND_TEMPLATE:
             cmd_template = Config.AGENT_REVIEW_COMMAND_TEMPLATE
        else:
             cmd_template = Config.AGENT_COMMAND_TEMPLATE
             
        # Inject Instructions
        instruction = ""
        if context.pr_context and not (context.is_review_task and Config.AGENT_REVIEW_COMMAND_TEMPLATE):
             # Only append to standard command if we aren't using a dedicated review command
             instruction = ' "IMPORTANT: Address review comments in PR_CONTEXT.md"'
             
        # Format Command
        cmd_str = cmd_template.format(
            issue_url=context.issue_url,
            issue_number=context.issue_number,
            workspace_dir=context.workspace_dir
        ) + instruction + Config.GIT_COMMIT_INSTRUCTION
        
        logger.info(f"Executing Agent Command: {cmd_str}")
        
        start_time = time.time()
        process = subprocess.Popen(
            cmd_str, 
            shell=True, 
            cwd=context.workspace_dir, 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        output_buffer = []
        for line in iter(process.stdout.readline, ''):
            if line:
                logger.info(f"[AGENT] {line.strip()}")
                output_buffer.append(line)
                
        process.wait()
        duration = time.time() - start_time
        logger.info(f"Agent finished in {duration:.2f}s with return code {process.returncode}")
        
        return process.returncode, "".join(output_buffer)

    @staticmethod
    def extract_commit_message(agent_output: str, issue_number: int) -> str:
        """Extract a meaningful commit message from agent output."""
        # Try to find a summary section
        summary_match = re.search(r'(?:Here is a )?summary of the changes:?\s*(.*)', agent_output, re.IGNORECASE | re.DOTALL)
        if summary_match:
            summary_text = summary_match.group(1).strip()
            # Clean up the summary (take mainly bullet points or first few lines)
            lines = [line.strip() for line in summary_text.splitlines() if line.strip()]
            
            # Take lines that look like bullet points or reasonable text, stop at next major header or long gap
            commit_body = []
            for line in lines:
                if re.match(r'^[-*•]', line) or len(commit_body) < 10: # limit length
                    if "Agent finished" in line: break # Stop at footer logs
                    commit_body.append(line)
            
            if commit_body:
                return f"Agent: Fixes #{issue_number}\n\n" + "\n".join(commit_body)

        return f"Agent: Implemented changes for #{issue_number}"

    @classmethod
    def execute_task(cls, issue: Issue):
        """Execute the full workflow for a task."""
        logger.info(f"Processing Issue #{issue.number}: {issue.title} in {issue.repo}")
        
        # 1. Label as WIP
        remove_labels = [Config.REVIEW_LABEL] if issue.is_review_task else []
        GitHub.update_labels(issue.number, issue.repo, add_labels=[Config.WIP_LABEL], remove_labels=remove_labels)
        
        try:
            # 2. Prepare Workspace
            context = Git.prepare_workspace(issue)
            
            # Write Artifacts
            issue_file = Path(context.workspace_dir) / "CURRENT_ISSUE.md"
            with open(issue_file, "w") as f:
                f.write(f"# Issue #{context.issue_number}: {context.issue_title}\n\n")
                f.write(f"URL: {context.issue_url}\n\n")
                f.write("## Description\n")
                f.write(context.issue_body)
                
            if context.pr_context:
                pr_file = Path(context.workspace_dir) / "PR_CONTEXT.md"
                with open(pr_file, "w") as f:
                    f.write(context.pr_context)
            
            # 3. Execution Loop (Implement -> Verify)
            # For now, we keep it simple (Single Pass) as per request to just modularize existing logic first.
            # The "Execute -> Verify" loop can be expanded here later.
            return_code, agent_output = cls.run_agent_command(context)
            
            if return_code == 0:
                # 4. Finalization (Push & PR)
                if cls.finalize_task(context, agent_output):
                    GitHub.update_labels(issue.number, issue.repo, add_labels=[Config.DONE_LABEL], remove_labels=[Config.WIP_LABEL])
                else:
                    GitHub.update_labels(issue.number, issue.repo, add_labels=[Config.ERROR_LABEL], remove_labels=[Config.WIP_LABEL])

            else:
                GitHub.update_labels(issue.number, issue.repo, add_labels=[Config.ERROR_LABEL], remove_labels=[Config.WIP_LABEL])
                
        except Exception as e:
            logger.error(f"Workflow failed for #{issue.number}: {e}")
            GitHub.update_labels(issue.number, issue.repo, add_labels=[Config.ERROR_LABEL], remove_labels=[Config.WIP_LABEL])

    @staticmethod
    def determine_pr_base(issue_number, issue_body, current_branch):
        """Determine the PR base branch."""
        # 1. Explicit override
        match = re.search(r'(?:PR Target|Base):\s*([\w/-]+)', issue_body, re.IGNORECASE)
        if match:
            return match.group(1).strip()
            
        # 2. Phase Mapping
        phase_map = Config.PHASE_MAP
        phase_match = re.match(r'feat/phase(\d+)-', current_branch)
        if phase_match:
            phase_num = phase_match.group(1)
            base = phase_map.get(phase_num)
            if base and base != current_branch:
                 return base

        return Config.PR_BASE_BRANCH

    @classmethod
    def finalize_task(cls, context: TaskContext, agent_output: str = "") -> bool:
        """Push changes and create/update PR."""
        try:
            cwd = context.workspace_dir
            # Get Current Branch
            branch_proc = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=cwd, capture_output=True, text=True, check=True)
            current_branch = branch_proc.stdout.strip()
            
            pr_base = cls.determine_pr_base(context.issue_number, context.issue_body, current_branch)
            
            if current_branch == pr_base:
                logger.warning("Current branch IS base branch. Skipping PR.")
                return True
            if current_branch in ['main', 'master', 'develop']:
                logger.warning("Protected branch detected. Skipping PR.")
                return True
            
            # Commit Changes
            commit_msg = cls.extract_commit_message(agent_output, context.issue_number)
            Git.commit_all_changes(cwd, commit_msg)
                
            logger.info(f"Pushing branch {current_branch}...")
            Git.run_git(['push', '-u', 'origin', current_branch], cwd=cwd)
            
            # Create PR
            # Check existence
            existing_prs = json.loads(GitHub.run_gh_command(['pr', 'list', '--head', current_branch, '--json', 'url']))
            
            if existing_prs:
                logger.info(f"PR already exists: {existing_prs[0]['url']}")
                pr_url = existing_prs[0]['url']
            else:
                logger.info(f"Creating PR into {pr_base}...")
                pr_body = f"Agent completed work for #{context.issue_number}. Closes #{context.issue_number}.\n\n/gemini review"
                
                try:
                    pr_out = GitHub.run_gh_command([
                        'pr', 'create',
                        '--title', f"{context.issue_title} (Agent)",
                        '--body', pr_body,
                        '--head', current_branch,
                        '--base', pr_base,
                        '--repo', context.repo
                    ])
                    pr_url = pr_out.strip()
                    logger.info(f"PR Created: {pr_url}")
                except Exception as e:
                    # Fallback check if creation failed because it exists (race condition or weird gh behavior)
                    logger.warning(f"PR creation failed: {e}. Checking if it actually exists now...")
                    existing_prs_retry = json.loads(GitHub.run_gh_command(['pr', 'list', '--head', current_branch, '--json', 'url']))
                    if existing_prs_retry:
                        pr_url = existing_prs_retry[0]['url']
                        logger.info(f"PR found on retry: {pr_url}")
                    else:
                        raise e

            # Resolve Threads (Code-based)
            if context.is_review_task and context.unresolved_thread_ids:
                logger.info(f"Resolving {len(context.unresolved_thread_ids)} review threads...")
                for thread_id in context.unresolved_thread_ids:
                    GitHub.resolve_thread(thread_id)

            if pr_url:
                GitHub.run_gh_command([
                    'issue', 'comment', str(context.issue_number),
                    '--repo', context.repo,
                    '--body', f"🚀 Agent finished! created/updated PR: {pr_url}"
                ])
                
            return True
            
        except Exception as e:
            logger.error(f"Finalization failed: {e}")
            return False
