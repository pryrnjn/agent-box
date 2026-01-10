from typing import List, Optional
from pydantic import BaseModel

class PRContext(BaseModel):
    number: int
    url: str
    head_ref_name: str
    comments: List[str] = []

class TaskContext(BaseModel):
    issue_number: int
    issue_title: str
    issue_body: str
    issue_url: str
    repo: str  # e.g., "owner/repo"
    
    is_review_task: bool = False
    
    # Branching
    target_branch: str
    is_existing_branch: bool = False
    
    # PR Context
    pr_context: Optional[str] = None # The rendered markdown context
    unresolved_thread_ids: List[str] = []
    
    # Paths
    workspace_dir: str

class Issue(BaseModel):
    number: int
    title: str
    body: str
    url: str
    repo: str # e.g., "owner/repo"
    labels: List[dict] = []
    is_review_task: bool = False
