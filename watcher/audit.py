"""Audit logging and notifications for Agent Box."""
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from .config import Config

logger = logging.getLogger(__name__)

class AuditLog:
    """Persist agent actions to a JSON Lines log file."""
    
    @classmethod
    def _get_log_path(cls) -> Path:
        """Get the audit log file path."""
        log_path = Path(Config.AUDIT_LOG_PATH)
        if not log_path.is_absolute():
            log_path = Path(Config.WORK_DIR_BASE) / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return log_path
    
    @classmethod
    def log(cls, event_type: str, repo: str = None, issue_number: int = None, 
            pr_number: int = None, message: str = None, details: dict = None):
        """Log an event to the audit trail."""
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event_type,
                "repo": repo,
                "issue": issue_number,
                "pr": pr_number,
                "message": message,
                "details": details or {}
            }
            
            # Remove None values
            entry = {k: v for k, v in entry.items() if v is not None}
            
            log_path = cls._get_log_path()
            with open(log_path, 'a') as f:
                f.write(json.dumps(entry) + '\n')
                
            logger.debug(f"Audit: {event_type} - {message}")
            
            # Send ALL audit logs to ntfy for persistence
            # Format: readable message with full JSON details
            ntfy_message = f"[{event_type}] {message or 'No message'}\n\n{json.dumps(entry, indent=2)}"
            notify(ntfy_message, title=f"Agent: {event_type}")
                
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    @classmethod
    def task_started(cls, repo: str, issue_number: int, title: str):
        cls.log("task_started", repo=repo, issue_number=issue_number, 
                message=f"Started: #{issue_number} - {title}")
    
    @classmethod
    def task_completed(cls, repo: str, issue_number: int, pr_url: str = None):
        cls.log("task_completed", repo=repo, issue_number=issue_number,
                message=f"Completed: #{issue_number}", details={"pr_url": pr_url})
    
    @classmethod
    def task_failed(cls, repo: str, issue_number: int, error: str = None):
        cls.log("task_failed", repo=repo, issue_number=issue_number,
                message=f"Failed: #{issue_number}", details={"error": error})
    
    @classmethod
    def pr_merged(cls, repo: str, pr_number: int, issue_number: int = None):
        cls.log("pr_merged", repo=repo, pr_number=pr_number, issue_number=issue_number,
                message=f"Merged: PR #{pr_number}")
    
    @classmethod
    def pr_created(cls, repo: str, pr_number: int, issue_number: int, pr_url: str):
        cls.log("pr_created", repo=repo, pr_number=pr_number, issue_number=issue_number,
                message=f"Created: PR #{pr_number}", details={"url": pr_url})
    
    @classmethod
    def stale_pr_detected(cls, repo: str, pr_number: int, age_hours: float, unresolved: int):
        cls.log("stale_pr_detected", repo=repo, pr_number=pr_number,
                message=f"Stale: PR #{pr_number} ({age_hours:.1f}h, {unresolved} unresolved)")
    
    @classmethod
    def review_assigned(cls, repo: str, issue_number: int):
        cls.log("review_assigned", repo=repo, issue_number=issue_number,
                message=f"Review assigned: #{issue_number}")


def notify(message: str, title: str = "Agent Box", priority: str = "default"):
    """Send push notification via ntfy.sh."""
    topic = Config.NTFY_TOPIC
    if not topic:
        return  # Notifications disabled
    
    try:
        url = f"https://ntfy.sh/{topic}"
        data = message.encode('utf-8')
        
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Title', title)
        req.add_header('Priority', priority)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.debug(f"Notification sent: {message}")
            else:
                logger.warning(f"Notification failed: {response.status}")
                
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")
