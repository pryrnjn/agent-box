#!/usr/bin/env python3
"""
Senior Dev Supervisor - Monitors PRs and automates merge workflow.

This script polls for PRs that have completed the review process
(5+ review rounds with all threads resolved), then:
1. Merges the PR
2. Closes the associated issue
3. Assigns the next pending issue to the agent
"""
import logging
import time
import sys

from watcher.config import Config
from watcher.supervisor import SupervisorWorkflow

# Configure logging
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='[%(asctime)s][%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('supervisor.log')
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("🧑‍💼 Senior Dev Supervisor starting...")
    logger.info(f"Min review rounds: {Config.MIN_REVIEW_ROUNDS}")
    logger.info(f"Poll interval: {Config.SUPERVISOR_POLL_INTERVAL}s")
    
    Config.validate()
    repos = Config.get_github_repos()
    
    while True:
        try:
            for repo in repos:
                SupervisorWorkflow.supervise_repo(repo)
                
        except KeyboardInterrupt:
            logger.info("Supervisor stopped by user.")
            break
        except Exception as e:
            logger.error(f"Supervisor error: {e}")
            
        logger.info(f"Sleeping for {Config.SUPERVISOR_POLL_INTERVAL}s...")
        time.sleep(Config.SUPERVISOR_POLL_INTERVAL)

if __name__ == "__main__":
    main()
