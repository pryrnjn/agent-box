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
            AuditLog.stale_pr_detected(repo, pr_number, pr.get('age_hours', 0), unresolved)
            
            issue_number = cls.extract_issue_number(pr.get('body', ''))
            
            if unresolved > 0:
                # Has unresolved comments - need agent to address them
                if issue_number:
                    cls.reassign_for_review(issue_number, repo)
                    AuditLog.review_assigned(repo, issue_number)
            else:
                # All comments resolved
                if review_count < Config.MIN_REVIEW_ROUNDS:
                    # Not enough reviews yet - request another review
                    logger.info(f"PR #{pr_number}: All comments resolved but only {review_count}/{Config.MIN_REVIEW_ROUNDS} reviews. Requesting review.")
                    cls.request_review(pr_number, repo)
                else:
                    # Enough reviews and all resolved - merge!
                    logger.info(f"PR #{pr_number}: All comments resolved with {review_count} reviews. Merging.")
                    if cls.merge_pr(pr_number, repo):
                        AuditLog.pr_merged(repo, pr_number, issue_number)
                        if issue_number:
                            cls.close_issue(issue_number, repo)
                        cls.assign_next_issue(repo)
    
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
            stale_threshold = timedelta(hours=Config.STALE_PR_HOURS)
            
            for pr in prs:
                # Skip PRs that already have agent labels
                pr_labels = {l.get('name', '') for l in pr.get('labels', [])}
                if pr_labels & agent_labels:
                    continue
                
                # Check if linked issue already has review label (avoid reprocessing)
                issue_number = cls.extract_issue_number(pr.get('body', ''))
                if issue_number:
                    issue_labels = cls.get_issue_labels(issue_number, repo)
                    if issue_labels & agent_labels:
                        logger.debug(f"Skipping PR #{pr['number']} - linked issue #{issue_number} already has agent label")
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
                    pr['age_hours'] = age.total_seconds() / 3600
                    stale_prs.append(pr)
                    logger.info(f"PR #{pr['number']} is stale ({pr['age_hours']:.1f}h, {unresolved} unresolved, {review_count} reviews)")
            
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
                '--add-label', Config.REVIEW_LABEL
            ])
            logger.info(f"Applied {Config.REVIEW_LABEL} to issue #{issue_number}")
        except Exception as e:
            logger.error(f"Failed to reassign issue #{issue_number} for review: {e}")
    
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

