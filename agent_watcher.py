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
        logger.info(f"Agent Watcher Started for {Config.GITHUB_REPO}")
        
        # Ensure labels exist? GitHub.ensure_labels() - could be added
        
        logger.info(f"Polling every {Config.POLL_INTERVAL} seconds for issues assigned to '{Config.GITHUB_USER}'")
        
        loop_count = 0
        while True:
            try:
                loop_count += 1
                
                # Check for Self Update
                loops_per_update = max(1, int(Config.SELF_UPDATE_INTERVAL / Config.POLL_INTERVAL))
                if loop_count % loops_per_update == 0:
                    check_self_update()
                    
                logger.info(f"Polling {Config.GITHUB_REPO} for changes... (Time: {time.strftime('%H:%M:%S')})")
                
                issues = GitHub.get_pending_issues()
                if issues:
                    processed_any = False
                    for issue in issues:
                        if GitHub.check_dependencies(issue):
                            Workflow.execute_task(issue)
                            processed_any = True
                            break
                    
                    if not processed_any:
                        logger.info("Found assigned issues, but all are blocked by dependencies.")
                else:
                    logger.debug("No pending issues.")
                    
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
