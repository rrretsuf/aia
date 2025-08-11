from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskType(str, Enum):
    HUMAN_REQUEST = "human_request"
    RESEARCH_SUBTASK = "research_subtask"
    SYNTHESIS = "synthesis"

class Task(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid.uuid4()))
    human_request: str
    status: TaskStatus = TaskStatus.PENDING
    task_type: TaskType = TaskType.HUMAN_REQUEST
    priority: int = Field(default=5, ge=1, le=10)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    results: Optional[Dict[str, Any]] = None
    assigned_agents: List[str] = Field(default_factory=list)
    subtasks: List[str] = Field(default_factory=list)
    parent_task_id: Optional[str] = None
    progress: float = Field(default=0.0, ge=0, le=1.0)

    class Config:
        use_enum_values = True

class TaskSubmission(BaseModel):
    human_request: str = Field(..., min_length=10, max_length=1000)
    priority: int = Field(default=5, ge=1, le=10)
