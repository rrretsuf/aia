from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    OFFLINE = "offline"

class AgentType(str, Enum):
    PLANNER = "planner"
    RESEARCH = "research"

class Agent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: AgentType
    status: AgentStatus = AgentStatus.IDLE
    current_task_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)