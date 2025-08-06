from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import uuid

class MessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    STATUS_UPDATE = "status_update"
    RESULT_SHARING = "result_sharing"
    COORDINATION = "coordination"
    ERROR_REPORT = "error_report"
    HEALTH_CHECK = "health_check"

class MessagePriority(str, Enum):
    LOW = 1
    MEDIUM = 5
    HIGH = 8
    URGENT = 10

class A2AMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str
    to_agent: Optional[str] = None
    holon_broadcast: Optional[str] = None
    message_type: MessageType
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    requires_response: bool = False
    response_to: Optional[str] = None
    priority: MessagePriority = MessagePriority.MEDIUM
    ttl: Optional[int] = None  
    processed: bool = False

    class Config:
        use_enum_values = True

class SharedStateUpdate(BaseModel):
    key: str
    value: Any
    agent_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ttl: Optional[int] = None

class ResearchFinding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    agent_id: str
    findings: Dict[str, Any]
    confidence: float = Field(ge=0, le=1.0)
    sources: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    verified: bool = False