import json
import logging
import subprocess
import re
from typing import List, Optional
from .config import Config
from .models import Issue, PRContext

logger = logging.getLogger(__name__)

class GitHub:
    @staticmethod
    def run_gh_command(args, cwd=None):
        """Run a GitHub CLI command and return output."""
        try:
            cmd = ['gh'] + args
            result = subprocess.run(
                cmd, 
                cwd=cwd, 
                capture_output=True, 
                text=True, 
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"GitHub CLI Error: {e.stderr}")
            raise

    @classmethod
    def get_pending_issues(cls) -> List[Issue]:
        """Fetch issues with the trigger label."""
        try:
            # Query 1: Review/Feedback items (High Priority)
            review_query = f"assignee:{Config.GITHUB_USER} is:open label:\"{Config.REVIEW_LABEL}\""
            
            # Query 2: Standard Pending items
            pending_query = f"assignee:{Config.GITHUB_USER} is:open -label:\"{Config.WIP_LABEL}\" -label:\"{Config.DONE_LABEL}\" -label:\"{Config.ERROR_LABEL}\" -label:\"{Config.REVIEW_LABEL}\""
            
            all_raw_issues = []
            
            # Fetch Review Issues
            review_out = cls.run_gh_command([
                'issue', 'list', '--repo', Config.GITHUB_REPO, '--search', review_query,
                '--json', 'number,url,title,body,labels', '--limit', '5'
            ])
            review_issues = json.loads(review_out)
            for i in review_issues:
                 i['is_review_task'] = True
            all_raw_issues.extend(review_issues)
            
            # Fetch Pending Issues
            pending_out = cls.run_gh_command([
                'issue', 'list', '--repo', Config.GITHUB_REPO, '--search', pending_query,
                '--json', 'number,url,title,body,labels', '--limit', '5'
            ])
            pending_issues = json.loads(pending_out)
            for i in pending_issues:
                 i['is_review_task'] = False
            all_raw_issues.extend(pending_issues)
            
            return [Issue(**i) for i in all_raw_issues]
            
        except Exception as e:
            logger.error(f"Failed to fetch issues: {e}")
            return []

    @classmethod
    def check_dependencies(cls, issue: Issue) -> bool:
        """Check if all dependencies are resolved."""
        if issue.is_review_task:
            return True
            
        if not issue.body:
            return True
        
        matches = re.findall(r'(?:[Dd]epends on|[Dd]ependencies|[Bb]locked by) #(\d+)', issue.body)
        
        if not matches:
            return True

        logger.info(f"Issue #{issue.number} has dependencies: {matches}")
        
        for dep_num in matches:
            try:
                output = cls.run_gh_command(['issue', 'view', dep_num, '--repo', Config.GITHUB_REPO, '--json', 'state'])
                dep_data = json.loads(output)
                state = dep_data.get('state')
                
                if state != 'closed':
                    logger.info(f"Skipping Issue #{issue.number}: Dependency #{dep_num} is {state} (not closed).")
                    return False
            except Exception as e:
                logger.error(f"Failed to check dependency #{dep_num}: {e}")
                return False
                
        return True

    @classmethod
    def update_labels(cls, issue_number, add_labels=None, remove_labels=None):
        """Update labels on an issue."""
        args = ['issue', 'edit', str(issue_number), '--repo', Config.GITHUB_REPO]
        if add_labels:
            for label in add_labels:
                args.extend(['--add-label', label])
        if remove_labels:
            for label in remove_labels:
                args.extend(['--remove-label', label])
        
        try:
            cls.run_gh_command(args)
            logger.info(f"Updated labels for #{issue_number}: +{add_labels} -{remove_labels}")
        except Exception as e:
            logger.error(f"Failed to update labels for #{issue_number}: {e}")

    @classmethod
    def find_active_branch(cls, issue_number) -> Optional[str]:
        """Check if there's already an open PR for this issue and return its branch."""
        try:
            query = f"{issue_number} in:title,body"
            output = cls.run_gh_command([
                'pr', 'list', '--repo', Config.GITHUB_REPO, 
                '--search', query,
                '--state', 'open',
                '--json', 'headRefName,number,updatedAt',
                '--limit', '5'
            ])
            prs = json.loads(output)
            
            if prs:
                prs.sort(key=lambda x: x['updatedAt'], reverse=True)
                target_branch = prs[0]['headRefName']
                logger.info(f"Found existing active PR #{prs[0]['number']} on branch '{target_branch}'")
                return target_branch
                
        except Exception as e:
            logger.warning(f"Failed to check for active branch: {e}")
            
        return None

    @classmethod
    def fetch_pr_context(cls, issue_number, branch_name, repo_dir) -> Optional[str]:
        """Fetch PR comments if a PR exists for this branch."""
        try:
            pr_list_out = cls.run_gh_command(['pr', 'list', '--head', branch_name, '--json', 'number,url'], cwd=repo_dir)
            pr_list = json.loads(pr_list_out)
            
            if not pr_list:
                return None
                
            pr = pr_list[0]
            context = []
            context.append(f"# Pull Request Context (PR #{pr['number']})")
            context.append(f"URL: {pr['url']}\n")
            
            pr_view_out = cls.run_gh_command(['pr', 'view', str(pr['number']), '--json', 'comments,reviews', '--repo', Config.GITHUB_REPO])
            pr_data = json.loads(pr_view_out)
            
            context.append("## user Reviews & Comments")
            
            for review in pr_data.get('reviews', []):
                if review['state'] != 'APPROVED':
                    context.append(f"### Review by {review['author']['login']} ({review['state']})")
                    context.append(review['body'])
                    context.append("---")
                    
            for comment in pr_data.get('comments', []):
                context.append(f"### Comment by {comment['author']['login']}")
                context.append(comment['body'])
                context.append("---")
                
            return "\n".join(context)
            
        except Exception as e:
            logger.error(f"Failed to fetch PR context: {e}")
            return None
