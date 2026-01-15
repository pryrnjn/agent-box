import os
import re
import json
import logging
import hashlib
from typing import List, Set
from .github import GitHub
from .config import Config

logger = logging.getLogger(__name__)

class LogMonitor:
    """Monitors log files for critical errors and attempts to report them."""
    
    STATE_FILE = "monitor_state.json"
    ERROR_PATTERNS = [
        r"CRITICAL",
        r"Traceback \(most recent call last\)",
        r"FATAL ERROR",
        r"Exception: ",
    ]
    
    def __init__(self, log_files: List[str]):
        self.log_files = log_files
        self.state = self._load_state()
        
    def _load_state(self) -> dict:
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"file_offsets": {}, "reported_errors": {}}

    def _save_state(self):
        try:
            with open(self.STATE_FILE, 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            logger.error(f"Failed to save monitor state: {e}")

    def check_logs(self):
        """Scan logs for new errors."""
        for log_file in self.log_files:
            if not os.path.exists(log_file):
                continue
                
            try:
                self._process_file(log_file)
            except Exception as e:
                logger.error(f"Failed to process log file {log_file}: {e}")
                
        self._save_state()

    def _process_file(self, log_path: str):
        file_size = os.path.getsize(log_path)
        last_offset = self.state["file_offsets"].get(log_path, 0)
        
        # If file shrank (rotated), start from 0
        if file_size < last_offset:
            last_offset = 0
            
        if file_size == last_offset:
            return # No new data
            
        with open(log_path, 'r') as f:
            f.seek(last_offset)
            new_content = f.read()
            self.state["file_offsets"][log_path] = f.tell()
            
        # Scan for errors
        for pattern in self.ERROR_PATTERNS:
            if re.search(pattern, new_content):
                # Found an error! Extract context (naive: just the block around it or the line)
                # Better: Extract the full traceback if possible. 
                # For now, let's grab the lines containing the error + surrounding
                lines = new_content.split('\n')
                for i, line in enumerate(lines):
                    if re.search(pattern, line):
                        # Extract context window (e.g., 5 lines before, 20 lines after for traceback)
                        start = max(0, i - 5)
                        end = min(len(lines), i + 20)
                        context = "\n".join(lines[start:end])
                        
                        self._report_error(log_path, context)
                        break # Report first error found in batch to avoid spam

    def _report_error(self, log_file: str, context: str):
        """Create a GitHub issue for the error."""
        # Gen hash to dedup
        error_hash = hashlib.md5(context.encode()).hexdigest()
        
        # Check if already reported recently (simple dedup)
        if error_hash in self.state["reported_errors"]:
            return
            
        title = f"🚨 Critical Error in {os.path.basename(log_file)}"
        body = f"""
## Automated Error Report

**Source**: `{log_file}`
**Time**: (See logs)

### Traceback / Error Detail
```
{context}
```

Please investigate immediately. 
"""
        try:
            # We need a repo to report to. Use the first one in config? 
            # Or a specific ops repo? Let's use the first tracked repo for now.
            repos = Config.get_github_repos()
            if not repos:
                return
                
            target_repo = repos[0]
            
            # Check if an issue with this title already exists (double check)
            # Actually, let's just create it.
            
            GitHub.run_gh_command([
                'issue', 'create',
                '--repo', target_repo,
                '--title', title,
                '--body', body,
                '--label', Config.ERROR_LABEL
            ])
            
            logger.info(f"Reported critical error in {log_file} to {target_repo}")
            self.state["reported_errors"][error_hash] = True
            
        except Exception as e:
            logger.error(f"Failed to report error: {e}")
