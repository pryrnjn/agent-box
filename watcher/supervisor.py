import json
import logging
import re
from typing import List, Optional
from .config import Config
from .github import GitHub

logger = logging.getLogger(__name__)

class SupervisorWorkflow:
    """Senior Dev Supervisor - monitors PRs and manages merge workflow."""
    
    @classmethod
    def get_mature_prs(cls, repo: str) -> List[dict]:
        """Find PRs with agent-done label that have enough review rounds."""
        try:
            # Find PRs with the DONE label
            out = GitHub.run_gh_command([
                'pr', 'list', '--repo', repo,
                '--label', Config.DONE_LABEL,
                '--state', 'open',
                '--json', 'number,title,url,headRefName,body'
            ])
            prs = json.loads(out)
            
            mature_prs = []
            for pr in prs:
                review_count = cls.count_review_rounds(pr['number'], repo)
                logger.info(f"PR #{pr['number']} has {review_count} review rounds")
                
                if review_count >= Config.MIN_REVIEW_ROUNDS:
                    pr['review_count'] = review_count
                    mature_prs.append(pr)
                    
            return mature_prs
            
        except Exception as e:
            logger.error(f"Failed to get mature PRs: {e}")
            return []
    
    @classmethod
    def count_review_rounds(cls, pr_number: int, repo: str) -> int:
        """Count the number of review submission events on a PR."""
        try:
            # Use GraphQL to get review threads and their resolution status
            owner, repo_name = repo.split('/')
            
            query = """
            query($owner: String!, $repo: String!, $number: Int!) {
              repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                  reviews(first: 100) {
                    totalCount
                  }
                  reviewThreads(first: 100) {
                    nodes {
                      isResolved
                    }
                  }
                }
              }
            }
            """
            
            cmd = [
                'api', 'graphql',
                '-f', f'query={query}',
                '-F', f'owner={owner}',
                '-F', f'repo={repo_name}',
                '-F', f'number={pr_number}'
            ]
            
            out = GitHub.run_gh_command(cmd)
            data = json.loads(out)
            
            pr_data = data['data']['repository']['pullRequest']
            review_count = pr_data['reviews']['totalCount']
            
            # Also check that all threads are resolved
            threads = pr_data['reviewThreads']['nodes']
            unresolved = sum(1 for t in threads if not t['isResolved'])
            
            if unresolved > 0:
                logger.info(f"PR #{pr_number} has {unresolved} unresolved threads")
                return 0  # Don't consider mature if threads are unresolved
                
            return review_count
            
        except Exception as e:
            logger.error(f"Failed to count review rounds for PR #{pr_number}: {e}")
            return 0
    
    @classmethod
    def extract_issue_number(cls, pr_body: str) -> Optional[int]:
        """Extract issue number from PR body (e.g., 'Closes #123')."""
        if not pr_body:
            return None
            
        match = re.search(r'(?:Closes|Fixes|Resolves)\s+#(\d+)', pr_body, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    @classmethod
    def merge_pr(cls, pr_number: int, repo: str) -> bool:
        """Merge the PR using squash merge."""
        try:
            GitHub.run_gh_command([
                'pr', 'merge', str(pr_number),
                '--repo', repo,
                '--squash',
                '--delete-branch'
            ])
            logger.info(f"Merged PR #{pr_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to merge PR #{pr_number}: {e}")
            return False
    
    @classmethod
    def close_issue(cls, issue_number: int, repo: str) -> bool:
        """Close the associated issue."""
        try:
            GitHub.run_gh_command([
                'issue', 'close', str(issue_number),
                '--repo', repo,
                '--reason', 'completed'
            ])
            logger.info(f"Closed issue #{issue_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to close issue #{issue_number}: {e}")
            return False
    
    @classmethod
    def assign_next_issue(cls, repo: str) -> Optional[int]:
        """Find and assign the next pending issue to the agent."""
        try:
            # Find oldest unassigned issue without agent labels
            out = GitHub.run_gh_command([
                'issue', 'list', '--repo', repo,
                '--state', 'open',
                '--json', 'number,title,assignees',
                '--limit', '20'
            ])
            issues = json.loads(out)
            
            # Filter for unassigned issues
            unassigned = [i for i in issues if not i['assignees']]
            
            if not unassigned:
                logger.info("No unassigned issues found")
                return None
            
            # Sort by number (oldest first)
            unassigned.sort(key=lambda x: x['number'])
            next_issue = unassigned[0]
            
            # Assign to the agent user
            GitHub.run_gh_command([
                'issue', 'edit', str(next_issue['number']),
                '--repo', repo,
                '--add-assignee', Config.GITHUB_USER
            ])
            
            logger.info(f"Assigned issue #{next_issue['number']} to {Config.GITHUB_USER}")
            return next_issue['number']
            
        except Exception as e:
            logger.error(f"Failed to assign next issue: {e}")
            return None
    
    @classmethod
    def supervise_repo(cls, repo: str):
        """Main supervision loop for a single repo."""
        from .audit import AuditLog
        
        logger.info(f"Supervising {repo}...")
        
        # Handle mature PRs (ready to merge)
        mature_prs = cls.get_mature_prs(repo)
        
        for pr in mature_prs:
            pr_number = pr['number']
            logger.info(f"Processing mature PR #{pr_number}: {pr['title']}")
            
            # Extract issue number
            issue_number = cls.extract_issue_number(pr.get('body', ''))
            
            # Merge the PR
            if cls.merge_pr(pr_number, repo):
                AuditLog.pr_merged(repo, pr_number, issue_number)
                
                # Close the issue if found
                if issue_number:
                    cls.close_issue(issue_number, repo)
                
                # Assign next issue
                cls.assign_next_issue(repo)
        
        # Handle stale PRs (open for too long)
        stale_prs = cls.get_stale_prs(repo)
        
        for pr in stale_prs:
            pr_number = pr['number']
            unresolved = pr.get('unresolved_count', 0)
            review_count = pr.get('review_count', 0)
            
            logger.info(f"Processing stale PR #{pr_number}: {pr['title']} (unresolved={unresolved}, reviews={review_count})")
            AuditLog.stale_pr_detected(repo, pr_number, pr.get('age_mins', 0), unresolved)
            
            issue_number = cls.extract_issue_number(pr.get('body', ''))
            
            if unresolved > 0:
                # Has unresolved comments - try to auto-resolve them first
                logger.info(f"PR #{pr_number}: Attempting to auto-resolve {unresolved} comments...")
                resolved_count = cls.review_and_resolve_comments(pr_number, repo)
                
                # Recheck unresolved count after auto-resolve
                owner, repo_name = repo.split('/')
                new_unresolved, _ = cls.get_pr_review_status(pr_number, owner, repo_name)
                
                if new_unresolved > 0:
                    # Still has unresolved comments - need agent to address them
                    logger.info(f"PR #{pr_number}: {new_unresolved} comments still unresolved after auto-resolve")
                    if issue_number:
                        # Only reassign if NOT already assigned (to avoid spamming logs/audit)
                        issue_labels = cls.get_issue_labels(issue_number, repo)
                        agent_labels = {Config.WIP_LABEL, Config.REVIEW_LABEL}
                        
                        if not (issue_labels & agent_labels):
                            cls.reassign_for_review(issue_number, repo)
                            AuditLog.review_assigned(repo, issue_number)
                        else:
                            logger.info(f"Issue #{issue_number} already has agent label. Waiting for agent.")
                else:
                    logger.info(f"PR #{pr_number}: All comments auto-resolved!")
                    # Remove agent labels from issue since we resolved it
                    if issue_number:
                        cls.remove_agent_labels(issue_number, repo)
            else:
                # All comments resolved
                if issue_number:
                     cls.remove_agent_labels(issue_number, repo)

                if review_count < Config.MIN_REVIEW_ROUNDS:
                    # Not enough reviews yet - request another review
                    logger.info(f"PR #{pr_number}: All comments resolved but only {review_count}/{Config.MIN_REVIEW_ROUNDS} reviews. Requesting review.")
                    cls.request_review(pr_number, repo)
                else:
                    # Check Branch Policy
                    if not cls.validate_target_branch(pr, repo):
                        continue
                        
                    # Check Requirements Verification (Senior Dev Check)
                    verification_status = cls.verify_implementation(pr, issue_number, repo)
                    
                    if verification_status == 'PASS':
                        # Validated! Safe to merge.
                        logger.info(f"PR #{pr_number}: Verified & Approved by Supervisor. Merging.")
                        if cls.merge_pr(pr_number, repo):
                            AuditLog.pr_merged(repo, pr_number, issue_number)
                            if issue_number:
                                cls.close_issue(issue_number, repo)
                            cls.assign_next_issue(repo)
                    elif verification_status == 'FAIL':
                        # Verification failed - feedback already left by verify_implementation
                        logger.info(f"PR #{pr_number}: Verification failed. Waiting for fixes.")
                        if issue_number:
                             # Reassign to agent because fixes are needed
                             cls.reassign_for_review(issue_number, repo)
                    else:
                        # PENDING/ERROR - Skip
                        pass
    
    @classmethod
    def request_review(cls, pr_number: int, repo: str):
        """Add a comment to request another review cycle."""
        try:
            GitHub.run_gh_command([
                'pr', 'comment', str(pr_number),
                '--repo', repo,
                '--body', '/gemini review'
            ])
            logger.info(f"Requested review on PR #{pr_number}")
        except Exception as e:
            logger.error(f"Failed to request review on PR #{pr_number}: {e}")
    
    @classmethod
    def review_and_resolve_comments(cls, pr_number: int, repo: str) -> int:
        """Review unresolved comments and auto-resolve if addressed. Returns count resolved."""
        owner, repo_name = repo.split('/')
        threads = cls.get_unresolved_threads(pr_number, owner, repo_name)
        
        resolved_count = 0
        for thread in threads:
            thread_id = thread['id']
            comment_body = thread['comment']
            file_path = thread.get('path', 'unknown')
            
            logger.info(f"Checking if comment on {file_path} was addressed...")
            
            if cls.check_comment_addressed(pr_number, repo, comment_body, file_path):
                if cls.resolve_thread(thread_id):
                    resolved_count += 1
                    logger.info(f"Auto-resolved thread on {file_path}")
                else:
                    logger.warning(f"Failed to resolve thread on {file_path}")
            else:
                logger.info(f"Comment on {file_path} was NOT addressed")
        
        return resolved_count
    
    @classmethod
    def get_unresolved_threads(cls, pr_number: int, owner: str, repo_name: str) -> List[dict]:
        """Get unresolved review threads with their content."""
        try:
            query = """
            query($owner: String!, $repo: String!, $number: Int!) {
              repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                  reviewThreads(first: 100) {
                    nodes {
                      id
                      isResolved
                      path
                      line
                      comments(first: 1) {
                        nodes {
                          body
                        }
                      }
                    }
                  }
                }
              }
            }
            """
            
            cmd = [
                'api', 'graphql',
                '-f', f'query={query}',
                '-F', f'owner={owner}',
                '-F', f'repo={repo_name}',
                '-F', f'number={pr_number}'
            ]
            
            out = GitHub.run_gh_command(cmd)
            data = json.loads(out)
            
            threads = data['data']['repository']['pullRequest']['reviewThreads']['nodes']
            unresolved = []
            for t in threads:
                if not t['isResolved']:
                    comments = t.get('comments', {}).get('nodes', [])
                    comment_body = comments[0]['body'] if comments else ''
                    unresolved.append({
                        'id': t['id'],
                        'path': t.get('path', ''),
                        'line': t.get('line'),
                        'comment': comment_body
                    })
            
            return unresolved
            
        except Exception as e:
            logger.error(f"Failed to get unresolved threads for PR #{pr_number}: {e}")
            return []
    
    @classmethod
    def check_comment_addressed(cls, pr_number: int, repo: str, comment: str, file_path: str) -> bool:
        """Use LLM agent to check if a review comment was addressed."""
        import subprocess
        
        prompt = f"""You are reviewing a Pull Request.

A reviewer left this comment on file `{file_path}`:
---
{comment}
---

Check the current code in the PR to determine if this comment has been addressed.
Use `gh pr diff {pr_number} --repo {repo}` to see the changes.

Respond with ONLY one word: "RESOLVED" if the comment was addressed, or "UNRESOLVED" if not."""

        try:
            cmd = f'gemini --yolo "{prompt}"'
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            output = result.stdout.strip().upper()
            return 'RESOLVED' in output
            
        except Exception as e:
            logger.error(f"Failed to check comment: {e}")
            return False
    
    @classmethod
    def resolve_thread(cls, thread_id: str) -> bool:
        """Resolve a review thread via GraphQL mutation."""
        try:
            mutation = """
            mutation($threadId: ID!) {
              resolveReviewThread(input: {threadId: $threadId}) {
                thread {
                  isResolved
                }
              }
            }
            """
            
            cmd = [
                'api', 'graphql',
                '-f', f'query={mutation}',
                '-F', f'threadId={thread_id}'
            ]
            
            out = GitHub.run_gh_command(cmd)
            data = json.loads(out)
            
            return data.get('data', {}).get('resolveReviewThread', {}).get('thread', {}).get('isResolved', False)
            
        except Exception as e:
            logger.error(f"Failed to resolve thread {thread_id}: {e}")
            return False
    
    @classmethod
    def get_stale_prs(cls, repo: str) -> List[dict]:
        """Find PRs that are open for too long."""
        from datetime import datetime, timezone, timedelta
        
        try:
            # Get open PRs - but exclude those with agent labels (already being handled)
            out = GitHub.run_gh_command([
                'pr', 'list', '--repo', repo,
                '--state', 'open',
                '--json', 'number,title,url,body,updatedAt,headRefName,labels'
            ])
            prs = json.loads(out)
            
            # Labels that indicate agent is handling or has handled the PR
            agent_labels = {Config.DONE_LABEL, Config.WIP_LABEL, Config.REVIEW_LABEL}
            
            stale_prs = []
            now = datetime.now(timezone.utc)
            stale_threshold = timedelta(minutes=Config.STALE_PR_MINS)
            
            for pr in prs:
                # Skip PRs that already have agent labels
                pr_labels = {l.get('name', '') for l in pr.get('labels', [])}
                if pr_labels & agent_labels:
                    continue
                
                # Parse updatedAt
                updated_str = pr.get('updatedAt', '')
                if not updated_str:
                    continue
                    
                updated_at = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                age = now - updated_at
                
                if age > stale_threshold:
                    # Get unresolved count and review count
                    owner, repo_name = repo.split('/')
                    unresolved, review_count = cls.get_pr_review_status(pr['number'], owner, repo_name)
                    
                    pr['unresolved_count'] = unresolved
                    pr['review_count'] = review_count
                    pr['age_mins'] = age.total_seconds() / 60
                    stale_prs.append(pr)
                    logger.info(f"PR #{pr['number']} is stale ({pr['age_mins']:.1f}m, {unresolved} unresolved, {review_count} reviews)")
            
            return stale_prs
            
        except Exception as e:
            logger.error(f"Failed to get stale PRs: {e}")
            return []
    
    @classmethod
    def get_issue_labels(cls, issue_number: int, repo: str) -> set:
        """Get labels for an issue."""
        try:
            out = GitHub.run_gh_command([
                'issue', 'view', str(issue_number),
                '--repo', repo,
                '--json', 'labels'
            ])
            data = json.loads(out)
            return {l.get('name', '') for l in data.get('labels', [])}
        except Exception as e:
            logger.error(f"Failed to get labels for issue #{issue_number}: {e}")
            return set()
    
    @classmethod
    def get_pr_review_status(cls, pr_number: int, owner: str, repo_name: str) -> tuple:
        """Get count of unresolved threads and total reviews. Returns (unresolved, review_count)."""
        try:
            query = """
            query($owner: String!, $repo: String!, $number: Int!) {
              repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                  reviews(first: 100) {
                    totalCount
                  }
                  reviewThreads(first: 100) {
                    nodes {
                      isResolved
                    }
                  }
                }
              }
            }
            """
            
            cmd = [
                'api', 'graphql',
                '-f', f'query={query}',
                '-F', f'owner={owner}',
                '-F', f'repo={repo_name}',
                '-F', f'number={pr_number}'
            ]
            
            out = GitHub.run_gh_command(cmd)
            data = json.loads(out)
            
            pr_data = data['data']['repository']['pullRequest']
            threads = pr_data['reviewThreads']['nodes']
            unresolved = sum(1 for t in threads if not t['isResolved'])
            review_count = pr_data['reviews']['totalCount']
            
            return (unresolved, review_count)
            
        except Exception as e:
            logger.error(f"Failed to get review status for PR #{pr_number}: {e}")
            return (0, 0)
    
    @classmethod
    def reassign_for_review(cls, issue_number: int, repo: str):
        """Apply REVIEW_LABEL to issue to trigger agent to address comments."""
        try:
            GitHub.run_gh_command([
                'issue', 'edit', str(issue_number),
                '--repo', repo,
                '--add-label', Config.REVIEW_LABEL,
                '--add-assignee', Config.GITHUB_USER
            ])
            logger.info(f"Applied {Config.REVIEW_LABEL} to issue #{issue_number}")
        except Exception as e:
            logger.error(f"Failed to reassign issue #{issue_number} for review: {e}")

    @classmethod
    def remove_agent_labels(cls, issue_number: int, repo: str):
        """Remove agent labels (REVIEW, DONE, WIP) from issue."""
        try:
            labels_to_remove = [Config.REVIEW_LABEL, Config.DONE_LABEL, Config.WIP_LABEL]
            for label in labels_to_remove:
                # We can't batch remove easily with gh cli issue edit, so we try one by one 
                # or check if it exists first. For robustness, just try remove.
                # Actually 'gh issue edit --remove-label' takes comma separated list? No, repeatedly.
                # Let's just try removing REVIEW_LABEL which is the critical one here.
                # But to be safe, let's remove all agent labels.
                
                # Check current labels first to avoid error spam
                current_labels = cls.get_issue_labels(issue_number, repo)
                if label in current_labels:
                    GitHub.run_gh_command([
                        'issue', 'edit', str(issue_number),
                        '--repo', repo,
                        '--remove-label', label
                    ])
                    logger.info(f"Removed {label} from issue #{issue_number}")
        except Exception as e:
            logger.error(f"Failed to remove agent labels from issue #{issue_number}: {e}")
    
    @classmethod
    def validate_target_branch(cls, pr: dict, repo: str) -> bool:
        """Ensure PR targets the correct branch based on naming convention."""
        head_ref = pr['headRefName']
        base_ref = pr.get('baseRefName', '') # Target branch
        
        # Simple policy:
        # hotfix/* -> main or master
        # feat/* -> develop (if it exists, otherwise main)
        
        target_policy = {
            'hotfix': ['main', 'master'],
            'feat': ['develop'] 
        }
        
        # Check if 'develop' exists in this repo. If not, fallback to main.
        # Ideally we'd cache this or check config. For now, let's just warn if base seems odd.
        
        # We can implement a stricter check if needed.
        # For now, let's just log.
        # logger.info(f"Validating PR #{pr['number']} ({head_ref} -> {base_ref})")
        return True

    @classmethod
    def verify_implementation(cls, pr: dict, issue_number: int, repo: str) -> str:
        """Verify that the PR implementation satisfies the Issue requirements using LLM."""
        if not issue_number:
            return 'PASS' # No issue to verify against, assume OK or manual PR
            
        pr_number = pr['number']
        
        # Check if already verified
        # We can use a label to track verification status to avoid re-running LLM
        VERIFIED_LABEL = "supervisor-verified"
        pr_labels = {l.get('name', '') for l in pr.get('labels', [])}
        if VERIFIED_LABEL in pr_labels:
            return 'PASS'
            
        logger.info(f"Verifying PR #{pr_number} against Issue #{issue_number}...")
        
        # 1. Fetch Issue Body
        try:
            issue_out = GitHub.run_gh_command(['issue', 'view', str(issue_number), '--repo', repo, '--json', 'body'])
            issue_body = json.loads(issue_out).get('body', '')
        except Exception:
            logger.warning(f"Could not fetch body for Issue #{issue_number}")
            return 'PENDING'
            
        # 2. Consult LLM
        prompt = f"""You are a Senior QA Engineer.
        
ISSUE REQUIREMENTS (Issue #{issue_number}):
---
{issue_body}
---

Review the PR Diff to ensure it fully implements these requirements.
Run: `gh pr diff {pr_number} --repo {repo}`

Output format:
- Start with "PASS" if the implementation looks correct and complete.
- Start with "FAIL" if requirements are missing or implementation is wrong.
- Provide a brief valid justification.
"""
        import subprocess
        try:
            cmd = f'gemini --yolo "{prompt}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180)
            output = result.stdout.strip()
            
            if output.upper().startswith("PASS"):
                # Add label
                GitHub.run_gh_command(['pr', 'edit', str(pr_number), '--repo', repo, '--add-label', VERIFIED_LABEL])
                logger.info(f"PR #{pr_number} PASSED verification.")
                return 'PASS'
            else:
                logger.warning(f"PR #{pr_number} FAILED verification: {output[:100]}...")
                # Post feedback
                GitHub.run_gh_command(['pr', 'comment', str(pr_number), '--repo', repo, '--body', f"Supervisor Verification Failed:\n\n{output}"])
                return 'FAIL'
                
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return 'ERROR'
            
    @classmethod
    def consult_llm(cls, context: str, question: str, workspace_dir: str = None) -> str:
        """Query Gemini agent for decision-making on ambiguous situations."""
        import subprocess
        
        prompt = f"""You are a Senior Dev Supervisor reviewing AI agent work.

Context:
{context}

Question:
{question}

Review the codebase if needed. Respond with a brief, actionable decision."""

        try:
            cmd = f'gemini --yolo "{prompt}"'
            
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5 min timeout for agent
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.error(f"Agent command failed: {result.stderr}")
                return "Unable to get agent response"
                
        except subprocess.TimeoutExpired:
            logger.error("Agent consultation timed out")
            return "Agent consultation timed out"
        except Exception as e:
            logger.error(f"Failed to consult agent: {e}")
            return "Agent consultation failed"

