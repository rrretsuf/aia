from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    ERROR = "error"
    OFFLINE = "offline"

class AgentType(str, Enum):
    PLANNER = "planner"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    COORDINATOR = "coordinator"

class AgentCapability(BaseModel):
    name: str
    level: float = Field(ge=0, le=1.0)
    description: Optional[str] = None

class Agent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    agent_type: AgentType
    holon_id: str
    status: AgentStatus = AgentStatus.IDLE
    current_task_id: Optional[str] = None
    capabilities: List[AgentCapability] = Field(default_factory=list)
    performance_metrics: Dict[str, float] = Field(default_factory=dict)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    max_concurrent_tasks: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True

class AgentState(BaseModel):
    agent_id: str
    status: AgentStatus
    current_task_id: Optional[str] = None
    progress: float = Field(default=0.0, ge=0, le=1.0)
    last_update: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AgentActivity(BaseModel):
    agent_id: str
    activity_type: str
    description: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)