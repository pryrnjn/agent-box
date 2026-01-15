import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    GITHUB_REPOS_STR = os.getenv('GITHUB_REPOS', '')
    
    @classmethod
    def get_github_repos(cls):
        return [r.strip() for r in cls.GITHUB_REPOS_STR.split(',') if r.strip()]

    GITHUB_USER = os.getenv('GITHUB_USER')
    POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 60))
    SELF_UPDATE_INTERVAL = int(os.getenv('SELF_UPDATE_INTERVAL', 3600))
    
    # Labels
    TRIGGER_LABEL = os.getenv('TRIGGER_LABEL', 'status:pending-agent')
    WIP_LABEL = os.getenv('WIP_LABEL', 'status:agent-working')
    DONE_LABEL = os.getenv('DONE_LABEL', 'status:agent-done')
    REVIEW_LABEL = os.getenv('REVIEW_LABEL', 'status:agent-review')
    ERROR_LABEL = os.getenv('ERROR_LABEL', 'status:agent-failed')
    
    # Commands
    AGENT_COMMAND_TEMPLATE = os.getenv('AGENT_COMMAND')
    AGENT_REVIEW_COMMAND_TEMPLATE = os.getenv('AGENT_REVIEW_COMMAND')
    
    # Prompt additions
    GIT_COMMIT_INSTRUCTION = " When done, git commit your changes with a descriptive message."
    
    # Workspaces
    WORK_DIR_BASE = os.getenv('WORK_DIR_BASE', 'workspace')
    BRANCH_NAME_TEMPLATE = os.getenv('BRANCH_NAME_TEMPLATE', 'feat/issue-{number}-{safe_title}')
    PR_BASE_BRANCH = os.getenv('PR_BASE_BRANCH', 'develop')
    
    # Supervisor
    MIN_REVIEW_ROUNDS = int(os.getenv('MIN_REVIEW_ROUNDS', 5))
    SUPERVISOR_POLL_INTERVAL = int(os.getenv('SUPERVISOR_POLL_INTERVAL', 300))
    STALE_PR_HOURS = int(os.getenv('STALE_PR_HOURS', 24))
    
    # Phase Mapping
    PHASE_MAP = {
        '0': 'feat/phase0-foundation',
        '1': 'feat/phase1-memory',
        '2': 'feat/phase2-teacher',
        '3': 'feat/phase3-reward',
        '4': 'feat/phase4-curriculum'
    }
    
    # Logging
    LOG_LEVEL_STR = os.getenv('LOG_LEVEL', 'INFO').upper()
    LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

    @classmethod
    def validate(cls):
        if not cls.get_github_repos():
            raise ValueError("No repositories configured. Set GITHUB_REPOS.")
        if not cls.GITHUB_USER:
            raise ValueError("GITHUB_USER not defined in config.")
