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
    CANCELLED = "cancelled"

class TaskPriority(str, Enum):
    LOW = 1
    MEDIUM = 5
    HIGH = 8
    URGENT = 10

class Task(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid.uuid4()))
    human_request: str = Field(..., description="Original human request")
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
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
    priority: TaskPriority = TaskPriority.NORMAL
    context: Dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: float
    results: Optional[Dict[str, Any]] = None
    agent_activities: List[Dict[str, Any]] = Field(default_factory=list)