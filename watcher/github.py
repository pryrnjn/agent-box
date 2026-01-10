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
    def fetch_pr_context(cls, issue_number, branch_name, repo_dir) -> tuple[Optional[str], List[str]]:
        """Fetch PR comments and thread IDs using GraphQL."""
        try:
            # First, find PR number for the branch
            pr_list_out = cls.run_gh_command(['pr', 'list', '--head', branch_name, '--json', 'number,url'], cwd=repo_dir)
            pr_list = json.loads(pr_list_out)
            
            if not pr_list:
                return None, []
                
            pr = pr_list[0]
            pr_number = pr['number']
            
            # GraphQL Query to fetch threads
            query = """
            query($owner: String!, $repo: String!, $number: Int!) {
              repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                  reviewThreads(first: 50) {
                    nodes {
                      id
                      isResolved
                      comments(first: 1) {
                        nodes {
                          author { login }
                          body
                        }
                      }
                    }
                  }
                }
              }
            }
            """
            
            owner, repo_name = Config.GITHUB_REPO.split('/')
            
            # Use gh api graphql
            variables = json.dumps({'owner': owner, 'repo': repo_name, 'number': pr_number})
            cmd = ['api', 'graphql', '-f', f'query={query}', '-F', f'variables={variables}']
            
            api_out = cls.run_gh_command(cmd)
            data = json.loads(api_out)
            
            threads = data['data']['repository']['pullRequest']['reviewThreads']['nodes']
            
            context = []
            context.append(f"# Pull Request Context (PR #{pr_number})")
            context.append(f"URL: {pr['url']}\n")
            context.append("## User Reviews & Comments")
            
            unresolved_ids = []
            
            for thread in threads:
                if not thread['isResolved']:
                    comment = thread['comments']['nodes'][0]
                    author = comment['author']['login']
                    body = comment['body']
                    
                    unresolved_ids.append(thread['id'])
                    
                    context.append(f"### Comment by {author} (Unresolved)")
                    context.append(body)
                    context.append("---")
            
            if not unresolved_ids:
                context.append("No unresolved comments found.")
                
            return "\n".join(context), unresolved_ids
            
        except Exception as e:
            logger.error(f"Failed to fetch PR context: {e}")
            return None, []

    @classmethod
    def resolve_thread(cls, thread_id: str):
        """Resolve a review thread using GraphQL."""
        try:
            query = """
            mutation($threadId: ID!) {
              resolveReviewThread(input: {threadId: $threadId}) {
                clientMutationId
              }
            }
            """
            variables = json.dumps({'threadId': thread_id})
            cmd = ['api', 'graphql', '-f', f'query={query}', '-F', f'variables={variables}']
            cls.run_gh_command(cmd)
            logger.info(f"Resolved thread {thread_id}")
        except Exception as e:
            logger.error(f"Failed to resolve thread {thread_id}: {e}")
