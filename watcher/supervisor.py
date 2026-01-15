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
        logger.info(f"Supervising {repo}...")
        
        mature_prs = cls.get_mature_prs(repo)
        
        for pr in mature_prs:
            pr_number = pr['number']
            logger.info(f"Processing mature PR #{pr_number}: {pr['title']}")
            
            # Extract issue number
            issue_number = cls.extract_issue_number(pr.get('body', ''))
            
            # Merge the PR
            if cls.merge_pr(pr_number, repo):
                # Close the issue if found
                if issue_number:
                    cls.close_issue(issue_number, repo)
                
                # Assign next issue
                cls.assign_next_issue(repo)
