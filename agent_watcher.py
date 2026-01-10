import sys
import time
import logging
from watcher.config import Config
from watcher.github import GitHub
from watcher.workflow import Workflow

# Setup Logging
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('agent_watcher.log')
    ]
)
logger = logging.getLogger(__name__)

def check_self_update():
    """Check for updates to the agent watcher itself."""
    # (Simplified for now, can move to a separate module)
    import subprocess
    import os
    try:
        if not os.path.isdir('.git'):
            return
            
        logger.debug("Checking for self-updates on 'main' branch...")
        subprocess.run(['git', 'fetch', 'origin'], check=True, capture_output=True)
        
        # Get the commit hash of the local HEAD and the remote main branch
        local_hash_proc = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True)
        remote_hash_proc = subprocess.run(['git', 'rev-parse', 'origin/main'], capture_output=True, text=True, check=True)
        
        if local_hash_proc.stdout.strip() != remote_hash_proc.stdout.strip():
            logger.info("New version detected on 'main' branch! Updating...")
            # Use reset --hard to match the deployment script and avoid conflicts
            subprocess.run(['git', 'reset', '--hard', 'origin/main'], check=True, capture_output=True)
            
            logger.info("Update complete. Restarting service in 5 seconds...")
            time.sleep(5)
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Self-update check failed: {e}")

def main():
    try:
        Config.validate()
        repos = Config.get_github_repos()
        logger.info(f"Agent Watcher Started for {repos}")
        
        # Ensure labels exist for all tracked repositories
        for repo in repos:
            GitHub.ensure_labels(repo)
        
        logger.info(f"Polling every {Config.POLL_INTERVAL} seconds for issues assigned to '{Config.GITHUB_USER}'")
        
        loop_count = 0
        while True:
            try:
                loop_count += 1
                
                # Check for Self Update
                loops_per_update = max(1, int(Config.SELF_UPDATE_INTERVAL / Config.POLL_INTERVAL))
                if loop_count % loops_per_update == 0:
                    check_self_update()
                    
                # repos = Config.get_github_repos() # Redundant
                logger.info(f"Polling {repos} for changes... (Time: {time.strftime('%H:%M:%S')})")
                
                processed_any = False
                found_any_issues = False
                
                for repo in repos:
                    try:
                        issues = GitHub.get_pending_issues(repo)
                        if issues:
                            found_any_issues = True
                            for issue in issues:
                                if GitHub.check_dependencies(issue):
                                    Workflow.execute_task(issue)
                                    processed_any = True
                                    # Break to restart loop or continue? 
                                    # If we want to be fair, maybe continue. 
                                    # But if we want to avoid concurrency issues, maybe break and loop again.
                                    # For now, let's process one task at a time per poll cycle across all repos.
                                    break 
                        else:
                            logger.debug(f"No pending issues in {repo}.")
                             
                        if processed_any:
                            break

                    except Exception as e_repo:
                        logger.error(f"Error polling {repo}: {e_repo}")

                if not processed_any:
                    if found_any_issues:
                        logger.info("Found pending issues, but all are currently blocked by dependencies.")
                    else:
                        logger.debug("No pending issues found in any repo.")
                    
            except KeyboardInterrupt:
                logger.info("Stopping watcher...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
            
            time.sleep(Config.POLL_INTERVAL)
            
    except Exception as fatal_error:
        logger.critical(f"FATAL ERROR: {fatal_error}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
